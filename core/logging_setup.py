"""Configurazione del logging applicativo.

Perche' esiste
--------------
Nel percorso di prodotto non c'era **nessuna** configurazione di logging: solo
`scripts/backup.py` chiamava `basicConfig`. Di conseguenza tutti gli avvisi
scritti con cura nel codice — token OIDC rifiutato, chiave di audit
segnaposto, problemi di configurazione — finivano sul gestore di ultima
istanza di Python, cioe' stderr senza formato, e tutto cio' che stava sotto
WARNING non veniva emesso affatto.

In azienda i log non li legge una persona su un terminale: finiscono in un
aggregatore che li interroga per campi. Una riga di testo libero li' dentro
non e' consultabile. Da qui il formato JSON, attivabile con
`ERMES_LOG_FORMAT=json`, che resta disattivato di default perche' durante lo
sviluppo il testo leggibile e' piu' utile.

Correlazione delle richieste
----------------------------
Ogni riga emessa durante una richiesta HTTP porta lo stesso `request_id`, che
viene preso dall'intestazione `X-Request-ID` se il reverse proxy ne mette una
e altrimenti generato. E' la differenza fra "c'e' stato un errore" e "questo
errore appartiene alla richiesta che l'utente ci ha segnalato": senza,
correlare le righe di un'istanza sotto carico e' impossibile.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging

# Campi che LogRecord porta sempre: tutto il resto e' contesto aggiunto dal
# chiamante con `extra=` e va emesso insieme all'evento.
_STANDARD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ermes_request_id", default=None)
actor_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("ermes_actor", default=None)


class RequestContextFilter(logging.Filter):
    """Aggiunge a ogni record il contesto della richiesta in corso, se c'e'."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_var.get()
        if request_id:
            record.request_id = request_id
        actor = actor_var.get()
        if actor:
            record.actor = actor
        return True


class JsonFormatter(logging.Formatter):
    """Un evento per riga, con i campi separati."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": _dt.datetime.fromtimestamp(record.created, tz=_dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # `default=str` invece di lasciar sollevare: un campo non
        # serializzabile non deve far perdere l'intero evento, che e'
        # esattamente il momento in cui serve leggerlo.
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Formato leggibile per lo sviluppo, con il request id quando c'e'."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = getattr(record, "request_id", None)
        return f"{base} [req {request_id}]" if request_id else base


def _build_handler(log_format: str) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    handler.addFilter(RequestContextFilter())
    return handler


def configure_logging(cfg) -> None:
    """Installa il formato scelto sul logger radice e su quelli di uvicorn.

    Uvicorn attacca handler propri ai suoi logger: senza riallinearli, meta'
    delle righe uscirebbe in JSON e meta' no, che e' peggio di entrambi.
    """
    log_format = getattr(cfg, "LOG_FORMAT", "text")
    level_name = getattr(cfg, "LOG_LEVEL", "INFO")
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(_build_handler(log_format))
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        for existing in list(uvicorn_logger.handlers):
            uvicorn_logger.removeHandler(existing)
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)
