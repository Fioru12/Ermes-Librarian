"""
rate_limiter.py
Sistema di rate limiting semplice in-memory per proteggere da abusi.
Limita richieste per IP/sessione per evitare DOS e abusi.
"""
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Configurazione limiti rate."""
    max_requests_per_minute: int = 300
    max_uploads_per_hour: int = 100
    max_upload_mb_per_hour: int = 2000
    cleanup_interval_seconds: int = 3600  # Pulizia ogni ora


class RateLimiter:
    """
    Rate limiter semplice in-memory con cleanup periodico.
    Per produzione, usare Redis o simili per distribuito.
    """

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._requests: dict[str, list] = defaultdict(list)
        self._uploads: dict[str, list] = defaultdict(list)
        self._upload_sizes: dict[str, float] = defaultdict(float)
        self._upload_sizes_log: dict[str, dict[str, float]] = defaultdict(dict)
        self._last_cleanup = time.time()
        self._cleanup_lock = threading.Lock()

    def _cleanup_old_entries(self, timestamps: list, max_age_seconds: float) -> list:
        """Rimuove timestamp più vecchi di max_age_seconds."""
        cutoff = time.time() - max_age_seconds
        return [ts for ts in timestamps if ts > cutoff]

    def _cleanup_stale_identifiers(self):
        """Rimuove identifier inattivi per evitare memory leak."""
        with self._cleanup_lock:
            now = time.time()
            if now - self._last_cleanup < self.config.cleanup_interval_seconds:
                return

            self._last_cleanup = now
            stale_time = now - (24 * 3600)  # 24 ore di inattività

            # Identifiers inattivi
            stale_ids = []
            for identifier in list(self._requests.keys()):
                if self._requests[identifier]:
                    max_ts = max(self._requests[identifier])
                    if max_ts < stale_time:
                        stale_ids.append(identifier)
                else:
                    stale_ids.append(identifier)

            # Rimuovi identifier stali
            for identifier in stale_ids:
                self._requests.pop(identifier, None)
                self._uploads.pop(identifier, None)
                self._upload_sizes.pop(identifier, None)

            if stale_ids:
                logging.debug(f"RateLimiter: rimossi {len(stale_ids)} identifier stali")

    def check_request_rate(self, identifier: str) -> tuple[bool, str]:
        """
        Controlla se identifier può fare una richiesta.
        Ritorna (allowed, reason).
        """
        self._cleanup_stale_identifiers()

        now = time.time()
        now - 60

        # Pulisci richieste vecchie
        self._requests[identifier] = self._cleanup_old_entries(
            self._requests[identifier], 60
        )

        # Conta richieste nell'ultimo minuto
        recent_count = len(self._requests[identifier])

        if recent_count >= self.config.max_requests_per_minute:
            return False, f"Rate limit: {recent_count} richieste/minuto (max {self.config.max_requests_per_minute})"

        # Registra questa richiesta
        self._requests[identifier].append(now)
        return True, ""

    def _recalculate_upload_size(self, identifier: str) -> float:
        """
        Ricalcola la dimensione totale upload per identifier
        basandosi sui timestamp attuali.
        """
        cutoff = time.time() - 3600
        total = 0.0
        for ts in self._uploads.get(identifier, []):
            if ts > cutoff:
                total += self._upload_sizes_log.get(identifier, {}).get(str(ts), 0.0)
        return total

    def check_upload_rate(self, identifier: str, size_mb: float) -> tuple[bool, str]:
        """
        Controlla se identifier può fare upload.
        Ritorna (allowed, reason).
        """
        self._cleanup_stale_identifiers()

        now = time.time()

        # Inizializza strutture dati per questo identifier
        if identifier not in self._upload_sizes_log:
            self._upload_sizes_log[identifier] = {}

        # Pulisci upload vecchi basandoti sui timestamp
        self._uploads[identifier] = self._cleanup_old_entries(
            self._uploads.get(identifier, []), 3600
        )

        # Rimuovi entry di size per timestamp scaduti
        cutoff = now - 3600
        self._upload_sizes_log[identifier] = {
            ts_str: sz for ts_str, sz in self._upload_sizes_log[identifier].items()
            if float(ts_str) > cutoff
        }

        # Calcola size corrente
        upload_size = sum(self._upload_sizes_log[identifier].values())

        if upload_size + size_mb > self.config.max_upload_mb_per_hour:
            return False, f"Upload size limit: {upload_size:.1f}MB/ora (max {self.config.max_upload_mb_per_hour}MB)"

        upload_count = len(self._uploads[identifier])
        if upload_count >= self.config.max_uploads_per_hour:
            return False, f"Upload limit: {upload_count} upload/ora (max {self.config.max_uploads_per_hour})"

        # Registra questo upload
        self._uploads[identifier].append(now)
        self._upload_sizes_log[identifier][str(now)] = size_mb
        # Tieni sincronizzato _upload_sizes per retrocompatibilità
        self._upload_sizes[identifier] = sum(self._upload_sizes_log[identifier].values())
        return True, ""

    def reset(self, identifier: str = None):
        """Resetta i contatori per identifier o tutti se None."""
        if identifier:
            self._requests.pop(identifier, None)
            self._uploads.pop(identifier, None)
            self._upload_sizes.pop(identifier, None)
        else:
            self._requests.clear()
            self._uploads.clear()
            self._upload_sizes.clear()

    def get_upload_status(self, identifier: str) -> dict:
        """
        Ritorna lo stato corrente degli upload per un identifier.
        Utile per debug e monitoring.
        """
        time.time()
        self._uploads[identifier] = self._cleanup_old_entries(
            self._uploads.get(identifier, []), 3600
        )
        return {
            "upload_count": len(self._uploads.get(identifier, [])),
            "total_size_mb": self._upload_sizes.get(identifier, 0.0),
            "max_uploads": self.config.max_uploads_per_hour,
            "max_size_mb": self.config.max_upload_mb_per_hour,
        }


# Istanza globale per uso in app
_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Ritorna l'istanza globale del rate limiter."""
    return _limiter
