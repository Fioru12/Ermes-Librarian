"""Optional local embeddings for the library retrieval path.

The module deliberately supports only the configured Ollama endpoint. Failure
is normal in a lightweight install and callers must retain keyword retrieval.
"""
from __future__ import annotations

import math
from typing import Iterable

from config import cfg


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values, right_values = list(left), list(right)
    if len(left_values) != len(right_values) or not left_values:
        return 0.0
    numerator = sum(a * b for a, b in zip(left_values, right_values))
    denominator = math.sqrt(sum(a * a for a in left_values)) * math.sqrt(sum(b * b for b in right_values))
    return numerator / denominator if denominator else 0.0


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a small batch locally, returning [] when semantic mode is unavailable."""
    if not cfg.LIBRARY_SEMANTIC_SEARCH_ENABLED or not texts:
        return []
    try:
        import httpx
    except ImportError:
        return []
    base_url = cfg.OLLAMA_HOST.rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/api/embed", json={"model": cfg.EMBED_MODEL_ID, "input": texts}, timeout=10,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if len(embeddings) == len(texts) and all(isinstance(item, list) for item in embeddings):
            return embeddings
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return []
