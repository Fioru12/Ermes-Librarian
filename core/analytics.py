"""
analytics.py
Enterprise Analytics & Knowledge Gap Tracker per Ermes Librarian.
Traccia latenza, soddisfazione utente (feedback), frequenza query e
rileva automaticamente i "buchi di conoscenza" (Knowledge Gaps).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from config import cfg

_logger = logging.getLogger(__name__)
_ANALYTICS_LOCK = threading.RLock()


def _ensure_dir(filepath: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def record_query_event(
    query: str,
    library_id: str,
    actor: str = "anonymous",
    result_count: int = 0,
    latency_ms: float = 0.0,
    coverage: str = "supported",
    assistant_mode: str = "evidence_only",
    fallback_reason: str | None = None,
) -> str:
    """Registra una transazione di ricerca / chat RAG."""
    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "type": "query",
        "timestamp": _timestamp(),
        "query": query.strip(),
        "library_id": library_id,
        "actor": actor,
        "result_count": result_count,
        "latency_ms": round(latency_ms, 2),
        "coverage": coverage,
        "assistant_mode": assistant_mode,
        "fallback_reason": fallback_reason or "",
    }
    _ensure_dir(cfg.ANALYTICS_FILE)
    try:
        with _ANALYTICS_LOCK, open(cfg.ANALYTICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as e:
        _logger.warning("Impossibile salvare l'evento analytics: %s", e)
    return event_id


def record_feedback(
    event_id: str,
    rating: int,  # 1 = positive, -1 = negative
    comment: str = "",
    actor: str = "anonymous",
) -> bool:
    """Registra feedback dell'utente (thumbs up / thumbs down)."""
    feedback_entry = {
        "event_id": str(uuid.uuid4()),
        "type": "feedback",
        "timestamp": _timestamp(),
        "target_event_id": event_id,
        "rating": 1 if rating > 0 else -1,
        "comment": comment.strip()[:500],
        "actor": actor,
    }
    _ensure_dir(cfg.ANALYTICS_FILE)
    try:
        with _ANALYTICS_LOCK, open(cfg.ANALYTICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")
        return True
    except OSError as e:
        _logger.warning("Impossibile salvare il feedback: %s", e)
        return False


def _read_events(days: int = 30) -> list[dict[str, Any]]:
    if not os.path.exists(cfg.ANALYTICS_FILE):
        return []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    events: list[dict[str, Any]] = []
    try:
        with _ANALYTICS_LOCK, open(cfg.ANALYTICS_FILE, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    ts_str = data.get("timestamp", "")
                    # Riconosce formati ISO UTC con o senza timezone
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=UTC)
                        if ts < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                    events.append(data)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def get_analytics_summary(days: int = 30) -> dict[str, Any]:
    """Genera riepilogo delle metriche per dashboard di governance."""
    events = _read_events(days=days)
    queries = [e for e in events if e.get("type") == "query"]
    feedbacks = [e for e in events if e.get("type") == "feedback"]

    total_queries = len(queries)
    if total_queries == 0:
        return {
            "period_days": days,
            "total_queries": 0,
            "avg_latency_ms": 0.0,
            "knowledge_gaps_count": 0,
            "positive_feedback_rate": 0.0,
            "total_feedback": len(feedbacks),
            "by_coverage": {},
            "top_libraries": [],
        }

    total_latency = sum(q.get("latency_ms", 0.0) for q in queries)
    avg_latency = round(total_latency / total_queries, 2)

    by_coverage: dict[str, int] = defaultdict(int)
    by_library: dict[str, int] = defaultdict(int)
    gap_count = 0

    for q in queries:
        cov = q.get("coverage", "supported")
        by_coverage[cov] += 1
        if cov == "insufficient_evidence" or q.get("result_count", 0) == 0:
            gap_count += 1
        lib_id = q.get("library_id", "unknown")
        by_library[lib_id] += 1

    positive_fb = sum(1 for fb in feedbacks if fb.get("rating", 0) > 0)
    pos_rate = round((positive_fb / len(feedbacks) * 100.0), 1) if feedbacks else 100.0

    top_libraries = sorted(
        [{"library_id": lib, "count": count} for lib, count in by_library.items()],
        key=lambda x: -x["count"],
    )[:10]

    return {
        "period_days": days,
        "total_queries": total_queries,
        "avg_latency_ms": avg_latency,
        "knowledge_gaps_count": gap_count,
        "positive_feedback_rate": pos_rate,
        "total_feedback": len(feedbacks),
        "by_coverage": dict(by_coverage),
        "top_libraries": top_libraries,
    }


def get_knowledge_gaps(days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    """
    Estrae le domande frequenti a cui il RAG non ha trovato risposte o ha
    ricevuto feedback negativo, raggruppate per identificare aree documentali da colmare.
    """
    events = _read_events(days=days)
    queries = [e for e in events if e.get("type") == "query"]
    feedbacks = {fb.get("target_event_id"): fb for fb in events if fb.get("type") == "feedback"}

    frequency_map: dict[str, dict[str, Any]] = {}

    for q in queries:
        event_id = q.get("event_id", "")
        cov = q.get("coverage", "supported")
        res_count = q.get("result_count", 0)
        fb = feedbacks.get(event_id)
        has_negative_fb = fb is not None and fb.get("rating", 0) < 0

        is_gap = cov == "insufficient_evidence" or res_count == 0 or has_negative_fb

        if is_gap:
            normalized_q = q.get("query", "").strip()
            if not normalized_q:
                continue
            if normalized_q not in frequency_map:
                frequency_map[normalized_q] = {
                    "query": normalized_q,
                    "count": 0,
                    "library_id": q.get("library_id", ""),
                    "last_seen": q.get("timestamp", ""),
                    "reason": q.get("fallback_reason") or ("Nessun risultato" if res_count == 0 else "Evidenza insufficiente"),
                    "negative_feedback": 1 if has_negative_fb else 0,
                }
            frequency_map[normalized_q]["count"] += 1
            if has_negative_fb:
                frequency_map[normalized_q]["negative_feedback"] += 1

    sorted_gaps = sorted(
        frequency_map.values(),
        key=lambda item: (-item["count"], -item["negative_feedback"]),
    )
    return sorted_gaps[:limit]
