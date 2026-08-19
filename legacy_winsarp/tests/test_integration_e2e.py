"""
test_integration_e2e.py
Test di integrazione end-to-end per Ermes.

Verifica il flusso completo:
  1. Inizializzazione LlamaIndex (embed model + node parser)
  2. Creazione indicizzazione modulo WinSarp su documenti di test
  3. Blue-Green: verifica che dopo indicizzazione il pointer sia diverso dal blue iniziale
  4. Verifica fonti retrieval (get_source_nodes)
  5. Re-indicizzazione: verifica che il blue-green swap funzioni
  6. Fallimento indicizzazione: verifica che la vecchia collection resti intatta
  7. Verifica Knowledge Graph
  8. Pulizia file temporanei

Requires:
  - Ollama attivo con qwen3.5:9b e bge-m3
  - Python 3.11+
"""
import logging
import os
import sys
import tempfile
import time

# Aggiungi root del progetto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chromadb

from config import cfg
from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
from legacy_winsarp.core.rag_engine import (
    check_ollama,
    get_active_coll_name,
    get_index,
    get_source_nodes,
    init_llama_settings,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
_logger = logging.getLogger("test_e2e")

PASS = 0
FAIL = 0


def _assert(condition: bool, message: str):
    global PASS, FAIL
    if condition:
        PASS += 1
        _logger.info("  \u2705 PASS: %s", message)
    else:
        FAIL += 1
        _logger.error("  \u274c FAIL: %s", message)


def _make_test_doc(directory: str, filename: str, content: str):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    _logger.debug("Creato file test: %s", path)
    return path


TEST_WINSARP_CATALOG = """# WinSarp Catalogo Formule

### <a name="100"></a> 100 - Formula Principale
**Tipo:** Inizio Giornata
**Scopo:** Formula principale di calcolo ore ordinarie

```
(55=I)(71=0)(561=1)K601A561(561=0)(800=0)(50=19)R130;(50=AUTS)R140;(50=MALAT)R150;(50=MATERN)R160;R110;
```

### <a name="130"></a> 130 - Straordinario Festivo
**Tipo:** Di Giornata
**Scopo:** Calcolo straordinario per giorni festivi

```
(50=19)V11(55=UZ)(71=0)(70=11)(72=?70!)K601A561R200;
```

### <a name="140"></a> 140 - Straordinario Diurno
**Tipo:** Di Giornata
**Scopo:** Calcolo straordinario per lavoro diurno

```
(55=I)(50=AUTS)V11(71=0)(70=11)(72=?70!)K601A561R200;
```
"""


def main():
    global PASS, FAIL
    _logger.info("=" * 60)
    _logger.info("TEST INTEGRAZIONE END-TO-END")
    _logger.info("=" * 60)

    # ---------------------------------------------------------------
    # 0. PRE-CONDIZIONI: Ollama attivo
    # ---------------------------------------------------------------
    _logger.info("\n[0] Verifica pre-condizioni (Ollama)...")
    ok, msg = check_ollama()
    _assert(ok, f"Ollama attivo: {msg}")
    if not ok:
        _logger.error("Ollama non disponibile, salto test. Dettaglio: %s", msg)
        return 1

    # ---------------------------------------------------------------
    # 1. INIZIALIZZAZIONE
    # ---------------------------------------------------------------
    _logger.info("\n[1] Inizializzazione LlamaIndex...")
    try:
        init_llama_settings()
        _assert(True, "init_llama_settings completato")
    except Exception as e:
        _assert(False, f"init_llama_settings fallito: {e}")
        return 1

    # ---------------------------------------------------------------
    # 2. CREA DOCUMENTI DI TEST IN DIRECTORY TEMPORANEA
    # ---------------------------------------------------------------
    _logger.info("\n[2] Creazione documenti di test WinSarp...")
    test_dir = tempfile.mkdtemp(prefix="ermes_e2e_test_")
    chroma_test_dir = os.path.join(test_dir, "chroma_db")
    docs_test_dir = os.path.join(test_dir, "documenti")
    winsarp_dir = os.path.join(docs_test_dir, "WinSarp")
    hash_file_path = os.path.join(test_dir, "test_hashes.json")

    _make_test_doc(winsarp_dir, "WinSarp_Formule.txt", TEST_WINSARP_CATALOG)
    _assert(os.path.exists(winsarp_dir), "Directory documenti di test creata")

    base_name = "coll_winsarp"
    initial_default = get_active_coll_name("WinSarp", base_name, chroma_dir=chroma_test_dir)
    _logger.info("  Nome default iniziale: %s", initial_default)

    # ---------------------------------------------------------------
    # 3. PRIMA INDICIZZAZIONE (blue-green)
    # ---------------------------------------------------------------
    _logger.info("\n[3] Prima indicizzazione WinSarp...")
    index1 = get_index(
        modulo="WinSarp",
        model_id=cfg.DEFAULT_MODEL_ID,
        base_docs_dir=docs_test_dir,
        base_chroma_path=chroma_test_dir,
        hash_file=hash_file_path,
    )
    _assert(index1 is not None, "Primo indice creato con successo")

    # Verifica blue-green: pointer deve essere cambiato dal default
    active_name_after_first = get_active_coll_name("WinSarp", base_name, chroma_dir=chroma_test_dir)
    _assert(
        active_name_after_first != initial_default,
        f"Blue-Green: active dopo indicizzazione ('{active_name_after_first}') diverso da default ('{initial_default}')",
    )

    # Verifica collection attiva in ChromaDB
    persist_path = os.path.join(chroma_test_dir, "winsarp")
    db = chromadb.PersistentClient(path=persist_path)
    active_coll = db.get_or_create_collection(active_name_after_first)
    count1 = active_coll.count()
    _assert(count1 > 0, f"Collection attiva '{active_name_after_first}' ha {count1} documenti")

    # ---------------------------------------------------------------
    # 4. VERIFICA RETRIEVAL FONTI (get_source_nodes - solo vector, senza LLM)
    # ---------------------------------------------------------------
    _logger.info("\n[4] Verifica retrieval fonti...")
    sources = get_source_nodes(
        modulo="WinSarp",
        model_id=cfg.DEFAULT_MODEL_ID,
        index=index1,
        query="formula 130 straordinario festivo",
    )
    _assert(len(sources) > 0, f"get_source_nodes: fonti recuperate ({len(sources)})")
    if sources:
        scores = [s.get("score", 0) or 0 for s in sources]
        top_score = max(scores)
        _assert(top_score > 0, f"Score retrieval > 0 (top={top_score:.3f})")
        _logger.info("  Top score: %.3f, fonti: %d", top_score, len(sources))

    # ---------------------------------------------------------------
    # 5. RE-INDICIZZAZIONE (blue-green swap)
    # ---------------------------------------------------------------
    _logger.info("\n[5] Re-indicizzazione (simula cambio documenti)...")
    _make_test_doc(
        winsarp_dir,
        "WinSarp_Formule_extra.txt",
        """### <a name="200"></a> 200 - Formula Finale
**Tipo:** Fine Giornata
**Scopo:** Formula di chiusura e totalizzazione

```
(55=F)(800=0)(71=0)(70=11)(72=?70!)K601A561R999;
```
"""
    )

    index2 = get_index(
        modulo="WinSarp",
        model_id=cfg.DEFAULT_MODEL_ID,
        base_docs_dir=docs_test_dir,
        base_chroma_path=chroma_test_dir,
        hash_file=hash_file_path,
    )
    _assert(index2 is not None, "Secondo indice (re-index) creato con successo")

    # Verifica blue-green swap: pointer diverso da dopo prima indicizzazione
    active_name_after_second = get_active_coll_name("WinSarp", base_name, chroma_dir=chroma_test_dir)
    _assert(
        active_name_after_second != active_name_after_first,
        f"Blue-Green swap: active dopo re-index ('{active_name_after_second}') diverso da prima ('{active_name_after_first}')",
    )

    # Verifica: entrambe le collection esistono
    db2 = chromadb.PersistentClient(path=persist_path)
    green_coll = db2.get_or_create_collection(f"{base_name}_green")
    blue_coll = db2.get_or_create_collection(f"{base_name}_blue")
    count_green = green_coll.count()
    count_blue = blue_coll.count()
    _logger.info("  Collection _green: %d docs, _blue: %d docs", count_green, count_blue)
    _assert(
        count_green > 0 and count_blue > 0,
        f"Entrambe le collection esistono: _green={count_green} docs, _blue={count_blue} docs",
    )

    # ---------------------------------------------------------------
    # 6. VERIFICA ROLLBACK SU FALLIMENTO INDICIZZAZIONE
    # ---------------------------------------------------------------
    _logger.info("\n[6] Verifica rollback su fallimento indicizzazione...")
    active_before_fail = get_active_coll_name("WinSarp", base_name, chroma_dir=chroma_test_dir)

    # Simula fallimento: docs path inesistente
    index_fail = get_index(
        modulo="WinSarp",
        model_id=cfg.DEFAULT_MODEL_ID,
        base_docs_dir=winsarp_dir + "_inesistente",
        base_chroma_path=chroma_test_dir,
        hash_file=hash_file_path,
    )
    _assert(index_fail is None, "Indicizzazione su docs path inesistente ritorna None (fallimento atteso)")

    active_after_fail = get_active_coll_name("WinSarp", base_name, chroma_dir=chroma_test_dir)
    _assert(
        active_after_fail == active_before_fail,
        f"Blue-Green rollback: active invariato dopo fallimento ('{active_after_fail}' == '{active_before_fail}')",
    )

    # ---------------------------------------------------------------
    # 7. VERIFICA KNOWLEDGE GRAPH
    # ---------------------------------------------------------------
    _logger.info("\n[7] Verifica Knowledge Graph...")
    kg = KnowledgeGraph()
    stats = kg.stats()
    _logger.info("  KG stats: %s", stats)
    _assert(stats.get("totale_formule", 0) > 0, f"KG ha {stats.get('totale_formule', 0)} formule")

    formula_130 = kg.get_formula(130)
    _assert(formula_130 is not None, "KG formula 130 esiste")
    if formula_130:
        _assert(len(formula_130.get("name", "")) > 0, f"KG formula 130 ha nome: '{formula_130.get('name')}'")
        _assert(len(formula_130.get("tipo", "")) > 0, f"KG formula 130 ha tipo: '{formula_130.get('tipo')}'")

    # ---------------------------------------------------------------
    # 8. PULIZIA E RIEPILOGO
    # ---------------------------------------------------------------
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    _logger.info("\n[8] Pulizia completata: rimossa directory temporanea %s", test_dir)

    _logger.info("\n" + "=" * 60)
    _logger.info("RIEPILOGO TEST INTEGRAZIONE E2E")
    _logger.info("=" * 60)
    _logger.info("  PASS: %d", PASS)
    _logger.info("  FAIL: %d", FAIL)
    _logger.info("  TOT:  %d", PASS + FAIL)
    _logger.info("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    start = time.time()
    exit_code = main()
    elapsed = time.time() - start
    _logger.info("Tempo totale: %.1fs", elapsed)
    sys.exit(exit_code)
