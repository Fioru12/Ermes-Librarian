"""
tests/test_deduplication.py
Unit tests for core/deduplication.py (Document Fingerprinting and Deduplication Engine).
"""
from __future__ import annotations

import pytest
from core.deduplication import (
    compute_content_fingerprint,
    compute_shingle_set,
    jaccard_similarity,
    find_library_duplicates,
)


def test_compute_content_fingerprint_normalized():
    text1 = "Questo è un documento di prova!!!"
    text2 = "questo è un documento di prova"
    # L'hash normalizzato dovrebbe ignorare maiuscole e punteggiatura
    assert compute_content_fingerprint(text1) == compute_content_fingerprint(text2)


def test_jaccard_similarity_identical_and_different():
    s1 = compute_shingle_set("procedura aziendale per richiesta ferie")
    s2 = compute_shingle_set("procedura aziendale per richiesta ferie")
    s3 = compute_shingle_set("configurazione server database mysql")

    assert jaccard_similarity(s1, s2) == 1.0
    assert jaccard_similarity(s1, s3) < 0.2


def test_find_library_duplicates_exact_and_near():
    docs = [
        {
            "id": "doc1",
            "filename": "policy_v1.txt",
            "text": "La pausa pranzo ha una durata massima di 60 minuti secondo il regolamento.",
        },
        {
            "id": "doc2",
            "filename": "policy_v1_copy.txt",
            "text": "La pausa pranzo ha una durata massima di 60 minuti secondo il regolamento.",
        },
        {
            "id": "doc3",
            "filename": "policy_v2.txt",
            "text": "La pausa pranzo ha una durata massima di 60 minuti secondo il regolamento aziendale aggiornato.",
        },
        {
            "id": "doc4",
            "filename": "server_config.txt",
            "text": "Indirizzo IP del server DNS 192.168.1.1 e porta 53.",
        },
    ]

    duplicates = find_library_duplicates(docs, similarity_threshold=0.6)
    assert len(duplicates) >= 1

    exact_group = [g for g in duplicates if g["type"] == "exact"]
    assert len(exact_group) == 1
    assert "doc1" in exact_group[0]["document_ids"]
    assert "doc2" in exact_group[0]["document_ids"]
