"""Protezione contro i tentativi ripetuti di accesso.

Perche' questo modulo esiste
----------------------------
`POST /api/auth/login` accettava un numero illimitato di tentativi di
password. Non per una svista isolata: `core/rate_limiter.py` esiste, e'
completo e ha dieci test che passano, ma all'epoca non era applicato a
nessuna rotta — un componente verificato in isolamento che non proteggeva
niente, esattamente come i test OIDC che verificavano l'integrazione senza
firmare i token. (Da allora il limitatore generale e' stato collegato alle
rotte costose come `api/auth.py::rate_limited`; il conteggio dei tentativi
di accesso resta comunque separato, perche' misura una cosa diversa: non la
frequenza delle richieste ma i fallimenti di autenticazione, su una finestra
di minuti invece che di secondi.)

Non esisteva nemmeno un conteggio dei tentativi falliti: nessun blocco,
nessuna traccia, nessun ritardo.

Su cosa si conta, e perche'
---------------------------
I tentativi vengono contati **per indirizzo IP** e **per coppia
(IP, username)**, mai per solo username. La differenza non e' teorica: se si
bloccasse un account dopo N fallimenti da qualunque provenienza, chiunque
conosca il nome utente di un collega potrebbe lasciarlo fuori dal sistema
sbagliando la password apposta. Il blocco per username diventerebbe uno
strumento di disservizio invece che una difesa.

Il conteggio vive sull'archivio condiviso: con lo stato in memoria di
processo, tre istanze dietro un bilanciatore avrebbero concesso tre volte i
tentativi previsti.
"""

import logging
import time
import uuid

import config
from core.shared_backend import SharedTableStore

_logger = logging.getLogger(__name__)


class LoginGuard(SharedTableStore):
    """Conta i fallimenti recenti e decide se un tentativo va rifiutato."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS login_failures (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        occurred_at DOUBLE PRECISION NOT NULL
    )
    """

    _INDEXES = (
        "CREATE INDEX IF NOT EXISTS login_failures_by_scope ON login_failures(scope)",
        "CREATE INDEX IF NOT EXISTS login_failures_by_time ON login_failures(occurred_at)",
    )

    # -- parametri ------------------------------------------------------

    def _max_attempts(self) -> int:
        return max(1, int(config.cfg.LOGIN_MAX_ATTEMPTS))

    def _window_seconds(self) -> float:
        return max(1, int(config.cfg.LOGIN_LOCKOUT_MINUTES)) * 60.0

    @staticmethod
    def _scopes(client_ip: str, username: str) -> list[str]:
        """Gli ambiti su cui si conta: mai lo username da solo."""
        return [f"ip:{client_ip}", f"ip+user:{client_ip}|{username.strip().lower()}"]

    # -- interrogazione --------------------------------------------------

    def failures_in_window(self, scope: str) -> int:
        backend = self._connection()
        row = backend.execute_one(
            "SELECT COUNT(*) AS n FROM login_failures WHERE scope = ? AND occurred_at > ?",
            (scope, time.time() - self._window_seconds()),
        )
        return int(row["n"]) if row else 0

    def is_blocked(self, client_ip: str, username: str) -> tuple[bool, str]:
        """(bloccato, motivo). Il motivo non rivela se l'utente esista."""
        limit = self._max_attempts()
        for scope in self._scopes(client_ip, username):
            if self.failures_in_window(scope) >= limit:
                minutes = int(self._window_seconds() // 60)
                return True, f"Troppi tentativi di accesso falliti. Riprova fra {minutes} minuti."
        return False, ""

    # -- aggiornamento ---------------------------------------------------

    def register_failure(self, client_ip: str, username: str) -> None:
        backend = self._connection()
        now = time.time()
        for scope in self._scopes(client_ip, username):
            backend.execute_write(
                "INSERT INTO login_failures (id, scope, occurred_at) VALUES (?, ?, ?)",
                # Id casuale, non derivato dall'istante: due fallimenti
                # nello stesso tick del clock collidevano sulla chiave
                # primaria, e sotto carico e' esattamente cio' che succede.
                (uuid.uuid4().hex, scope, now),
            )
        backend.commit()
        self._purge_old(backend)

    def register_success(self, client_ip: str, username: str) -> None:
        """Un accesso riuscito azzera il conteggio di quella provenienza.

        Solo gli ambiti legati a questo IP: un accesso legittimo da un'altra
        rete non deve ripulire i tentativi di chi sta bussando altrove.
        """
        backend = self._connection()
        for scope in self._scopes(client_ip, username):
            backend.execute_write("DELETE FROM login_failures WHERE scope = ?", (scope,))
        backend.commit()

    def _purge_old(self, backend) -> None:
        """Le righe fuori finestra non servono piu' a nessuno."""
        backend.execute_write(
            "DELETE FROM login_failures WHERE occurred_at <= ?",
            (time.time() - self._window_seconds(),),
        )
        backend.commit()

    # -- supporto --------------------------------------------------------

    def clear(self) -> None:
        backend = self._connection()
        backend.execute_write("DELETE FROM login_failures", ())
        backend.commit()


login_guard = LoginGuard()
