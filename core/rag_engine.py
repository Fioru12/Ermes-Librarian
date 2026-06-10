"""
rag_engine.py
Configurazione LlamaIndex, indice ChromaDB, chat engine e retrieval.
Nessuna dipendenza da streamlit — pura logica di business.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.request

import chromadb
from filelock import FileLock
from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.chroma import ChromaVectorStore

from config import cfg
from core.error_handler import log_error, retry_on_error
from core.formula_booster import FormulaNumberBooster
from core.utils import compute_dir_hash, load_hash, save_hash, validate_docs
from modules.winsarp import PROMPT_GENERALE, PROMPTS, PROMPTS_GENERAZIONE

_logger = logging.getLogger(__name__)


def _ollama_url() -> str:
    host = cfg.OLLAMA_HOST.strip()
    host = host.rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    return host


# ============================================================
# CONFIGURAZIONE MODELLI
# ============================================================
DEFAULT_MODEL_ID = cfg.DEFAULT_MODEL_ID
EMBED_MODEL_ID = cfg.EMBED_MODEL_ID

AVAILABLE_MODELS = {
    "Qwen3.5 4B (veloce, ~10s)": "qwen3.5:4b",
    "Qwen3.5 9B (qualita, ~1min)": "qwen3.5:9b",
}

MODULE_CONFIG = {
    "WinSarp": {
        "temperature": 0,
        "chat_history": 50,
        "num_ctx": 4096,
        "top_k": 4,
    },
    "__default__": {
        "temperature": 0.3,
        "chat_history": 10,
        "num_ctx": 2048,
        "top_k": 3,
    },
}


# ============================================================
# SOGLIE CONFIDENZA RAG — lette da config.py
# ============================================================
SCORE_THRESHOLD_LOW = cfg.SCORE_THRESHOLD_LOW
SCORE_THRESHOLD_MED = cfg.SCORE_THRESHOLD_MED


# ============================================================
# LOCK GLOBALE CHROMA — serializza le scritture cross-process
# ============================================================
_chroma_lock = FileLock(os.path.join(cfg.BASE_DIR, ".chroma_lock"), timeout=30)


# ============================================================
# SETUP GLOBALE LLAMA_INDEX
# ============================================================
def init_llama_settings():
    """
    Inizializza Settings di LlamaIndex.

    MarkdownNodeParser splitta il catalogo formule WinSarp (.txt markdown)
    in corrispondenza delle intestazioni ###: ogni formula diventa un nodo
    autonomo. Il PDF del manuale operativo (non markdown) rimane un unico
    nodo, che è ok per retrieval accessorio.
    """
    Settings.embed_model = OllamaEmbedding(
        model_name=EMBED_MODEL_ID,
        base_url=_ollama_url(),
    )
    Settings.node_parser = MarkdownNodeParser()


# ============================================================
# HELPERS
# ============================================================
def get_module_config(modulo: str) -> dict:
    return MODULE_CONFIG.get(modulo, MODULE_CONFIG["__default__"])



def get_llm(modulo: str, model_id: str = DEFAULT_MODEL_ID) -> Ollama:
    mcfg = get_module_config(modulo)
    return Ollama(
        model=model_id,
        request_timeout=600.0,
        temperature=mcfg["temperature"],
        context_window=mcfg["num_ctx"],
        base_url=_ollama_url(),
    )



def _find_ollama() -> str | None:
    r"""
    Cerca Ollama nell'ordine:
      1. PATH di sistema (shutil.which)
      2. Fallback Windows su %LOCALAPPDATA%\Programs\Ollama\ollama.exe
    Ritorna il path trovato o None se non esiste.
    """
    found = shutil.which("ollama")
    if found:
        return found

    fallback = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "Ollama", "ollama.exe",
    )
    if os.path.exists(fallback):
        return fallback

    return None



def _installed_models(output: str) -> set[str]:
    models = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name "):
            continue
        first = line.split()[0]
        if first:
            # Normalizza: rimuovi solo :latest se presente, mantieni altri formati come qwen2.5:7b
            if first.endswith(":latest"):
                normalized = first[:-7]  # Rimuovi :latest
            else:
                normalized = first
            models.add(normalized)
    return models



def _node_to_source_dict(node, max_chars: int = 400) -> dict:
    inner_node = getattr(node, "node", None)
    if inner_node is not None:
        metadata = getattr(inner_node, "metadata", {}) or {}
        source = metadata.get("file_name", "—")
        try:
            text = inner_node.get_content()[:max_chars]
        except Exception as ex:
            _logger.debug("_node_to_source_dict: fallback to .text: %s", ex)
            text = getattr(inner_node, "text", "")[:max_chars]
        score = round(getattr(node, "score", 0) or 0, 3)
        return {"text": text, "score": score, "source": source}

    metadata = getattr(node, "metadata", {}) or {}
    text = getattr(node, "text", "")[:max_chars]
    score = round(getattr(node, "score", 0) or 0, 3)
    source = metadata.get("file_name", "—")
    return {"text": text, "score": score, "source": source}


# ============================================================
# CONTROLLO OLLAMA
# ============================================================
def check_ollama_uncached(model_id: str = DEFAULT_MODEL_ID) -> tuple[bool, str]:
    """
    Verifica che Ollama sia attivo e che i modelli necessari siano presenti.
    Versione non-cached per uso in API e test. Retry su errori transitori.
    """
    ollama_exe = _find_ollama()
    if not ollama_exe:
        return False, "Ollama non trovato sul sistema."

    try:
        kwargs = {"creationflags": 0x08000000} if os.name == "nt" else {}

        def _run_ollama_list():
            return subprocess.run(
                [ollama_exe, "list"],
                capture_output=True,
                text=True,
                timeout=5,
                **kwargs,
            )

        result = retry_on_error(
            _run_ollama_list,
            max_attempts=3,
            delay=0.5,
            exceptions=(subprocess.TimeoutExpired,),
            on_retry=lambda a, e: log_error(f"ollama list tentativo {a} fallito", error=e),
        )

        if result.returncode != 0:
            return False, "Ollama e' installato ma non risponde correttamente."

        installed = _installed_models(result.stdout)
        missing = [m for m in [model_id, EMBED_MODEL_ID] if m not in installed]
        if missing:
            return False, f"Modelli mancanti in Ollama: {', '.join(missing)}"

        return True, "OK"

    except FileNotFoundError:
        return False, "Ollama non trovato sul sistema."
    except subprocess.TimeoutExpired:
        return False, "Ollama non risponde (timeout)."
    except Exception as e:
        return False, f"Errore controllo Ollama: {e}"


def check_ollama(model_id: str = DEFAULT_MODEL_ID) -> tuple[bool, str]:
    """
    Verifica che Ollama sia attivo e che i modelli necessari siano presenti.
    """
    return check_ollama_uncached(model_id)


def fetch_ollama_models() -> list[str]:
    """
    Recupera la lista dei modelli LLM disponibili su Ollama.
    Filtra modelli di embedding (contengono 'embed' o coincidono con EMBED_MODEL_ID).
    """
    try:
        req = urllib.request.Request(
            f"{_ollama_url()}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        embed_lower = EMBED_MODEL_ID.lower()
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            name_lower = name.lower()
            if "embed" in name_lower or name_lower.startswith(embed_lower):
                continue
            models.append(name)
        return sorted(models)
    except Exception as e:
        _logger.warning("fetch_ollama_models: %s", e)
        return []


# ============================================================
# INDICE RAG
# ============================================================
def get_index(
    modulo: str,
    model_id: str,
    base_docs_dir: str,
    base_chroma_path: str,
    hash_file: str,
    cache_buster: str = "",
):
    """
    Carica o crea l'indice ChromaDB per il modulo specificato.
    Nessuna dipendenza Streamlit — usa solo logging.

    Logica hash-based:
      - DB popolato e hash invariato -> carica senza reindicizzare
      - DB vuoto o hash cambiato     -> reindicizza da zero

    Nota: vengono indicizzati solo .txt, .pdf e .docx.
    I .csv sono esclusi per evitare rumore nel retrieval.
    """
    _ = (model_id, cache_buster)

    modulo_path = os.path.join(base_docs_dir, modulo)
    persist_path = os.path.join(base_chroma_path, modulo.lower())

    ok, msg, _ = validate_docs(modulo_path)
    if not ok:
        _logger.error("get_index: %s", msg)
        return None
    if msg:
        _logger.warning("get_index: %s", msg)

    coll_name = f"coll_{re.sub(r'[^a-zA-Z0-9]', '', modulo.lower())}"
    current_hash = compute_dir_hash(modulo_path)
    saved_hash = load_hash(hash_file, modulo)

    _logger.info("Indicizzazione %s...", modulo)

    # Check rapido: se hash corrisponde e collection esiste, salta indicizzazione
    try:
        with _chroma_lock:
            db = chromadb.PersistentClient(path=persist_path)
            collection = db.get_or_create_collection(coll_name)
            coll_count = collection.count()

            _logger.info("Hash corrente: %s...", current_hash[:16])
            _logger.info("Hash salvato: %s...", saved_hash[:16] if saved_hash else 'None')
            _logger.info("Documenti in collection: %d", coll_count)

            if coll_count > 0 and current_hash == saved_hash:
                _logger.info("Cache valida: %d documenti già indicizzati", coll_count)
                vector_store = ChromaVectorStore(chroma_collection=collection)
                storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
                return VectorStoreIndex.from_vector_store(
                    vector_store,
                    storage_context=storage_ctx,
                )
            else:
                reason = "hash diverso" if current_hash != saved_hash else "collection vuota"
                _logger.info("Cache non valida: %s, procedo con indicizzazione", reason)
    except Exception as e:
        _logger.warning("Check cache fallito, procedo con indicizzazione: %s", e)

    _logger.info("Lettura documenti...")

    try:
        docs = SimpleDirectoryReader(
            modulo_path,
            required_exts=[".txt", ".pdf", ".docx"],
        ).load_data()
    except Exception as e:
        _logger.error("Errore lettura documenti: %s", e)
        return None

    if not docs:
        _logger.error("Nessun documento leggibile trovato.")
        return None

    _logger.info("Indicizzazione con MarkdownNodeParser — %d file...", len(docs))

    # FASE 2: Operazioni ChromaDB - solo queste sotto lock
    try:
        with _chroma_lock:
            db = chromadb.PersistentClient(path=persist_path)
            collection = db.get_or_create_collection(coll_name)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_ctx = StorageContext.from_defaults(vector_store=vector_store)

            try:
                db.delete_collection(coll_name)
            except Exception as ex:
                ex_str = str(ex).lower()
                if "not found" not in ex_str and "does not exist" not in ex_str:
                    _logger.warning("get_index: delete_collection fallito (errore vero): %s", ex)
                else:
                    _logger.debug("get_index: collection non esiste (ok): %s", ex)

            collection = db.get_or_create_collection(coll_name)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_ctx = StorageContext.from_defaults(vector_store=vector_store)

            index = VectorStoreIndex.from_documents(
                docs,
                storage_context=storage_ctx,
            )
    except Exception as e:
        _logger.error("get_index: errore generazione embeddings per %s (docs=%d): %s",
                      modulo, len(docs), e, exc_info=True)
        return None

    # FASE 3: Save hash - lock separato breve
    with _chroma_lock:
        save_hash(hash_file, modulo, current_hash)

    _logger.info("Indicizzazione %s completata", modulo)
    return index


# ============================================================
# CHAT ENGINE
# ============================================================
def _resolve_prompt(modulo: str, use_generation_prompt: bool = False, formula_only: bool = False, modules: dict | None = None) -> str:
    """
    Risolve il system prompt per un modulo.
    Cerca prima nella mappa moduli (se fornita),
    poi nel fallback legacy (PROMPTS).
    """
    base = None
    if modules is not None:
        # Ordina: moduli specifici prima, Generic fallback per ultimo
        for mod in sorted(
            modules.values(),
            key=lambda m: (m.name.lower() != modulo.lower(), m.name == "Generic"),
        ):
            if mod.is_applicable(modulo):
                if use_generation_prompt and mod.supports_generation():
                    base = mod.get_generation_prompt(modulo)
                else:
                    base = mod.get_system_prompt()
                if formula_only and mod.has_formula_only():
                    base += mod.get_formula_only_instruction()
                break

    # Fallback legacy se non trovato
    if not base:
        if use_generation_prompt and modulo == "WinSarp":
            base = PROMPTS_GENERAZIONE.get(modulo, PROMPT_GENERALE)
        else:
            base = PROMPTS.get(modulo, PROMPT_GENERALE)
        if formula_only and modulo == "WinSarp":
            base += (
                "\n\nRISPOSTA SOLO FORMULA: L'utente ha richiesto 'formula_only'. "
                "Rispondi ESCLUSIVAMENTE con il codice della formula, senza header, "
                "senza spiegazioni e senza testo aggiuntivo. Ritorna solo il codice compresso "
                "dentro un blocco di codice o come singola riga. "
                "Se non trovi una formula, rispondi esattamente: Nel catalogo non e' presente una formula per questo caso."
            )
    return base


def build_chat_engine(modulo: str, model_id: str, index, use_generation_prompt: bool = False, formula_only: bool = False, modules: dict | None = None):
    """
    Costruisce il chat engine LlamaIndex con memoria e system prompt.
    Va ricostruito ogni volta che cambia modulo.

    Args:
        modulo: Nome del modulo
        model_id: ID del modello LLM
        index: Indice vettoriale
        use_generation_prompt: Se True, usa prompt di generazione invece di retrieval
        formula_only: Se True (WinSarp), aggiunge istruzioni per rispondere solo con la formula
        modules: Dict opzionale di moduli (es. st.session_state.modules) per risolvere il prompt
    """
    from llama_index.core.chat_engine import CondensePlusContextChatEngine

    mcfg = get_module_config(modulo)
    system_prompt = _resolve_prompt(modulo, use_generation_prompt, formula_only, modules=modules)

    llm = get_llm(modulo, model_id)
    memory = ChatMemoryBuffer.from_defaults(
        token_limit=mcfg["chat_history"] * 600
    )

    retriever = index.as_retriever(similarity_top_k=mcfg["top_k"])

    return CondensePlusContextChatEngine.from_defaults(
        retriever=retriever,
        llm=llm,
        memory=memory,
        system_prompt=system_prompt,
        node_postprocessors=[FormulaNumberBooster()],
        verbose=False,
    )


# ============================================================
# RECUPERO CONTESTO RAG (chunk usati + score)
# ============================================================
def get_source_nodes(modulo: str, model_id: str, index,
                     query: str) -> list[dict]:
    """
    Esegue una query di retrieval puro sull'indice e restituisce
    i chunk usati con il loro score di similarita'.
    Usata da chat_handler come fonte primaria di chunk retrieval.
    source_nodes nello streaming_response.

    Ritorna:
        [{"text": str, "score": float, "source": str}, ...]
    """
    _ = model_id
    mcfg = get_module_config(modulo)
    retriever = index.as_retriever(similarity_top_k=mcfg["top_k"])
    try:
        nodes = retriever.retrieve(query)
        return [_node_to_source_dict(node, max_chars=400) for node in nodes]
    except Exception as ex:
        _logger.warning("get_source_nodes: retrieval fallito per %s: %s", modulo, ex)
        return []


# ============================================================
# VALUTAZIONE CONFIDENZA
# ============================================================
def score_to_confidence(top_score: float) -> str:
    """
    Converte il top score di retrieval in livello confidenza testuale.

    Soglie (cosine similarity ChromaDB):
      >= SCORE_THRESHOLD_MED -> "alta"
      >= SCORE_THRESHOLD_LOW -> "media"
      <  SCORE_THRESHOLD_LOW -> "bassa"

    Ritorna: "alta" | "media" | "bassa"
    """
    if top_score >= SCORE_THRESHOLD_MED:
        return "alta"
    if top_score >= SCORE_THRESHOLD_LOW:
        return "media"
    return "bassa"



def is_low_confidence(sources: list[dict]) -> bool:
    if not sources:
        return True
    top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
    return top_score < SCORE_THRESHOLD_LOW
