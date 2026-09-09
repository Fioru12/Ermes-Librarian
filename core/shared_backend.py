"""Base per lo stato che deve essere condiviso fra le istanze.

Sessioni e tentativi di accesso hanno lo stesso requisito: devono esistere
fuori dal singolo processo, altrimenti due istanze dietro un bilanciatore si
comportano come due applicazioni diverse — l'utente viene disconnesso a
richieste alterne, e un limite di dieci tentativi diventa dieci per istanza.

Entrambi si appoggiano allo stesso archivio delle biblioteche, che e' gia'
condiviso, invece di introdurre un componente in piu' da installare.
"""

import threading
from pathlib import Path

import config
from core.database_backend import Backend, SqliteBackend, create_backend


class SharedTableStore:
    """Store legato a una tabella sull'archivio condiviso.

    Le sottoclassi dichiarano `_SCHEMA` (una CREATE TABLE) e, se servono,
    `_INDEXES`.
    """

    _SCHEMA: str = ""
    _INDEXES: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._backend: Backend | None = None
        self._identity: str | None = None

    def _current_identity(self) -> str:
        # `config.cfg` letto a ogni chiamata, non importato una volta: i test
        # sostituiscono l'oggetto di configurazione, e uno store legato a
        # quello visto all'import scriverebbe nel database reale invece che
        # nella directory temporanea del test.
        active = config.cfg
        return active.DATABASE_URL or str(Path(active.LIBRARY_DB_PATH))

    def _connection(self) -> Backend:
        identity = self._current_identity()
        with self._lock:
            if self._backend is None or self._identity != identity:
                active = config.cfg
                self._backend = (
                    create_backend(active.DATABASE_URL)
                    if active.DATABASE_URL
                    else SqliteBackend(active.LIBRARY_DB_PATH)
                )
                self._identity = identity
                self._backend.execute_script(self._SCHEMA)
                for statement in self._INDEXES:
                    self._backend.execute_script(statement)
            return self._backend
