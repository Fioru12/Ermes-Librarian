import contextlib
import json
import logging
import re
import time
from datetime import datetime

import chromadb
import httpx

from config import cfg

_logger = logging.getLogger(__name__)

_MEMORY_COLLECTION_PREFIX = "ermes_mem_"
_VERIFY_MODEL = "qwen2.5-coder:7b"
_AUTO_MATCH_THRESHOLD = 0.85
_HIGH_CONFIDENCE_THRESHOLD = 0.80
_SKIP_LLM_THRESHOLD = 0.50

_VERIFY_PROMPT = (
    "Nuova domanda: \"{new_query}\"\n"
    "Domande precedenti:\n{candidates}\n"
    "Quale chiede la STESSA cosa? Ignora sinonimi e errori.\n"
    "Rispondi SOLO 1-{n} o NONE.\n"
    "Risposta:"
)

_CANDIDATE_LINE = '{i}. "{query}"'


class MemoryManager:
    def __init__(self):
        self._client: chromadb.PersistentClient | None = None
        self._collections: dict[str, chromadb.Collection] = {}

    def _get_client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(path=cfg.CHROMA_DIR)
        return self._client

    def _coll_name(self, module: str) -> str:
        safe = re.sub(r'[^a-zA-Z0-9]', '', module.lower())
        return f"{_MEMORY_COLLECTION_PREFIX}{safe}"

    def _get_collection(self, module: str) -> chromadb.Collection:
        name = self._coll_name(module)
        if name not in self._collections:
            client = self._get_client()
            try:
                self._collections[name] = client.get_collection(name)
            except Exception:
                self._collections[name] = client.create_collection(
                    name, metadata={"hnsw:space": "cosine"}
                )
        return self._collections[name]

    def remember(self, query: str, answer: str, module: str, model_id: str,
                 sources: list | None = None, rating: int = 0) -> None:
        coll = self._get_collection(module)
        doc_id = f"mem_{hash(query)}_{time.time_ns()}"
        searchable_text = query
        metadata = {
            "module": module,
            "model_id": model_id,
            "stored_answer": answer,
            "rating": rating,
            "timestamp": datetime.now().isoformat(),
            "sources": json.dumps(sources or []),
            "query_full": query,
        }
        try:
            coll.add(documents=[searchable_text], metadatas=[metadata], ids=[doc_id])
        except Exception as e:
            _logger.warning("Memory remember fallita: %s", e)

    def recall(self, query: str, module: str) -> dict | None:
        coll = self._get_collection(module)
        try:
            count = coll.count()
            if count == 0:
                return None
        except Exception:
            return None

        n_candidates = min(count, 5)
        try:
            results = coll.query(query_texts=[query], n_results=n_candidates)
        except Exception as e:
            _logger.warning("Memory recall query fallita: %s", e)
            return None

        if not results or not results.get("ids") or not results["ids"][0]:
            return None

        ids = results["ids"][0]
        distances = results.get("distances", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        valid = []
        for i in range(len(ids)):
            meta = metadatas[i] if i < len(metadatas) else {}
            if meta and meta.get("rating", 0) < 0:
                continue
            doc_text = documents[i] if i < len(documents) else ""
            first_line = meta.get("query_full", doc_text.split("\n")[0].strip()) if meta else doc_text.split("\n")[0].strip()
            valid.append({
                "idx": i,
                "first_line": first_line,
                "doc": doc_text,
                "meta": meta,
                "score": 1.0 - distances[i],
            })

        if not valid:
            return None

        best_score = valid[0]["score"]
        if best_score >= _AUTO_MATCH_THRESHOLD:
            chosen_idx = 0
        elif best_score >= _HIGH_CONFIDENCE_THRESHOLD:
            chosen_idx = _fast_keyword_match(query, valid)
        elif best_score < _SKIP_LLM_THRESHOLD:
            return None
        else:
            chosen_idx = _fast_keyword_match(query, valid)
            if chosen_idx is None:
                chosen_idx = _verify_batch_with_llm(query, valid)

        if chosen_idx is None:
            return None

        chosen = valid[chosen_idx]
        meta = chosen["meta"]
        sources_raw = meta.get("sources", "[]")
        try:
            sources = json.loads(sources_raw) if isinstance(sources_raw, str) else sources_raw
        except (json.JSONDecodeError, TypeError):
            sources = []

        return {
            "answer": meta.get("stored_answer", ""),
            "model_id": meta.get("model_id", ""),
            "timestamp": meta.get("timestamp", ""),
            "rating": meta.get("rating", 0),
            "score": round(chosen["score"], 3),
            "sources": sources,
        }

    def rate(self, query: str, module: str, rating: int) -> None:
        coll = self._get_collection(module)
        try:
            results = coll.query(query_texts=[query], n_results=1)
            if results and results.get("ids") and results["ids"][0]:
                doc_id = results["ids"][0][0]
                meta = results["metadatas"][0][0] if results.get("metadatas") else {}
                meta["rating"] = rating
                coll.update(ids=[doc_id], metadatas=[meta])
        except Exception as e:
            _logger.warning("Memory rate fallita: %s", e)

    def clear(self, module: str) -> None:
        name = self._coll_name(module)
        with contextlib.suppress(Exception):
            self._get_client().delete_collection(name)
        self._collections.pop(name, None)

    def clear_all(self) -> None:
        client = self._get_client()
        for name in list(self._collections.keys()):
            with contextlib.suppress(Exception):
                client.delete_collection(name)
        self._collections.clear()

    def get_stats(self, module: str) -> dict:
        coll = self._get_collection(module)
        try:
            count = coll.count()
        except Exception:
            count = 0
        ratings = []
        if count > 0:
            try:
                all_data = coll.get()
                for meta in (all_data.get("metadatas") or []):
                    if meta and "rating" in meta:
                        ratings.append(meta["rating"])
            except Exception:
                pass
        avg = sum(ratings) / len(ratings) if ratings else 0.0
        return {"count": count, "avg_rating": round(avg, 2), "rated": len(ratings)}


_memory_manager: MemoryManager | None = None


def _get_manager() -> MemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def recall(query: str, module: str) -> dict | None:
    return _get_manager().recall(query, module)


def remember(query: str, answer: str, module: str, model_id: str,
             sources: list | None = None, rating: int = 0) -> None:
    _get_manager().remember(query, answer, module, model_id, sources, rating)


def clear_module_memory(module: str) -> None:
    _get_manager().clear(module)


def clear_all_memory() -> None:
    from chromadb import PersistentClient
    client = PersistentClient(path=cfg.CHROMA_DIR)
    for c in client.list_collections():
        if c.name.startswith(_MEMORY_COLLECTION_PREFIX):
            with contextlib.suppress(Exception):
                client.delete_collection(c.name)
    _get_manager()._collections.clear()


def memory_stats(module: str) -> dict:
    return _get_manager().get_stats(module)


def _fast_keyword_match(query_new: str, candidates: list[dict]) -> int | None:
    nq = query_new.lower()
    nq_tokens = set(re.findall(r'[a-z0-9]+', nq))
    if not nq_tokens:
        return None
    best_idx = None
    best_overlap = 0.0
    for i, c in enumerate(candidates):
        c_text = c.get("doc", "").lower()
        c_tokens = set(re.findall(r'[a-z0-9]+', c_text))
        if not c_tokens:
            continue
        overlap = len(nq_tokens & c_tokens) / len(nq_tokens | c_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = i
    if best_overlap >= 0.50:
        return best_idx
    return None


def _verify_batch_with_llm(query_new: str, candidates: list[dict],
                           timeout_s: int = 15) -> int | None:
    n = len(candidates)
    lines = "\n".join(_CANDIDATE_LINE.format(i=i + 1, query=c["first_line"])
                      for i, c in enumerate(candidates))
    prompt = _VERIFY_PROMPT.format(n=n, new_query=query_new, candidates=lines)
    url = _ollama_url() + "/api/generate"
    payload = {
        "model": _VERIFY_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 10, "temperature": 0.0},
    }
    try:
        resp = httpx.post(url, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip().upper()
        text = re.sub(r'^[^0-9N]+', '', text)  # remove leading garbage
        if text.startswith("NONE") or not text:
            return None
        m = re.search(r'(\d+)', text)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < n:
                return idx
        return None
    except Exception as e:
        _logger.debug("LLM batch verify fallita (non bloccante): %s", e)
        return None


def _ollama_url() -> str:
    base = getattr(cfg, "OLLAMA_BASE_URL", None) or "http://127.0.0.1:11434"
    return base.strip().rstrip("/")
