"""
api/integrations.py
External chat integrations (Teams, Slack, Telegram).
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from config import cfg
from legacy_winsarp.core.rag_engine import build_chat_engine, get_index
from api import _get_modules, _list_available_modules, _get_http_client, _resolve_module_name

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Integrations"])


async def _process_integration_query(query_text: str, module_name: str | None = None) -> tuple[str, str | None]:
    try:
        if not query_text or not query_text.strip():
            return "", "La domanda non può essere vuota."

        if not module_name:
            modules = _list_available_modules()
            if not modules:
                return "", "Nessun modulo documentale disponibile."
            module_name = "WinSarp" if "WinSarp" in modules else modules[0]

        _resolve_module_name(module_name)
        model_id = cfg.DEFAULT_MODEL_ID
        index = get_index(module_name, model_id, cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
        if index is None:
            return "", f"Nessun documento indicizzato per '{module_name}'."

        chat_engine = build_chat_engine(module_name, model_id, index, formula_only=False, modules=_get_modules())
        response = chat_engine.chat(query_text.strip())
        answer = response.response.strip()
        return answer, None
    except HTTPException as e:
        return "", str(e.detail)
    except Exception as e:
        _logger.error("Errore query integrazione: %s", e)
        return "", "Si è verificato un errore interno. Riprova più tardi."


@router.post("/api/integrations/teams", summary="Webhook per Microsoft Teams Outgoing Webhook")
async def teams_webhook(request: Request):
    teams_secret = cfg.TEAMS_WEBHOOK_SECRET
    if teams_secret:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Basic "):
            raise HTTPException(403, "Autorizzazione mancante")
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            user_part = decoded.split(":")[0]
            pass_part = decoded.split(":")[1] if ":" in decoded else ""
            ok = hmac.compare_digest(user_part, teams_secret) or hmac.compare_digest(pass_part, teams_secret)
            if not ok:
                raise HTTPException(403, "Secret Webhook non valido")
        except (ValueError, IndexError):
            raise HTTPException(403, "Authorization header non valido")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body JSON non valido")

    text = body.get("text", "").strip()
    text = re.sub(r"<at>[^<]+</at>", "", text).strip()

    if not text:
        return {"type": "message", "text": "Non ho ricevuto una domanda. Puoi riformulare?"}

    answer, error = await _process_integration_query(text)
    if error:
        return {"type": "message", "text": f"❌ {error}"}
    return {"type": "message", "text": answer}


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if not cfg.SLACK_SIGNING_SECRET or not signature:
        return False
    try:
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            cfg.SLACK_SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


@router.post("/api/integrations/slack", summary="Webhook per Slack Slash Command ed Event API")
async def slack_webhook(request: Request):
    body_bytes = await request.body()
    content_type = request.headers.get("content-type", "")

    if cfg.SLACK_SIGNING_SECRET:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
        signature = request.headers.get("X-Slack-Signature", "")
        if not _verify_slack_signature(body_bytes, timestamp, signature):
            raise HTTPException(403, "Firma Slack non valida")

    if "application/x-www-form-urlencoded" in content_type:
        form = parse_qs(body_bytes.decode("utf-8"))
        text = form.get("text", [""])[0].strip()

        if not text:
            return {
                "response_type": "ephemeral",
                "text": "Ciao! Sono Ermes. Fammi una domanda, ad esempio:\n"
                        "`/ermes Come si calcola la pausa pranzo?`",
            }

        answer, error = await _process_integration_query(text)
        if error:
            return {"response_type": "in_channel", "text": f"❌ {error}"}
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
            text = event["text"].strip()
            text = re.sub(r"<@[^>]+>", "", text).strip()

            if not text:
                return {"ok": True}

            answer, error = await _process_integration_query(text)
            if cfg.SLACK_BOT_TOKEN:
                client = _get_http_client()
                channel = event.get("channel", "")
                reply = f"❌ {error}" if error else answer
                asyncio.create_task(
                    client.post(
                        "https://slack.com/api/chat.postMessage",
                        headers={"Authorization": f"Bearer {cfg.SLACK_BOT_TOKEN}"},
                        json={"channel": channel, "text": reply, "link_names": False},
                    )
                )

    return {"ok": True}


@router.post("/api/integrations/telegram", summary="Webhook per Telegram Bot")
async def telegram_webhook(request: Request):
    bot_token = cfg.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise HTTPException(503, "Telegram Bot non configurato (ERMES_TELEGRAM_BOT_TOKEN)")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(400, "Update JSON non valido")

    message = update.get("message", {}) or update.get("edited_message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return {"ok": True}

    client = _get_http_client()
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def _process_and_reply():
        try:
            answer, error = await _process_integration_query(text)
            reply = f"❌ {error}" if error else answer
            if len(reply) > 4000:
                reply = reply[:3997] + "..."
            await client.post(
                api_url,
                json={
                    "chat_id": chat_id,
                    "text": reply,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except Exception as e:
            _logger.error("Errore risposta Telegram chat %s: %s", chat_id, e)

    asyncio.create_task(_process_and_reply())
    return {"ok": True}


@router.post("/api/integrations/telegram/set-webhook", summary="Registra l'URL del webhook Telegram")
async def telegram_set_webhook(request: Request):
    bot_token = cfg.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise HTTPException(503, "ERMES_TELEGRAM_BOT_TOKEN non configurato")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Body JSON richiesto con campo 'url'")

    webhook_url = body.get("url", "").strip()
    if not webhook_url:
        raise HTTPException(400, "Campo 'url' richiesto")

    client = _get_http_client()
    resp = await client.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={"url": webhook_url},
    )
    result = resp.json()
    if result.get("ok"):
        return {"ok": True, "description": result.get("description", "")}
    raise HTTPException(500, detail=result.get("description", "Errore setWebhook"))