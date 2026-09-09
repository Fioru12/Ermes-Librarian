"""Sessioni browser su archivio condiviso.

Perche' questo modulo esiste
----------------------------
Le sessioni vivevano in un dizionario di modulo (`api/auth.py::_SESSIONS`).
Finche' l'applicazione gira in un solo processo funziona; appena se ne
avviano due dietro un bilanciatore smette di funzionare, e non in modo
evidente:

- chi fa login sull'istanza A riceve 401 alla richiesta successiva se
  questa finisce sull'istanza B;
- disattivare un utente ne invalida le sessioni solo sull'istanza che ha
  ricevuto la chiamata: sulle altre resta autenticato fino alla scadenza;
- ogni riavvio o rilascio disconnette tutti.

Il progetto dichiara supporto PostgreSQL e ha test di carico, cioe'
l'infrastruttura per scalare, sopra un'autenticazione che per costruzione
non poteva superare un processo. Qui le sessioni passano sullo stesso
archivio delle biblioteche, che e' gia' condiviso fra le istanze: nessun
componente aggiuntivo da chiedere all'azienda.

Nota sui token
--------------
In memoria il token era la chiave del dizionario. Su un archivio durevole
questo sarebbe un peggioramento: un accesso in lettura al database
regalerebbe sessioni valide, pronte da usare. Viene quindi memorizzato solo
lo SHA-256 del token, come per una password: il cookie del browser resta
l'unico posto dove il valore in chiaro esiste.
"""

import hashlib
import json
import logging
import time

from core.shared_backend import SharedTableStore

_logger = logging.getLogger(__name__)

_TABLE = """
CREATE TABLE IF NOT EXISTS browser_sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    payload TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL
)
"""

_TABLE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS browser_sessions_by_user ON browser_sessions(username)",
    "CREATE INDEX IF NOT EXISTS browser_sessions_by_expiry ON browser_sessions(expires_at)",
)


def _fingerprint(token: str) -> str:
    """SHA-256 del token: quello che viene scritto, mai il token stesso."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionStore(SharedTableStore):
    """Sessioni condivise fra i processi che puntano allo stesso archivio."""

    _SCHEMA = _TABLE
    _INDEXES = _TABLE_INDEXES

    # -- ciclo di vita di una sessione ---------------------------------

    def create(self, token: str, user: dict, expires_at: float) -> None:
        backend = self._connection()
        backend.execute_write(
            "INSERT INTO browser_sessions (token_hash, username, payload, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (token_hash) DO UPDATE SET username = excluded.username, "
            "payload = excluded.payload, expires_at = excluded.expires_at",
            (
                _fingerprint(token),
                str(user.get("username", "")),
                json.dumps(user),
                float(expires_at),
            ),
        )
        backend.commit()

    def get(self, token: str | None) -> dict | None:
        """Utente della sessione, oppure None se assente o scaduta.

        Una sessione scaduta viene rimossa qui invece di restare in attesa
        della pulizia periodica: il costo e' una scrittura sul percorso
        raro, il guadagno e' che l'archivio non accumula credenziali morte.
        """
        if not token:
            return None
        backend = self._connection()
        row = backend.execute_one(
            "SELECT payload, expires_at FROM browser_sessions WHERE token_hash = ?",
            (_fingerprint(token),),
        )
        if row is None:
            return None
        if float(row["expires_at"]) <= time.time():
            self.delete(token)
            return None
        try:
            user = json.loads(row["payload"])
        except (TypeError, ValueError):
            _logger.warning("Sessione con payload illeggibile, rimossa")
            self.delete(token)
            return None
        return user if isinstance(user, dict) else None

    def delete(self, token: str | None) -> None:
        if not token:
            return
        backend = self._connection()
        backend.execute_write("DELETE FROM browser_sessions WHERE token_hash = ?", (_fingerprint(token),))
        backend.commit()

    def delete_for_user(self, username: str) -> int:
        """Chiude tutte le sessioni di un utente, su ogni istanza."""
        backend = self._connection()
        removed = backend.execute_write("DELETE FROM browser_sessions WHERE username = ?", (username,))
        backend.commit()
        return removed

    def purge_expired(self) -> int:
        backend = self._connection()
        removed = backend.execute_write("DELETE FROM browser_sessions WHERE expires_at <= ?", (time.time(),))
        backend.commit()
        return removed

    # -- supporto ------------------------------------------------------

    def clear(self) -> None:
        """Rimuove ogni sessione. Usata dai test fra un caso e l'altro."""
        backend = self._connection()
        backend.execute_write("DELETE FROM browser_sessions", ())
        backend.commit()

    def count(self) -> int:
        row = self._connection().execute_one("SELECT COUNT(*) AS n FROM browser_sessions", ())
        return int(row["n"]) if row else 0


session_store = SessionStore()
