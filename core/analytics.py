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


# `timedelta` solleva OverflowError oltre ~999999999 giorni: un parametro di
# query diventava un errore del server. Le rotte lo validano, questo e' il
# secondo strato, per i chiamanti interni.
_MAX_GIORNI = 3650


def _giorni_validi(days: int) -> int:
    try:
        valore = int(days)
    except (TypeError, ValueError):
        return 30
    return max(1, min(valore, _MAX_GIORNI))


def find_query_event(event_id: str) -> dict[str, Any] | None:
    """L'evento di domanda con questo identificativo, se esiste.

    Serve alla rotta del feedback, che accettava qualunque `event_id` senza
    verificare nulla: il rapporto Knowledge Gaps e' cio' su cui un
    amministratore decide quali documenti scrivere, e chiunque potesse
    indovinare o inventare un identificativo poteva farci comparire la domanda
    che voleva.
    """
    if not event_id:
        return None
    for evento in _read_events(days=_MAX_GIORNI):
        if evento.get("type") == "query" and evento.get("event_id") == event_id:
            return evento
    return None


def feedback_already_given(event_id: str, actor: str) -> bool:
    """Se questo utente ha gia' giudicato questo evento.

    Senza questo controllo un ciclo di POST gonfiava `negative_feedback` a
    piacere e portava in cima al rapporto la domanda desiderata.
    """
    for evento in _read_events(days=_MAX_GIORNI):
        if (
            evento.get("type") == "feedback"
            and evento.get("target_event_id") == event_id
            and evento.get("actor") == actor
        ):
            return True
    return False


def export_user_events(actor: str) -> list[dict[str, Any]]:
    """Le domande e i giudizi registrati a nome di `actor`, senza limite di
    giorni: il diritto di accesso copre tutto cio' che c'e'."""
    return [e for e in _read_events(days=_MAX_GIORNI) if e.get("actor") == actor]


def erase_user_events(actor: str) -> int:
    """Rimuove dall'archivio analitico ogni evento di `actor`. Ritorna quanti.

    Riscrive il file per intero sotto lock, in modo atomico: le domande sono
    testo scritto dalla persona, e tenerle con l'attore anonimizzato le
    lascerebbe comunque leggibili nel rapporto Knowledge Gaps.
    """
    if not os.path.exists(cfg.ANALYTICS_FILE):
        return 0
    with _ANALYTICS_LOCK:
        with open(cfg.ANALYTICS_FILE, encoding="utf-8") as f:
            righe = [r for r in f if r.strip()]
        conservate: list[str] = []
        rimosse = 0
        for riga in righe:
            try:
                evento = json.loads(riga)
            except json.JSONDecodeError:
                conservate.append(riga)
                continue
            if evento.get("actor") == actor:
                rimosse += 1
            else:
                conservate.append(riga)
        if rimosse:
            temporaneo = cfg.ANALYTICS_FILE + ".tmp"
            with open(temporaneo, "w", encoding="utf-8") as f:
                f.writelines(r if r.endswith("\n") else r + "\n" for r in conservate)
            os.replace(temporaneo, cfg.ANALYTICS_FILE)
    return rimosse


def _read_events(days: int = 30) -> list[dict[str, Any]]:
    if not os.path.exists(cfg.ANALYTICS_FILE):
        return []
    cutoff = datetime.now(UTC) - timedelta(days=_giorni_validi(days))
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


def get_analytics_summary(days: int = 30, library_ids: set[str] | None = None) -> dict[str, Any]:
    """Genera riepilogo delle metriche per dashboard di governance.

    `library_ids` restringe il calcolo alle biblioteche a cui chi chiede ha
    accesso; `None` significa "tutte" ed e' riservato agli amministratori. La
    rotta /overview richiede il solo ruolo `viewer`, e senza questo filtro
    rispondeva con `top_libraries`, cioe' l'elenco degli identificativi di
    ogni biblioteca privata dell'azienda e quante domande ha ricevuto: non il
    contenuto, ma proprio il confine che il prodotto promette di tenere.
    """
    events = _read_events(days=days)
    queries = [e for e in events if e.get("type") == "query"]
    if library_ids is not None:
        queries = [q for q in queries if q.get("library_id", "") in library_ids]
        visibili = {q.get("event_id") for q in queries}
        feedbacks = [e for e in events if e.get("type") == "feedback" and e.get("target_event_id") in visibili]
    else:
        feedbacks = [e for e in events if e.get("type") == "feedback"]

    total_queries = len(queries)
    if total_queries == 0:
        return {
            "period_days": days,
            "total_queries": 0,
            "avg_latency_ms": 0.0,
            "knowledge_gaps_count": 0,
            # None, non 0.0: senza giudizi ricevuti il tasso non e' zero, e'
            # sconosciuto. Il cruscotto mostra "—".
            "positive_feedback_rate": None,
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
    # Valeva 100.0 quando i feedback erano zero: un cruscotto che dichiarava
    # soddisfazione perfetta perche' non aveva ricevuto un solo giudizio,
    # indistinguibile da un dato reale per chi lo guarda.
    pos_rate = round((positive_fb / len(feedbacks) * 100.0), 1) if feedbacks else None

    top_libraries = [
        {"library_id": lib, "count": count} for lib, count in sorted(by_library.items(), key=lambda voce: -voce[1])[:10]
    ]

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


def get_knowledge_gaps(days: int = 30, limit: int = 20, library_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """
    Estrae le domande frequenti a cui il RAG non ha trovato risposte o ha
    ricevuto feedback negativo, raggruppate per identificare aree documentali da colmare.

    `library_ids` come in `get_analytics_summary`: le domande sono testo
    scritto dagli utenti, e non devono attraversare il confine fra biblioteche
    piu' di quanto lo facciano i documenti.
    """
    events = _read_events(days=days)
    limit = max(1, int(limit))
    queries = [e for e in events if e.get("type") == "query"]
    if library_ids is not None:
        queries = [q for q in queries if q.get("library_id", "") in library_ids]
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
                    "reason": q.get("fallback_reason")
                    or ("Nessun risultato" if res_count == 0 else "Evidenza insufficiente"),
                    # Era inizializzato a 1 e poi incrementato subito sotto,
                    # nella stessa iterazione: un feedback negativo ne
                    # contava due.
                    "negative_feedback": 0,
                }
            frequency_map[normalized_q]["count"] += 1
            if has_negative_fb:
                frequency_map[normalized_q]["negative_feedback"] += 1

    sorted_gaps = sorted(
        frequency_map.values(),
        key=lambda item: (-item["count"], -item["negative_feedback"]),
    )
    return sorted_gaps[:limit]
