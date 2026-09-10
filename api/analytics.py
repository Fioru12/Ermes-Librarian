"""
api/analytics.py
Enterprise Analytics and Knowledge Gaps API endpoints.

Nota sull'isolamento: queste rotte leggono un archivio di eventi che copre
tutte le biblioteche dell'istanza, quindi ogni risposta va filtrata sulle
biblioteche a cui chi chiede ha davvero accesso. `/overview` richiede il solo
ruolo `viewer` e prima non filtrava niente: rispondeva con l'elenco degli
identificativi di ogni biblioteca privata e quante domande ha ricevuto.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key, rate_limited
from api.libraries import get_library_store
from core.analytics import (
    feedback_already_given,
    find_query_event,
    get_analytics_summary,
    get_knowledge_gaps,
    record_feedback,
)
from core.library_store import LibraryStore

router = APIRouter(tags=["Analytics"])


class FeedbackRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    rating: int = Field(description="1 per positivo (like), -1 per negativo (dislike)")
    comment: str = Field(default="", max_length=500)


def _biblioteche_visibili(store: LibraryStore, auth: dict) -> set[str] | None:
    """Gli identificativi che chi chiede puo' vedere, o None per un admin.

    `None` significa "tutte" e vale solo per il ruolo globale `admin`: e' la
    stessa distinzione che `store.get_library` applica al contenuto.
    """
    if auth.get("role") == "admin":
        return None
    return {str(lib.get("id", "")) for lib in store.list_libraries(auth)}


@router.get(
    "/api/analytics/overview",
    summary="Panoramica analitiche e metriche RAG",
    dependencies=[Depends(rate_limited)],
)
async def analytics_overview(
    days: int = Query(default=30, ge=1, le=3650),
    _auth: dict = Depends(_require_role("viewer")),
    store: LibraryStore = Depends(get_library_store),
):
    return get_analytics_summary(days=days, library_ids=_biblioteche_visibili(store, _auth))


@router.get(
    "/api/analytics/knowledge-gaps",
    summary="Rilevamento Knowledge Gaps (domande senza risposta o con feedback negativo)",
    dependencies=[Depends(rate_limited)],
)
async def analytics_knowledge_gaps(
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=20, ge=1, le=500),
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
):
    gaps = get_knowledge_gaps(days=days, limit=limit, library_ids=_biblioteche_visibili(store, _auth))
    return {"gaps": gaps, "total": len(gaps), "period_days": days}


@router.post(
    "/api/analytics/feedback",
    summary="Invia feedback utente per una query",
    dependencies=[Depends(rate_limited)],
)
async def submit_feedback(
    body: FeedbackRequest,
    user: dict = Depends(_verify_api_key),
):
    # La rotta accettava qualunque event_id: nessuna verifica che l'evento
    # esistesse, che fosse una domanda di chi manda il giudizio, ne' che non
    # fosse gia' stato giudicato. Il rapporto Knowledge Gaps e' cio' su cui un
    # amministratore decide quali documenti scrivere, quindi bastava un ciclo
    # di POST per farci comparire in cima la domanda che si voleva.
    attore = str(user.get("username", "")).strip() or "anonymous"
    evento = find_query_event(body.event_id)
    if evento is None:
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if user.get("role") != "admin" and evento.get("actor") != attore:
        # 404 e non 403: distinguere "non tua" da "inesistente" direbbe a chi
        # prova identificativi a caso quali esistono.
        raise HTTPException(status_code=404, detail="Evento non trovato")
    if feedback_already_given(body.event_id, attore):
        raise HTTPException(status_code=409, detail="Hai già valutato questa risposta")

    ok = record_feedback(
        event_id=body.event_id,
        rating=body.rating,
        comment=body.comment,
        actor=attore,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Impossibile registrare il feedback")
    return {"ok": True, "event_id": body.event_id}


@router.get(
    "/api/analytics/export",
    summary="Esporta report Knowledge Gaps in formato CSV",
    dependencies=[Depends(rate_limited)],
)
async def export_knowledge_gaps_csv(
    days: int = Query(default=30, ge=1, le=3650),
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
):
    import csv
    import io

    from fastapi.responses import Response

    gaps = get_knowledge_gaps(days=days, limit=100, library_ids=_biblioteche_visibili(store, _auth))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Domanda", "Frequenza", "Biblioteca", "Motivo Esito", "Feedback Negativi", "Ultima Ricerca"])
    for g in gaps:
        writer.writerow(
            [
                # Le domande sono testo scritto dagli utenti: senza questo, un
                # valore che comincia per =, +, - o @ viene eseguito come
                # formula quando il CSV si apre in Excel.
                _cella_csv(g.get("query", "")),
                g.get("count", 0),
                g.get("library_id", ""),
                _cella_csv(g.get("reason", "")),
                g.get("negative_feedback", 0),
                g.get("last_seen", ""),
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ermes_knowledge_gaps_{days}d.csv"},
    )


def _cella_csv(valore: object) -> str:
    testo = str(valore)
    return "'" + testo if testo[:1] in ("=", "+", "-", "@", "\t", "\r") else testo
