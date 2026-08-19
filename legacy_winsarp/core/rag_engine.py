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
import urllib.request

import chromadb
from filelock import FileLock
from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.vector_stores.chroma import ChromaVectorStore

from config import cfg
from core.ai.utils import compute_dir_hash, load_hash, save_hash, validate_docs
from legacy_winsarp.modules.winsarp import PROMPT_GENERALE, PROMPTS, PROMPTS_GENERAZIONE

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
        "num_ctx": 16384,
        "top_k": 4,
    },
    "__default__": {
        "temperature": 0.3,
        "chat_history": 10,
        "num_ctx": 4096,
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
    Usa HuggingFaceEmbedding locale invece di OllamaEmbedding per
    eliminare la dipendenza da Ollama (OpenRouter gestisce le chiamate LLM).
    """
    # Mappa il modello embedding da config a HuggingFace
    hf_model = EMBED_MODEL_ID
    if "/" not in hf_model:
        # Nome modello Ollama -> equivalente HuggingFace
        ollama_to_hf = {
            "bge-m3": "BAAI/bge-m3",
            "bge-small": "BAAI/bge-small-en-v1.5",
            "bge-large": "BAAI/bge-large-en-v1.5",
            "all-minilm": "sentence-transformers/all-MiniLM-L6-v2",
            "nomic-embed-text": "nomic-ai/nomic-embed-text-v1",
        }
        hf_model = ollama_to_hf.get(hf_model.lower(), "BAAI/bge-m3")
    _logger.info("Embedding model: %s (from config: %s)", hf_model, EMBED_MODEL_ID)
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        Settings.embed_model = HuggingFaceEmbedding(
            model_name=hf_model,
            cache_folder=os.path.join(cfg.BASE_DIR, ".embed_cache"),
        )
    except ImportError:
        # L'import del server non deve dipendere da un embedding provider
        # opzionale. In un'installazione minimale usiamo l'embedder locale
        # Ollama, già dichiarato fra le dipendenze di runtime.
        from llama_index.embeddings.ollama import OllamaEmbedding

        _logger.warning(
            "llama-index-embeddings-huggingface non installato; uso Ollama per gli embedding."
        )
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

def _get_embed_dim() -> int:
    """Restituisce la dimensione del vettore embedding del modello corrente."""
    embed_model = Settings.embed_model
    if hasattr(embed_model, 'dimensions') and embed_model.dimensions is not None:
        return embed_model.dimensions
    # Fallback: genera un embedding di test
    test_vec = embed_model.get_text_embedding("test")
    return len(test_vec)



def get_llm(modulo: str, model_id: str = DEFAULT_MODEL_ID):
    """Restituisce un'istanza LLM, usando il bridge centralizzato.

    Se OPENROUTER_API_KEY è configurata, usa OpenRouter tramite
    llm_bridge.OpenRouterLLM. Altrimenti usa Ollama locale (legacy).
    """
    # Prova nuovo bridge se disponibile
    try:
        from core.ai.llm_bridge import get_llm as bridge_get_llm
        mcfg = get_module_config(modulo)
        return bridge_get_llm(
            model_id=model_id,
            temperature=mcfg["temperature"],
            request_timeout=900.0,
            context_window=mcfg["num_ctx"],
        )
    except ImportError:
        pass

    # Fallback legacy: Ollama diretto
    from llama_index.llms.ollama import Ollama
    mcfg = get_module_config(modulo)
    return Ollama(
        model=model_id,
        request_timeout=900.0,
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
    Usa l'API HTTP (funziona anche in Docker senza CLI).
    """
    try:
        url = f"{_ollama_url()}/api/tags"
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        installed = [m.get("name", "") for m in data.get("models", [])]
        missing = [m for m in [model_id, EMBED_MODEL_ID] if not any(m in i for i in installed)]
        if missing:
            return False, f"Modelli mancanti in Ollama: {', '.join(missing)}"

        return True, "OK"

    except Exception as e:
        return False, f"Errore connessione Ollama: {e}"


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


def get_active_coll_name(modulo: str, base_name: str, chroma_dir: str = "") -> str:
    """
    Blue-Green: restituisce il nome della collection attiva per il modulo.
    Cerca in active_collection.json; se non presente, default a _blue.

    Args:
        modulo: Nome del modulo
        base_name: Nome base della collection
        chroma_dir: Path alla directory chroma (default: cfg.CHROMA_DIR)
    """
    pointer_path = os.path.join(chroma_dir or cfg.CHROMA_DIR, "active_collection.json")
    if os.path.exists(pointer_path):
        try:
            with open(pointer_path, encoding="utf-8") as f:
                return json.load(f).get(modulo.lower(), f"{base_name}_blue")
        except Exception:
            pass
    return f"{base_name}_blue"

def set_active_coll_name(modulo: str, new_name: str, chroma_dir: str = ""):
    """
    Blue-Green: imposta quale collection e' attiva per il modulo (thread-safe).
    Chiamato SOLO dopo che la nuova indicizzazione e' completata con successo.

    Args:
        modulo: Nome del modulo
        new_name: Nome della collection da attivare
        chroma_dir: Path alla directory chroma (default: cfg.CHROMA_DIR)
    """
    pointer_path = os.path.join(chroma_dir or cfg.CHROMA_DIR, "active_collection.json")
    import tempfile
    with _chroma_lock:
        try:
            os.makedirs(os.path.dirname(pointer_path), exist_ok=True)
            data = {}
            if os.path.exists(pointer_path):
                with open(pointer_path, encoding="utf-8") as f:
                    data = json.load(f)
            data[modulo.lower()] = new_name
            tmp = tempfile.NamedTemporaryFile(dir=os.path.dirname(pointer_path), delete=False, suffix=".tmp", mode="w", encoding="utf-8")
            try:
                json.dump(data, tmp, indent=2)
                tmp.close()
                os.replace(tmp.name, pointer_path)
            except Exception:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
                raise
        except Exception as e:
            _logger.error("set_active_coll_name: %s", e)

def _get_staging_coll_name(active_name: str, base_name: str) -> str:
    """
    Blue-Green: restituisce il nome opposto (staging) rispetto a quello attivo.
    Se active e' _blue, staging e' _green; viceversa.
    """
    if active_name.endswith("_blue"):
        return f"{base_name}_green"
    return f"{base_name}_blue"


# ============================================================
# INDICE RAG — Blue-Green Deployment
# ============================================================
def _node_has_text(node) -> bool:
    """True se il nodo contiene testo significativo (non binario/immagine)."""
    try:
        text = node.text if hasattr(node, 'text') else str(node)
    except Exception:
        return False
    if not text or not text.strip():
        return False
    stripped = text.strip()
    # Nodi con solo character replacement o troppo corti per essere utili
    if len(stripped) < 10:
        return False
    # Se la maggior parte dei caratteri sono di replacement (da lettura binare), salta
    printable = sum(1 for c in stripped[:200] if c.isprintable() or c in '\n\r\t')
    if printable / max(len(stripped[:200]), 1) < 0.5:
        return False
    return True


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
    Usa strategia Blue-Green: scrive su una collection di staging,
    e solo a indicizzazione completata con successo scambia il pointer.

    Logica hash-based:
      - Hash invariato e collection attiva popolata -> carica senza reindicizzare
      - Hash cambiato                               -> reindicizza su staging

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

    base_name = f"coll_{re.sub(r'[^a-zA-Z0-9]', '', modulo.lower())}"
    active_name = get_active_coll_name(modulo, base_name, chroma_dir=base_chroma_path)
    current_hash = compute_dir_hash(modulo_path)
    saved_hash = load_hash(hash_file, modulo)

    _logger.info("Indicizzazione %s...", modulo)

    # Check rapido: se hash corrisponde e collection attiva esiste, salta
    try:
        with _chroma_lock:
            db = chromadb.PersistentClient(path=persist_path)
            active_collection = db.get_or_create_collection(active_name)
            coll_count = active_collection.count()

            _logger.info("Hash corrente: %s...", current_hash[:16])
            _logger.info("Hash salvato: %s...", saved_hash[:16] if saved_hash else 'None')
            _logger.info("Collection attiva '%s': %d documenti", active_name, coll_count)

            # Embedding dimension check: se il modello embedding è cambiato,
            # la dimensione dei vettori non corrisponde → forza reindex
            embed_dim_ok = True
            if coll_count > 0 and current_hash == saved_hash:
                try:
                    expected_dim = _get_embed_dim()
                    # Prende il primo vettore per vedere la dimensione corrente
                    peek = active_collection.get(limit=1, include=["embeddings"])
                    if peek and peek.get("embeddings") and len(peek["embeddings"]) > 0:
                        existing_dim = len(peek["embeddings"][0])
                        if existing_dim != expected_dim:
                            _logger.info(
                                "Dimensione embedding cambiata: %d → %d, reindex necessario",
                                existing_dim, expected_dim,
                            )
                            embed_dim_ok = False
                except Exception as dim_err:
                    _logger.debug("Check dimensione embedding fallito: %s", dim_err)

            if coll_count > 0 and current_hash == saved_hash and embed_dim_ok:
                _logger.info("Cache valida: %d documenti già indicizzati", coll_count)
                vector_store = ChromaVectorStore(chroma_collection=active_collection)
                storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
                return VectorStoreIndex.from_vector_store(
                    vector_store,
                    storage_context=storage_ctx,
                )
            else:
                reason = "hash diverso" if current_hash != saved_hash else "collection vuota"
                if not embed_dim_ok:
                    reason = "dimensione embedding cambiata"
                _logger.info("Cache non valida: %s, procedo con indicizzazione su staging", reason)
    except Exception as e:
        _logger.warning("Check cache fallito, procedo con indicizzazione su staging: %s", e)

    _logger.info("Lettura documenti...")

    try:
        docs = SimpleDirectoryReader(
            modulo_path,
            required_exts=[".txt", ".pdf", ".docx"],
            # Ignora file non di testo (immagini, ecc.)
            exclude=["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp"],
        ).load_data()
    except Exception as e:
        _logger.error("Errore lettura documenti: %s", e)
        return None

    if not docs:
        _logger.error("Nessun documento leggibile trovato.")
        return None

    # Filtra documenti vuoti (es. PDF scansionati senza testo estraibile)
    docs = [d for d in docs if d.text and d.text.strip()]
    if not docs:
        _logger.error("Nessun documento con testo estraibile trovato.")
        return None

    _logger.info("Indicizzazione con parsing adattativo (Markdown + SentenceSplitter) — %d file...", len(docs))

    # Blue-Green: determina il nome staging (quello NON attivo)
    staging_name = _get_staging_coll_name(active_name, base_name)
    _logger.info("Blue-Green: active='%s', staging='%s'", active_name, staging_name)

    # FASE 2: Scrive su collection staging — se fallisce, l'attiva resta intatta
    try:
        with _chroma_lock:
            db = chromadb.PersistentClient(path=persist_path)

            # Cancella la collection staging se esiste (da indicizzazione precedente fallita)
            try:
                db.delete_collection(staging_name)
                _logger.info("Cancellata vecchia staging '%s'", staging_name)
            except Exception as ex:
                ex_str = str(ex).lower()
                if "not found" not in ex_str and "does not exist" not in ex_str:
                    _logger.warning("delete_collection staging fallito: %s", ex)

            # Crea nuova collection staging
            staging_collection = db.get_or_create_collection(staging_name)
            vector_store = ChromaVectorStore(chroma_collection=staging_collection)
            storage_ctx = StorageContext.from_defaults(vector_store=vector_store)

            # Indicizza su staging con parser specifico per estensione
            markdown_parser = MarkdownNodeParser()
            pdf_docx_parser = SentenceSplitter(chunk_size=768, chunk_overlap=128)
            nodes = []
            for doc in docs:
                file_name = doc.metadata.get("file_name", "").lower()
                if file_name.endswith(".pdf") or file_name.endswith(".docx"):
                    _logger.info("Parsing PDF/DOCX con SentenceSplitter (768/128): %s", file_name)
                    doc_nodes = pdf_docx_parser.get_nodes_from_documents([doc])
                else:
                    _logger.info("Parsing Markdown/Text con MarkdownNodeParser: %s", file_name)
                    doc_nodes = markdown_parser.get_nodes_from_documents([doc])
                nodes.extend(doc_nodes)

            # Filtra nodi vuoti o che contengono solo dati binari/immagini
            _len_before = len(nodes)
            nodes = [
                n for n in nodes
                if _node_has_text(n)
            ]
            _dropped = _len_before - len(nodes)
            if _dropped:
                _logger.info("Nodi droppati (vuoti/immagini): %d → rimasti %d", _dropped, len(nodes))

            index = VectorStoreIndex(
                nodes,
                storage_context=storage_ctx,
            )

            # Indicizzazione completata: flipa il pointer active -> staging
            set_active_coll_name(modulo, staging_name, chroma_dir=base_chroma_path)
            _logger.info("Blue-Green: pointer flippato da '%s' a '%s'", active_name, staging_name)

    except Exception as e:
        _logger.error("get_index: errore generazione embeddings per %s (docs=%d): %s",
                      modulo, len(docs), e, exc_info=True)
        _logger.info("Blue-Green: indicizzazione fallita, collection attiva '%s' rimane intatta", active_name)
        return None

    # FASE 3: Save hash - lock separato breve
    with _chroma_lock:
        save_hash(hash_file, modulo, current_hash)

    _logger.info("Indicizzazione %s completata su '%s'", modulo, staging_name)
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


class HybridRetriever:
    """Combines KG exact lookup (by formula ID or name) with vector search.
    Priority: KG nodes appear first, then vector results (deduplicated)."""

    def __init__(self, vector_retriever, kg=None):
        self.vector_retriever = vector_retriever
        self._kg = kg

    def _get_kg(self):
        if self._kg is None:
            from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph
            self._kg = KnowledgeGraph()
        return self._kg

    def _parse_formula_ids(self, query):
        ids = set()
        for m in re.finditer(r"formula\s+(\d{1,4})", query, re.IGNORECASE):
            ids.add(int(m.group(1)))
        for m in re.finditer(r"(?:^|\s)(\d{2,4})(?:\s|$|[?.!,])", query):
            ids.add(int(m.group(1)))
        return ids

    def _parse_formula_names(self, query):
        name_map = {
            "principale": 120,
            "prima formula": 100,
            "straordinario festivo": 130,
            "straordinario diurno": 140,
            "formula finale": 200,
        }
        # Arricchisci con alias dal glossario semantico (formule correlate ai concetti)
        try:
            from legacy_winsarp.core.winsarp.glossary import CONCEPT_TO_FORMULA
            for concept, mapping in CONCEPT_TO_FORMULA.items():
                for fid in mapping.get("formulas", []):
                    name_map.setdefault(concept, fid)
            from legacy_winsarp.core.winsarp.glossary import SCENARIO_FLOWS
            for scen in SCENARIO_FLOWS.values():
                for flow in scen.get("flows", []):
                    for fid in flow.get("formulas", []):
                        name_map.setdefault(scen["description"].split()[0].lower(), fid)
        except Exception:
            pass
        q_lower = query.lower()
        return [(n, fid) for n, fid in name_map.items() if n in q_lower]

    def _kg_node_to_text(self, node):
        lines = [
            f"### Formula {node['id']} - {node['name']}",
            f"**Tipo:** {node.get('tipo', 'N/A')}",
            f"**Categoria:** {node.get('tipo_cat', 'N/A')}",
        ]
        if node.get("scopo"):
            lines.append(f"**Scopo:** {node['scopo']}")
        if node.get("code"):
            lines.append(f"**Codice:** `{node['code']}`")
        if node.get("all_calls"):
            lines.append(f"**Chiama:** {', '.join(str(c) for c in node['all_calls'])}")
        if node.get("called_by"):
            lines.append(f"**Chiamata da:** {', '.join(str(c) for c in node['called_by'])}")
        return "\n".join(lines)

    def retrieve(self, query_or_bundle):
        query = getattr(query_or_bundle, "query_str", str(query_or_bundle))
        kg = self._get_kg()
        hybrid_nodes = []

        for fid in self._parse_formula_ids(query):
            node = kg.get_formula(fid)
            if node:
                text = self._kg_node_to_text(node)
                tn = TextNode(text=text, id_=f"kg_{fid}", metadata={"source": "kg", "formula_id": fid})
                hybrid_nodes.append(NodeWithScore(node=tn, score=1.0))

        for name, fid in self._parse_formula_names(query):
            if not any(getattr(n.node, "metadata", {}).get("formula_id") == fid for n in hybrid_nodes):
                node = kg.get_formula(fid)
                if node:
                    text = self._kg_node_to_text(node)
                    tn = TextNode(text=text, id_=f"kg_{fid}", metadata={"source": "kg", "formula_id": fid})
                    hybrid_nodes.append(NodeWithScore(node=tn, score=0.95))

        try:
            vector_nodes = self.vector_retriever.retrieve(query_or_bundle)
        except Exception:
            vector_nodes = []

        seen = {n.node.id_ for n in hybrid_nodes}
        max_total = len(hybrid_nodes) + 4
        result = list(hybrid_nodes)
        for vn in vector_nodes:
            if vn.node.id_ not in seen:
                result.append(vn)
                seen.add(vn.node.id_)
            if len(result) >= max_total:
                break

        return result


# ============================================================
# CUSTOM CHAT ENGINE — sostituisce CondensePlusContextChatEngine
# ============================================================
# Il CondensePlusContextChatEngine di LlamaIndex usa CompactAndRefine
# che causa "Empty Response" con qwen3.5:4b su CPU quando il contesto
# supera ~10K caratteri. Questa implementazione chiama llm.chat()
# direttamente con contesto limitato.

MAX_CONTEXT_CHARS = 6000  # limite sicuro per qwen3.5:4b con num_ctx=16384


def _condense_question(message: str, memory, llm) -> str:
    """Condensa la domanda con la cronologia in una domanda autonoma."""
    chat_history = memory.get()
    if not chat_history:
        return message

    history_lines = []
    for m in chat_history[-6:]:
        role = "Utente" if m.role == MessageRole.USER else "Assistente"
        history_lines.append(f"{role}: {m.content}")
    history_text = "\n".join(history_lines)

    condense_prompt = (
        "Given the following conversation and a follow up question, "
        "rephrase the follow up question to be a standalone question."
    )
    condense_messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=condense_prompt),
        ChatMessage(
            role=MessageRole.USER,
            content=(
                f"Chat history:\n{history_text}\n\n"
                f"Follow up question: {message}\n\n"
                f"Standalone question:"
            ),
        ),
    ]
    try:
        resp = llm.chat(condense_messages)
        condensed = resp.message.content.strip()
        return condensed if condensed else message
    except Exception:
        return message


def _build_context(nodes, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Costruisce il contesto dai nodi, limitando la dimensione totale."""
    parts = []
    total = 0
    for n in nodes:
        text = n.node.get_text()
        if total + len(text) > max_chars:
            allowed = max_chars - total
            if allowed > 200:
                parts.append(text[:allowed])
            break
        parts.append(text)
        total += len(text)
    return "\n\n".join(parts)


class CustomChatEngine:
    """Chat engine custom che chiama llm.chat() direttamente.

    Supporta chat() e stream_chat() con la stessa interfaccia
    di CondensePlusContextChatEngine ma senza il synthesizer
    CompactAndRefine che causa "Empty Response".
    """

    def __init__(
        self,
        retriever,
        llm,
        memory,
        system_prompt: str,
    ):
        self.retriever = retriever
        self.llm = llm
        self.memory = memory
        self.system_prompt = system_prompt.strip()

    def _build_messages(self, message: str, context: str):
        from config import cfg as _cfg
        pii_enabled = getattr(_cfg, "PII_FILTER_ENABLED", True)
        safe_context = context
        safe_message = message
        if pii_enabled:
            try:
                from core.pii_filter import filter_pii
                safe_context = filter_pii(context, enabled=True)
                safe_message = filter_pii(message, enabled=True)
            except Exception:
                pass
        system_content = (
            "Context information is below.\n"
            "---------------------\n"
            f"{safe_context}\n"
            "---------------------\n"
            f"{self.system_prompt}"
        )
        self._pii_message = safe_message
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_content),
        ]
        for m in self.memory.get():
            messages.append(m)
        messages.append(ChatMessage(role=MessageRole.USER, content=self._pii_message))
        return messages

    def chat(self, message: str, chat_history=None):
        from llama_index.core.chat_engine.types import AgentChatResponse

        condensed = _condense_question(message, self.memory, self.llm)
        nodes = self.retriever.retrieve(condensed)
        context = _build_context(nodes, MAX_CONTEXT_CHARS)

        messages = self._build_messages(message, context)
        resp = self.llm.chat(messages)
        answer = resp.message.content or ""

        if not answer.strip():
            answer = "Non ho trovato informazioni sufficienti per rispondere."

        self.memory.put(ChatMessage(role=MessageRole.USER, content=self._pii_message))
        self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=answer))

        return AgentChatResponse(response=answer)

    def stream_chat(self, message: str, chat_history=None):
        from llama_index.core.chat_engine.types import StreamingAgentChatResponse
        from llama_index.core.base.llms.types import ChatResponse

        condensed = _condense_question(message, self.memory, self.llm)
        nodes = self.retriever.retrieve(condensed)
        context = _build_context(nodes, MAX_CONTEXT_CHARS)

        messages = self._build_messages(message, context)
        streaming_resp = self.llm.stream_chat(messages)

        def gen():
            full = ""
            for resp in streaming_resp:
                delta = resp.delta or ""
                full += delta
                yield ChatResponse(
                    delta=delta,
                    message=ChatMessage(content=full, role=MessageRole.ASSISTANT),
                )
            if not full.strip():
                fallback = "Non ho trovato informazioni sufficienti per rispondere."
                yield ChatResponse(
                    delta=fallback,
                    message=ChatMessage(content=fallback, role=MessageRole.ASSISTANT),
                )
                full = fallback
            self.memory.put(ChatMessage(role=MessageRole.USER, content=self._pii_message))
            self.memory.put(ChatMessage(role=MessageRole.ASSISTANT, content=full))

        return StreamingAgentChatResponse(chat_stream=gen())


def build_chat_engine(modulo: str, model_id: str, index, use_generation_prompt: bool = False, formula_only: bool = False, modules: dict | None = None):
    """
    Costruisce il chat engine con memoria e system prompt.
    Usa CustomChatEngine invece di CondensePlusContextChatEngine
    per evitare il bug "Empty Response" con qwen3.5:4b su CPU.

    Args:
        modulo: Nome del modulo
        model_id: ID del modello LLM
        index: Indice vettoriale
        use_generation_prompt: Se True, usa prompt di generazione invece di retrieval
        formula_only: Se True (WinSarp), aggiunge istruzioni per rispondere solo con la formula
        modules: Dict opzionale di moduli per risolvere il prompt
    """
    mcfg = get_module_config(modulo)
    system_prompt = _resolve_prompt(modulo, use_generation_prompt, formula_only, modules=modules)

    llm = get_llm(modulo, model_id)
    memory = ChatMemoryBuffer.from_defaults(
        token_limit=mcfg["chat_history"] * 600
    )

    vector_retriever = index.as_retriever(similarity_top_k=mcfg["top_k"])
    retriever = HybridRetriever(vector_retriever)

    return CustomChatEngine(
        retriever=retriever,
        llm=llm,
        memory=memory,
        system_prompt=system_prompt,
    )


# ============================================================
# RECUPERO CONTESTO RAG (chunk usati + score)
# ============================================================
def get_source_nodes(modulo: str, model_id: str, index,
                     query: str) -> list[dict]:
    """
    Esegue una query di retrieval puro sull'indice e restituisce
    i chunk usati con il loro score di similarita'.
    Usa HybridRetriever per cercare prima nel KG, poi vettorialmente.
    """
    _ = model_id
    mcfg = get_module_config(modulo)
    vector_retriever = index.as_retriever(similarity_top_k=mcfg["top_k"])
    retriever = HybridRetriever(vector_retriever)
    try:
        nodes = retriever.retrieve(QueryBundle(query))
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
