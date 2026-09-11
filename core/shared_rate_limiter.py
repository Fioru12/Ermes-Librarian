"""Limitatore di frequenza condiviso fra le istanze.

`core/rate_limiter.py` conta in memoria, per processo: due istanze dietro un
bilanciatore raddoppiano ogni soglia, e la documentazione lo dichiarava come
il primo intervento necessario per una scalabilita' orizzontale reale. Questa
classe ha la stessa interfaccia e tiene i conteggi nell'archivio condiviso,
come gia' fanno le sessioni e i tentativi di accesso (core/shared_backend.py):
nessun componente in piu' da installare.

Costo: una scrittura sul database per ogni richiesta limitata. Il guardiano
degli accessi paga lo stesso prezzo e non e' mai stato un problema; se lo
diventasse, ERMES_RATE_LIMIT_BACKEND=memory torna al contatore per processo,
dichiarando con cio' di rinunciare alla coerenza fra istanze.
"""

from __future__ import annotations

import time
import uuid

from core.rate_limiter import RateLimitConfig
from core.shared_backend import SharedTableStore

_FINESTRA_RICHIESTE = 60.0
_FINESTRA_UPLOAD = 3600.0


class SharedRateLimiter(SharedTableStore):
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS rate_events (
        id TEXT PRIMARY KEY,
        identifier TEXT NOT NULL,
        kind TEXT NOT NULL,
        occurred_at DOUBLE PRECISION NOT NULL,
        size_mb DOUBLE PRECISION NOT NULL DEFAULT 0
    )
    """
    _INDEXES = (
        "CREATE INDEX IF NOT EXISTS rate_events_by_identifier ON rate_events(identifier, kind, occurred_at)",
        "CREATE INDEX IF NOT EXISTS rate_events_by_time ON rate_events(occurred_at)",
    )

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        super().__init__()
        self.config = config or RateLimitConfig()
        self._ultima_pulizia = 0.0

    # -- conteggi ----------------------------------------------------------

    def _conta(self, identifier: str, kind: str, finestra: float) -> tuple[int, float]:
        backend = self._connection()
        row = backend.execute_one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(size_mb), 0) AS mb FROM rate_events "
            "WHERE identifier = ? AND kind = ? AND occurred_at > ?",
            (identifier, kind, time.time() - finestra),
        )
        return (int(row["n"]), float(row["mb"])) if row else (0, 0.0)

    def _registra(self, identifier: str, kind: str, size_mb: float = 0.0) -> None:
        backend = self._connection()
        backend.execute_write(
            "INSERT INTO rate_events (id, identifier, kind, occurred_at, size_mb) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, identifier, kind, time.time(), size_mb),
        )
        backend.commit()
        self._pulisci_se_serve(backend)

    def _pulisci_se_serve(self, backend) -> None:
        # Le righe fuori da entrambe le finestre non servono a nessuno: si
        # tolgono a intervalli, non a ogni richiesta.
        adesso = time.time()
        if adesso - self._ultima_pulizia < 60:
            return
        backend.execute_write("DELETE FROM rate_events WHERE occurred_at <= ?", (adesso - _FINESTRA_UPLOAD,))
        backend.commit()
        self._ultima_pulizia = adesso

    # -- interfaccia identica a RateLimiter -------------------------------

    def check_request_rate(self, identifier: str, max_per_minute: int | None = None) -> tuple[bool, str]:
        massimo = self.config.max_requests_per_minute if max_per_minute is None else max_per_minute
        recenti, _ = self._conta(identifier, "request", _FINESTRA_RICHIESTE)
        if recenti >= massimo:
            return False, f"Rate limit: {recenti} richieste/minuto (max {massimo})"
        self._registra(identifier, "request")
        return True, ""

    def check_upload_rate(self, identifier: str, size_mb: float) -> tuple[bool, str]:
        quanti, totale_mb = self._conta(identifier, "upload", _FINESTRA_UPLOAD)
        if totale_mb + size_mb > self.config.max_upload_mb_per_hour:
            return False, f"Upload size limit: {totale_mb:.1f}MB/ora (max {self.config.max_upload_mb_per_hour}MB)"
        if quanti >= self.config.max_uploads_per_hour:
            return False, f"Upload limit: {quanti} upload/ora (max {self.config.max_uploads_per_hour})"
        self._registra(identifier, "upload", size_mb)
        return True, ""

    def reset(self, identifier: str | None = None) -> None:
        backend = self._connection()
        if identifier:
            backend.execute_write("DELETE FROM rate_events WHERE identifier = ?", (identifier,))
        else:
            backend.execute_write("DELETE FROM rate_events")
        backend.commit()

    def get_upload_status(self, identifier: str) -> dict:
        quanti, totale_mb = self._conta(identifier, "upload", _FINESTRA_UPLOAD)
        return {
            "upload_count": quanti,
            "total_size_mb": totale_mb,
            "max_uploads": self.config.max_uploads_per_hour,
            "max_size_mb": self.config.max_upload_mb_per_hour,
        }
