"""
core/hyde.py
Enterprise HyDE (Hypothetical Document Embeddings) Engine per Ermes Knowledge.

Genera un documento o passaggio ipotetico in risposta a una domanda utente,
consentendo di effettuare la ricerca per similarita tra l'embedding del documento ipotetico
e i chunk memorizzati nella libreria, riducendo lo scostamento semantico (domain shift).
"""
from __future__ import annotations

import logging

import httpx

from config import cfg

logger = logging.getLogger(__name__)

_HYDE_SYSTEM_PROMPT = (
    "Sei un esperto redattore di documentazione aziendale. "
    "Dato un quesito o argomento dell'utente, scrivi un breve paragrafo o estratto di documento "
    "ipotetico (2-4 frasi in italiano) che risponde in modo dettagliato e formale al quesito. "
    "Non includere preamboli, introduzioni o saluti: scrivi esclusivamente il testo del documento ipotetico."
)


def generate_hypothetical_document(query: str, mode: str | None = None) -> str:
    """
    Genera un passaggio ipotetico (HyDE) per la query fornita.
    In caso di errore o assenza di modello LLM locale/remoto, restituisce la query originale.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return query

    # Se le chiamate LLM non sono attive o in modalita evidence_only pura
    mode = mode or getattr(cfg, "HYDE_MODE", "local_ollama")

    if mode == "disabled":
        return cleaned_query

    try:
        if mode == "local_ollama":
            response = httpx.post(
                f"{cfg.OLLAMA_HOST.rstrip('/')}/api/chat",
                json={
                    "model": cfg.DEFAULT_MODEL_ID,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
                        {"role": "user", "content": cleaned_query},
                    ],
                    "options": {"temperature": 0.3},
                },
                timeout=cfg.LIBRARY_ASSISTANT_TIMEOUT_SEC,
            )
            response.raise_for_status()
            content = str(response.json().get("message", {}).get("content", "")).strip()
            if content:
                return content
        elif mode == "approved_openrouter" and cfg.LIBRARY_CLOUD_CONSENT and cfg.OPENROUTER_API_KEY:
            response = httpx.post(
                f"{cfg.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.DEFAULT_MODEL_ID,
                    "messages": [
                        {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
                        {"role": "user", "content": cleaned_query},
                    ],
                    "temperature": 0.3,
                },
                timeout=cfg.LIBRARY_ASSISTANT_TIMEOUT_SEC,
            )
            response.raise_for_status()
            content = str(response.json()["choices"][0]["message"].get("content", "")).strip()
            if content:
                return content
    except Exception as err:
        logger.warning("HyDE generation fallback per query '%s': %s", cleaned_query, err)

    return cleaned_query
