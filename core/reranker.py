"""
reranker.py
Enterprise Reranking Engine per Ermes Knowledge.
Ri-ordina i passaggi recuperati (ibridi FTS5 + Vettori) calcolando un punteggio
di rilevanza contestuale multi-fattoriale per massimizzare la precisione e
ridurre allucinazioni.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from typing import Any

from config import cfg

logger = logging.getLogger(__name__)

# Stopwords base per non sovrastimare parole vuote
_STOPWORDS = {
    "a", "ad", "al", "alla", "alle", "che", "chi", "come", "con", "cosa", "dei", "del", "della", "delle",
    "di", "dove", "e", "gli", "i", "il", "in", "la", "le", "lo", "nei", "nelle", "per", "quali", "quando",
    "quale", "sono", "sul", "sulla", "the", "and", "are", "for", "from", "how", "is", "it",
    "of", "on", "or", "to", "what", "when", "where", "who", "why", "with",
}


def _tokenize(text: str) -> list[str]:
    return [
        w.lower() for w in re.findall(r"[\wÀ-ÿ]+", text)
        if len(w) >= 2 and w.lower() not in _STOPWORDS
    ]


def calculate_rerank_score(
    query: str,
    filename: str,
    excerpt: str,
    base_score: float = 0.0,
) -> float:
    """
    Calcola uno score di rilevanza compreso tra 0.0 e 1.0 basato su:
    1. Exact phrase matching
    2. Token overlap & IDF weighting
    3. Positional proximity (distanza tra i termini della query nel testo)
    4. Filename relevance bonus
    5. Integrazione con lo score base (vettoriale/ibrido)
    """
    normalized_query = query.strip().lower()
    if not normalized_query or not excerpt:
        return 0.0

    normalized_excerpt = excerpt.strip().lower()
    normalized_filename = filename.strip().lower()

    score = 0.0
    query_tokens = _tokenize(normalized_query)
    if not query_tokens:
        return min(1.0, max(0.0, base_score / 100.0))

    # 1. Exact phrase match (peso elevato)
    if normalized_query in normalized_excerpt:
        score += 0.40
    elif len(query_tokens) > 1:
        # Check per bi-grammi consecutivi
        bigrams = [f"{query_tokens[i]} {query_tokens[i+1]}" for i in range(len(query_tokens) - 1)]
        matched_bigrams = sum(1 for bg in bigrams if bg in normalized_excerpt)
        if matched_bigrams > 0:
            score += 0.20 * (matched_bigrams / len(bigrams))

    # 2. Token overlap & density
    excerpt_tokens = _tokenize(normalized_excerpt)
    excerpt_set = set(excerpt_tokens)
    matched_tokens = [t for t in query_tokens if t in excerpt_set]
    overlap_ratio = len(matched_tokens) / len(query_tokens)
    score += 0.30 * overlap_ratio

    # 3. Positional proximity dei termini
    if len(matched_tokens) >= 2:
        positions: list[int] = []
        for token in matched_tokens:
            try:
                pos = normalized_excerpt.index(token)
                positions.append(pos)
            except ValueError:
                pass
        if len(positions) >= 2:
            span = max(positions) - min(positions)
            # Minore è la distanza, maggiore è la coesione del passaggio
            proximity_score = max(0.0, 1.0 - (span / max(len(normalized_excerpt), 1)))
            score += 0.15 * proximity_score

    # 4. Filename bonus
    if any(t in normalized_filename for t in query_tokens):
        score += 0.10

    # 5. Base score contribution (se presente)
    if base_score > 0:
        norm_base = min(1.0, base_score / 100.0)
        score = (score * 0.75) + (norm_base * 0.25)

    return min(1.0, max(0.0, round(score, 4)))


# ============================================================
# RERANKER NEURALE (cross-encoder)
# ============================================================
# Un cross-encoder valuta (query, passaggio) insieme, quindi capta
# rilevanza semantica che il matching lessicale non vede (sinonimi,
# riformulazioni). È costoso: va usato solo sui candidati già
# pre-selezionati dalla ricerca ibrida, mai su tutto l'archivio.

_NEURAL_MODEL: Any | None = None
_NEURAL_MODEL_TRIED = False
_NEURAL_LOCK = threading.Lock()

# Pesi del blend: il cross-encoder è più preciso ma può andare fuori scala
# su query fuori dominio, il lessicale è più stabile. 60/40.
NEURAL_WEIGHT = 0.60
LEXICAL_WEIGHT = 0.40


def _load_neural_model() -> Any | None:
    """Carica lazy il cross-encoder una sola volta per processo.

    Ritorna None se sentence-transformers non è installato, il modello non
    è scaricabile o ERMES_RERANKER_NEURAL=0. Un fallimento non viene
    ritentato (evita retry storm a ogni query): si ripiega sul lessicale.
    """
    global _NEURAL_MODEL, _NEURAL_MODEL_TRIED
    if _NEURAL_MODEL_TRIED:
        return _NEURAL_MODEL
    with _NEURAL_LOCK:
        if _NEURAL_MODEL_TRIED:
            return _NEURAL_MODEL
        _NEURAL_MODEL_TRIED = True
        if not getattr(cfg, "RERANKER_NEURAL_ENABLED", True):
            logger.info("Reranker neurale disattivato da configurazione")
            return None
        try:
            from sentence_transformers import CrossEncoder  # dipendenza opzionale

            model_name = cfg.RERANKER_MODEL
            _NEURAL_MODEL = CrossEncoder(model_name, max_length=512)
            logger.info("Reranker neurale attivo: %s", model_name)
        except ImportError:
            logger.info(
                "sentence-transformers non installato: reranker lessicale in uso. "
                "Installare con `pip install .[neural]` per il cross-encoder."
            )
        except Exception as error:  # modello non scaricabile / OOM / ecc.
            logger.warning("Cross-encoder %s non disponibile (%s): fallback lessicale", cfg.RERANKER_MODEL, error)
        return _NEURAL_MODEL


def reset_neural_model() -> None:
    """Ripristina lo stato lazy (usato dai test e dopo re-configurazione)."""
    global _NEURAL_MODEL, _NEURAL_MODEL_TRIED
    with _NEURAL_LOCK:
        _NEURAL_MODEL = None
        _NEURAL_MODEL_TRIED = False


def _neural_scores(query: str, excerpts: list[str]) -> list[float] | None:
    """Score di rilevanza 0..1 per ogni (query, excerpt), o None se non neurale."""
    model = _load_neural_model()
    if model is None or not excerpts:
        return None
    try:
        raw = model.predict([(query, text) for text in excerpts])
    except Exception as error:
        logger.warning("Inferenza cross-encoder fallita (%s): fallback lessicale", error)
        return None
    # CrossEncoder restituisce logits: la sigmoid li porta in 0..1.
    return [float(1.0 / (1.0 + math.exp(-float(value)))) for value in raw]


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    min_score: float | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Applica il reranker alla lista di chunk candidati.
    Ogni dict deve contenere 'excerpt' e opzionalmente 'filename' e 'relevance_score'.
    """
    if not candidates or not query:
        return candidates[:limit]

    effective_min_score = min_score if min_score is not None else cfg.RERANKER_MIN_SCORE

    # Score lessicali prima (servono comunque nel blend e nel fallback).
    lexical: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        filename = item.get("filename") or item.get("citation", {}).get("filename", "")
        score = calculate_rerank_score(
            query=query,
            filename=filename,
            excerpt=item.get("excerpt", ""),
            base_score=float(item.get("relevance_score", 0.0)),
        )
        lexical.append((score, item))

    # Se il cross-encoder è disponibile, aggiunge il suo giudizio semantico.
    neural = _neural_scores(query, [item.get("excerpt", "") for _, item in lexical])
    mode = "neural" if neural is not None else "lexical"

    reranked: list[tuple[float, dict[str, Any]]] = []
    for index, (lex_score, item) in enumerate(lexical):
        if neural is not None:
            final_score = (NEURAL_WEIGHT * neural[index]) + (LEXICAL_WEIGHT * lex_score)
        else:
            final_score = lex_score
        item_copy = dict(item)
        item_copy["rerank_score"] = round(final_score, 4)
        if neural is not None:
            item_copy["neural_score"] = round(neural[index], 4)
        # Aggiorna relevance_score per coerenza verso l'esterno
        item_copy["relevance_score"] = item_copy["rerank_score"]
        reranked.append((final_score, item_copy))

    # Ordina per rerank_score decrescente
    reranked.sort(key=lambda x: -x[0])

    # Filtra per min_score se sono rimasti elementi validi
    filtered = [item for score, item in reranked if score >= effective_min_score]

    # Se il filtro rimuove tutto ma avevamo candidati, restituisce almeno il migliore
    if not filtered and reranked:
        filtered = [reranked[0][1]]

    results = filtered[:limit]
    # Profilazione: il chiamante può loggare quale modalità ha usato.
    for item in results:
        item.setdefault("rerank_mode", mode)
    return results
