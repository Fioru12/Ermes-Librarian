"""
api/analytics.py
Enterprise Analytics and Knowledge Gaps API endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _require_role, _verify_api_key
from core.analytics import get_analytics_summary, get_knowledge_gaps, record_feedback

router = APIRouter(tags=["Analytics"])


class FeedbackRequest(BaseModel):
    event_id: str = Field(min_length=1)
    rating: int = Field(description="1 per positivo (like), -1 per negativo (dislike)")
    comment: str = Field(default="", max_length=500)


@router.get("/api/analytics/overview", summary="Panoramica analitiche e metriche RAG")
async def analytics_overview(
    days: int = 30,
    _auth: dict = Depends(_require_role("viewer")),
):
    return get_analytics_summary(days=days)


@router.get("/api/analytics/knowledge-gaps", summary="Rilevamento Knowledge Gaps (domande senza risposta o con feedback negativo)")
async def analytics_knowledge_gaps(
    days: int = 30,
    limit: int = 20,
    _auth: dict = Depends(_require_role("admin")),
):
    gaps = get_knowledge_gaps(days=days, limit=limit)
    return {"gaps": gaps, "total": len(gaps), "period_days": days}


@router.post("/api/analytics/feedback", summary="Invia feedback utente per una query")
async def submit_feedback(
    body: FeedbackRequest,
    user: dict = Depends(_verify_api_key),
):
    ok = record_feedback(
        event_id=body.event_id,
        rating=body.rating,
        comment=body.comment,
        actor=user.get("username", "anonymous"),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Impossibile registrare il feedback")
    return {"ok": True, "event_id": body.event_id}


@router.get("/api/analytics/export", summary="Esporta report Knowledge Gaps in formato CSV")
async def export_knowledge_gaps_csv(
    days: int = 30,
    _auth: dict = Depends(_require_role("admin")),
):
    import csv
    import io
    from fastapi.responses import Response

    gaps = get_knowledge_gaps(days=days, limit=100)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Domanda", "Frequenza", "Biblioteca", "Motivo Esito", "Feedback Negativi", "Ultima Ricerca"])
    for g in gaps:
        writer.writerow([
            g.get("query", ""),
            g.get("count", 0),
            g.get("library_id", ""),
            g.get("reason", ""),
            g.get("negative_feedback", 0),
            g.get("last_seen", ""),
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=ermes_knowledge_gaps_{days}d.csv"},
    )

