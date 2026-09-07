"""Astrazione di database per Ermes Knowledge (Fase 2 del piano PostgreSQL)."""

from __future__ import annotations

import logging
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


def _translate_params(sql: str, params: tuple | dict | None, style: str) -> tuple[str, tuple | dict | None]:
    """Traduci i placeholder positional nel formato richiesto dal driver."""
    if style == "qmark" or params is None or "?" not in sql:
        return sql, params
    return "%s".join(sql.split("?")), params


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
            return cur.rowcount

    def execute_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(sql, params or ()).fetchone()
            conn.commit()
            return dict(row) if row else None

    def executemany(self, sql: str, params_seq: list[tuple | dict]) -> int:
        with closing(self._connect()) as conn:
            cur = conn.executemany(sql, params_seq)
            conn.commit()
            return cur.rowcount

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

    def __init__(self, url: str) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._connection = psycopg.connect(url, row_factory=dict_row, autocommit=False)

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
        sql, _ = self._translate(sql, None)
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
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise


def create_backend(url: str | None = None):
    """Crea il backend appropriato in base all'URL."""
    if not url or url.startswith("sqlite"):
        return SqliteBackend(cfg.SQLITE_PATH)
    if url.startswith("postgresql"):
        try:
            return PostgresBackend(url)
        except ImportError:
            logger.warning("psycopg non installato: ripiego su SQLite.")
            return SqliteBackend(cfg.SQLITE_PATH)
    raise ValueError(f"Schema URL non supportato: {url}")
