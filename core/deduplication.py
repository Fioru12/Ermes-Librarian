"""
core/deduplication.py
Enterprise Document Deduplication and Near-Duplicate Detection Engine.
Identifies identical content, near-duplicate documents, and obsolete revisions across libraries.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


def _normalize_for_hashing(text: str) -> str:
    """Normalizza il testo eliminando spazi multipli e punteggiatura non significativa."""
    return re.sub(r"\s+", " ", re.sub(r"[^\wÀ-ÿ\s]", "", text.lower())).strip()


def compute_content_fingerprint(text: str) -> str:
    """Genera un'impronta hash SHA-256 del contenuto testuale normalizzato."""
    norm = _normalize_for_hashing(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def compute_shingle_set(text: str, k: int = 3) -> set[str]:
    """Estrae unigrammi e k-shingle di parole per calcolo di somiglianza Jaccard."""
    words = _normalize_for_hashing(text).split()
    if not words:
        return set()
    shingles = set(words)
    if len(words) >= k:
        for i in range(len(words) - k + 1):
            shingles.add(" ".join(words[i : i + k]))
    return shingles


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calcola l'indice di somiglianza di Jaccard tra due insiemi di shingle."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return (intersection / union) if union > 0 else 0.0


def find_library_duplicates(
    documents: list[dict[str, Any]],
    similarity_threshold: float = 0.85,
) -> list[dict[str, Any]]:
    """
    Analizza i documenti di una biblioteca e raggruppa i duplicati esatti o parziali.
    Restituisce una lista di gruppi di duplicati con punteggio di confidenza.
    """
    if len(documents) < 2:
        return []

    # 1. Raggruppamento per hash esatto
    fingerprints: dict[str, list[dict[str, Any]]] = {}
    doc_shingles: dict[str, set[str]] = {}

    for doc in documents:
        text = doc.get("text") or doc.get("content_preview") or ""
        fp = compute_content_fingerprint(text)
        fingerprints.setdefault(fp, []).append(doc)
        doc_shingles[doc["id"]] = compute_shingle_set(text)

    duplicate_groups: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Gruppi di duplicati esatti
    for fp, docs in fingerprints.items():
        if len(docs) > 1:
            duplicate_groups.append({
                "type": "exact",
                "similarity": 1.0,
                "document_ids": [d["id"] for d in docs],
                "filenames": [d.get("filename", "") for d in docs],
                "recommendation": "Contenuto identico. Si consiglia di archiviare le versioni precedenti.",
            })
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    seen_pairs.add((docs[i]["id"], docs[j]["id"]))
                    seen_pairs.add((docs[j]["id"], docs[i]["id"]))

    # 2. Controllo near-duplicates con Jaccard su shingle
    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            doc_a = documents[i]
            doc_b = documents[j]
            pair = (doc_a["id"], doc_b["id"])
            if pair in seen_pairs:
                continue

            shingles_a = doc_shingles.get(doc_a["id"], set())
            shingles_b = doc_shingles.get(doc_b["id"], set())
            sim = jaccard_similarity(shingles_a, shingles_b)

            if sim >= similarity_threshold:
                duplicate_groups.append({
                    "type": "near_duplicate",
                    "similarity": round(sim, 2),
                    "document_ids": [doc_a["id"], doc_b["id"]],
                    "filenames": [doc_a.get("filename", ""), doc_b.get("filename", "")],
                    "recommendation": f"Contenuto quasi identico ({int(sim * 100)}% somiglianza). Verificare se si tratta di una revisione.",
                })
                seen_pairs.add(pair)
                seen_pairs.add((doc_b["id"], doc_a["id"]))

    return duplicate_groups
