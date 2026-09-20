"""Astrazione di database per Ermes Knowledge (Fase 2 del piano PostgreSQL)."""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Protocol

from config import cfg

logger = logging.getLogger(__name__)


class Backend(Protocol):
    """Contratto comune a tutti i backend di persistence."""

    def execute(self, sql: str, params: tuple | dict | None = None) -> list[dict]: ...

    def execute_one(self, sql: str, params: tuple | dict | None = None) -> dict | None: ...

    def execute_write(self, sql: str, params: tuple | dict | None = None) -> int: ...

    def execute_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None: ...

    def executemany(self, sql: str, params_seq: list[tuple | dict]) -> int: ...

    def execute_script(self, sql: str) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...

    @contextmanager
    def transaction(self) -> Iterator[Any]: ...


_NAMED_PARAM = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def _translate_params(sql: str, params: tuple | dict | None, style: str) -> tuple[str, tuple | dict | None]:
    """Traduci i segnaposto sqlite3 nel formato psycopg.

    Positional: `?` -> `%s`. Nominati (parametri in un dict): `:nome` ->
    `%(nome)s`. Il lookbehind esclude `::text` e simili, che sono cast
    Postgres e non segnaposto. Fino al 18 settembre 2026 venivano tradotti
    solo i `?`: le INSERT con `VALUES (:id, :name, ...)` di LibraryStore
    fallivano su Postgres con "syntax error at or near ':'" — la prima run
    dei test di parita' su un Postgres vero l'ha mostrato.
    """
    if style == "qmark" or params is None:
        return sql, params
    if isinstance(params, dict):
        return _NAMED_PARAM.sub(lambda m: "%(" + m.group(1) + ")s", sql), params
    if "?" not in sql:
        return sql, params
    return _qmark_to_format(sql), params


def _qmark_to_format(sql: str) -> str:
    """`?` -> `%s` solo fuori dalle stringhe SQL; `??` resta `?` (operatore).

    `"%s".join(sql.split("?"))` — la versione fino al 21 settembre 2026 —
    avrebbe riscritto un `?` dentro un letterale ('cosa?') e reso
    inutilizzabile l'operatore JSONB `?` di Postgres. Nessuna query lo usa
    oggi; il momento di correggerlo e' prima che una lo faccia.
    """
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            in_string = not in_string
            out.append(ch)
        elif ch == "?" and not in_string:
            if sql.startswith("??", i):
                out.append("?")
                i += 1
            else:
                out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


class SqliteBackend:
    """Wrapper attorno a sqlite3 con lo stesso contratto del protocollo."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        import sqlite3

        conn = sqlite3.connect(str(self._path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def execute(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql, params or ()).fetchall()]

    def execute_one(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(sql, params or ()).fetchone()
            return dict(row) if row else None

    def execute_write(self, sql: str, params: tuple | dict | None = None) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute(sql, params or ())
            conn.commit()
            return int(cur.rowcount)

    def execute_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(sql, params or ()).fetchone()
            conn.commit()
            return dict(row) if row else None

    def executemany(self, sql: str, params_seq: list[tuple | dict]) -> int:
        with closing(self._connect()) as conn:
            cur = conn.executemany(sql, params_seq)
            conn.commit()
            return int(cur.rowcount)

    def execute_script(self, sql: str) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(sql)
            conn.commit()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class PostgresBackend:
    """Wrapper attorno a psycopg 3 con lo stesso contratto del protocollo."""

    # Senza timeout esplicito, psycopg attende indefinitamente: misurato oltre
    # un minuto verso un host irraggiungibile, il che significa
    # un'applicazione appesa all'avvio invece di un errore leggibile. Dieci
    # secondi sono abbondanti per un database raggiungibile e brevi
    # abbastanza da far capire subito che non lo e'.
    _CONNECT_TIMEOUT_SECONDI = 10

    def __init__(self, url: str) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._connection = psycopg.connect(
            url,
            row_factory=dict_row,
            autocommit=False,
            connect_timeout=self._CONNECT_TIMEOUT_SECONDI,
        )

    def _translate(self, sql: str, params: tuple | dict | None) -> tuple[str, tuple | dict | None]:
        return _translate_params(sql, params, "format")

    def execute(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        sql, params = self._translate(sql, params)
        with self._connection.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []

    def execute_one(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        sql, params = self._translate(sql, params)
        with self._connection.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if cur.description else None

    def execute_write(self, sql: str, params: tuple | dict | None = None) -> int:
        sql, params = self._translate(sql, params)
        with self._connection.cursor() as cur:
            cur.execute(sql, params)
            self._connection.commit()
            return cur.rowcount

    def execute_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        sql, params = self._translate(sql, params)
        with self._connection.cursor() as cur:
            cur.execute(sql, params)
            self._connection.commit()
            return cur.fetchone() if cur.description else None

    def executemany(self, sql: str, params_seq: list[tuple | dict]) -> int:
        # Con None _translate non tocca la query (nessun parametro, nessun
        # segnaposto da tradurre): qui i parametri ci sono, sono nella
        # sequenza. Fino al 18 settembre 2026 passava None e `?` arrivava al
        # driver intatto.
        sql, _ = self._translate(sql, ())
        with self._connection.cursor() as cur:
            cur.executemany(sql, params_seq)
            self._connection.commit()
            return cur.rowcount

    def execute_script(self, sql: str) -> None:
        for raw in sql.split(";"):
            lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
            statement = "\n".join(lines).strip()
            if statement:
                self._connection.execute(statement)
        self._connection.commit()

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self):
        # Yielda l'ADAPTER, non la connessione psycopg. LibraryStore ha un
        # centinaio di `connection.execute("... ?", params)` scritti per
        # SQLite dentro `with self._connection()`; psycopg rifiuta `?`
        # ("the query has 0 placeholders"). La docstring di
        # LibraryStore._connection prometteva "Postgres: restituisce un
        # adapter dict-based" dal primo giorno, ma fino al 18 settembre 2026
        # qui usciva la connessione nuda — e i test di parita' che avrebbero
        # dovuto accorgersene giravano su SQLite senza saperlo (vedi
        # tests/test_postgres_parity.py, fixture pg_store).
        adapter = PostgresConnectionAdapter(self._connection, self._translate)
        try:
            yield adapter
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise


class PostgresConnectionAdapter:
    """La superficie di `sqlite3.Connection` che LibraryStore usa, su psycopg.

    `execute` traduce `?` in `%s` e restituisce il cursore psycopg, che ha
    `fetchone`/`fetchall`/`rowcount` come quello di sqlite3; le righe sono
    dict (row_factory=dict_row), accessibili per nome come sqlite3.Row.
    """

    def __init__(self, connection, translate) -> None:
        self._connection = connection
        self._translate = translate

    def execute(self, sql: str, params: tuple | dict | None = None):
        sql, params = self._translate(sql, params)
        return self._connection.execute(sql, params)

    def executemany(self, sql: str, params_seq) -> None:
        sql, _ = self._translate(sql, ())
        with self._connection.cursor() as cur:
            cur.executemany(sql, list(params_seq))

    def executescript(self, sql: str) -> None:
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                self._connection.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()


def integrity_errors() -> tuple[type[Exception], ...]:
    """Le eccezioni di vincolo violato, per entrambi i driver.

    `except sqlite3.IntegrityError` su Postgres lasciava passare
    psycopg.IntegrityError: un nome utente duplicato diventava un 500 invece
    del 409 previsto.
    """
    tipi: list[type[Exception]] = [sqlite3.IntegrityError]
    try:
        import psycopg

        tipi.append(psycopg.IntegrityError)
    except ImportError:
        pass
    return tuple(tipi)


INTEGRITY_ERRORS = integrity_errors()


def create_backend(url: str | None = None):
    """Crea il backend appropriato in base all'URL."""
    if not url or url.startswith("sqlite"):
        return SqliteBackend(cfg.SQLITE_PATH)
    if url.startswith("postgresql"):
        try:
            return PostgresBackend(url)
        except ImportError as errore:
            # Fail closed. Il codice precedente registrava un avviso e
            # ripiegava su SQLite: chi imposta ERMES_DATABASE_URL lo fa per
            # spostare i dati su un database condiviso, tipicamente per servire
            # piu' istanze. Ripiegare in silenzio significa che ogni istanza
            # continua a usare il proprio file locale, quindi dati e sessioni
            # non sono condivisi — il difetto peggiore possibile, presentato
            # come funzionante. Meglio non partire.
            raise RuntimeError(
                "ERMES_DATABASE_URL punta a PostgreSQL ma il driver psycopg non e' installato. "
                "Installa le dipendenze con `pip install -r requirements.txt`. "
                "Il ripiego automatico su SQLite non viene piu' fatto: userebbe un database "
                "locale per istanza mentre la configurazione chiede il contrario."
            ) from errore
    raise ValueError(f"Schema URL non supportato: {url}")
