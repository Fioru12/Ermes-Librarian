"""Slack e Teams: due adattatori sottili sopra la stessa risposta evidence-first
usata dall'endpoint /{library_id}/ask.

Un webhook non ha una sessione utente Ermes: qui l'autenticazione e' la firma
della piattaforma (HMAC Slack, HMAC Teams), non _verify_api_key. Per questo
un canale deve essere registrato esplicitamente su UNA biblioteca (vedi
api/libraries.py: add_library_chat_integration, solo proprietario/admin) prima
di poter fare domande — non esiste un percorso che lasci un webhook scegliere
quale biblioteca interrogare.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

from api import _get_http_client
from api.libraries import _answer_question, get_library_store
from config import cfg
from core.library_store import LibraryStore

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["Chat Integrations"])

_SLACK_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if not cfg.SLACK_SIGNING_SECRET or not signature:
        return False
    try:
        # Una firma calcolata su una richiesta vecchia resta matematicamente
        # valida per sempre: senza questo controllo, una richiesta intercettata
        # una sola volta potrebbe essere ripetuta indefinitamente (replay).
        if abs(time.time() - int(timestamp)) > _SLACK_TIMESTAMP_TOLERANCE_SECONDS:
            return False
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            cfg.SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except (ValueError, UnicodeDecodeError):
        return False


def _verify_teams_signature(body: bytes, authorization_header: str) -> bool:
    """Teams firma il body con HMAC-SHA256 usando il secret dell'Outgoing
    Webhook come chiave (dopo averlo decodificato da base64), non con Basic
    Auth: https://learn.microsoft.com/microsoftteams/platform/webhooks-and-connectors/how-to/add-outgoing-webhook
    Header atteso: "Authorization: HMAC <base64(hmac_sha256(key, body))>".
    """
    if not cfg.TEAMS_WEBHOOK_SECRET or not authorization_header.startswith("HMAC "):
        return False
    try:
        key = base64.b64decode(cfg.TEAMS_WEBHOOK_SECRET)
        expected = base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()
        received = authorization_header[len("HMAC "):].strip()
        return hmac.compare_digest(expected, received)
    except (ValueError, TypeError):
        return False


async def _resolve_answer_text(store: LibraryStore, platform: str, external_channel_id: str, question: str) -> str:
    integration = store.get_chat_integration_by_channel(platform, external_channel_id)
    if integration is None:
        return "Questo canale non è collegato a nessuna biblioteca Ermes. Chiedi al proprietario di una biblioteca di collegarlo."
    if not question:
        return "Fammi una domanda, ad esempio: «Come si calcola la pausa pranzo?»"
    actor = {"username": integration["created_by"], "role": "editor"}
    result = await asyncio.to_thread(_answer_question, store, integration["library_id"], question, 3, actor)
    answer = result["answer"]
    filenames = sorted({item["filename"] for item in result["citations"]})
    if filenames:
        answer = f"{answer}\n\n📎 Fonti: {', '.join(filenames)}"
    return answer


@router.post("/slack", summary="Webhook per Slack Slash Command ed Event API")
async def slack_webhook(request: Request):
    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "")

    if cfg.SLACK_SIGNING_SECRET:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
        signature = request.headers.get("X-Slack-Signature", "")
        if not _verify_slack_signature(body_bytes, timestamp, signature):
            raise HTTPException(403, "Firma Slack non valida")

    store = get_library_store()

    if "application/x-www-form-urlencoded" in content_type:
        form = parse_qs(body_bytes.decode("utf-8"))
        text = form.get("text", [""])[0].strip()
        channel_id = form.get("channel_id", [""])[0]
        answer = await _resolve_answer_text(store, "slack", channel_id, text)
        return {"response_type": "in_channel", "text": answer}

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body JSON non valido")

    if body.get("type") == "url_verification":
        return {"challenge": body["challenge"]}

    if body.get("type") == "event_callback":
        event = body.get("event", {})
        if event.get("type") in ("message", "app_mention") and event.get("text"):
            text = re.sub(r"<@[^>]+>", "", event["text"]).strip()
            channel_id = event.get("channel", "")

            async def _process_and_reply():
                try:
                    answer = await _resolve_answer_text(store, "slack", channel_id, text)
                    if cfg.SLACK_BOT_TOKEN:
                        client = _get_http_client()
                        await client.post(
                            "https://slack.com/api/chat.postMessage",
                            headers={"Authorization": f"Bearer {cfg.SLACK_BOT_TOKEN}"},
                            json={"channel": channel_id, "text": answer, "link_names": False},
                        )
                except Exception as error:
                    _logger.error("Errore risposta Slack canale %s: %s", channel_id, error)

            asyncio.create_task(_process_and_reply())

    return {"ok": True}


@router.post("/teams", summary="Webhook per Microsoft Teams Outgoing Webhook")
async def teams_webhook(request: Request):
    body_bytes = await request.body()
    if cfg.TEAMS_WEBHOOK_SECRET:
        authorization = request.headers.get("authorization", "")
        if not _verify_teams_signature(body_bytes, authorization):
            raise HTTPException(403, "Firma Teams non valida")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body JSON non valido")

    text = re.sub(r"<at>[^<]+</at>", "", body.get("text", "")).strip()
    channel_id = body.get("conversation", {}).get("id", "")

    store = get_library_store()
    answer = await _resolve_answer_text(store, "teams", channel_id, text)
    return {"type": "message", "text": answer}
