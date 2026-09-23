"""tests/test_postgres_migration.py
Test suite per la migrazione da SQLite a PostgreSQL (Fase 5) e per lo script CLI.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from core.library_store import LibraryStore
from scripts.migrate_sqlite_to_postgres import (
    _get_sqlite_columns,
    migrate_table,
    verify_migration,
)


def test_get_sqlite_columns(tmp_path: Path):
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, age INTEGER)")
        cur = conn.cursor()
        cols = _get_sqlite_columns(cur, "users")
        assert cols == ["id", "name", "age"]


def test_migrate_table_with_mocked_pg(tmp_path: Path):
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE libraries (id TEXT PRIMARY KEY, name TEXT, description TEXT)")
        conn.execute("INSERT INTO libraries VALUES ('lib-1', 'Biblioteca 1', 'Desc 1')")
        conn.execute("INSERT INTO libraries VALUES ('lib-2', 'Biblioteca 2', 'Desc 2')")

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.row_factory = sqlite3.Row

    # Mock PostgreSQL Connection
    mock_pg = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"column_name": "id"},
        {"column_name": "name"},
        {"column_name": "description"},
    ]
    mock_cur.rowcount = 2
    mock_pg.cursor.return_value.__enter__.return_value = mock_cur

    migrated, skipped = migrate_table(
        sqlite_conn=sqlite_conn,
        pg_conn=mock_pg,
        table_name="libraries",
        batch_size=10,
        clean_target=False,
    )

    assert migrated == 2
    assert skipped == 0
    mock_cur.executemany.assert_called_once()
    sqlite_conn.close()


def test_migrate_table_jsonb_handling(tmp_path: Path):
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE document_chunks (id TEXT PRIMARY KEY, embedding_json TEXT)")
        conn.execute("INSERT INTO document_chunks VALUES ('c1', '[0.1, 0.2, 0.3]')")
        conn.execute("INSERT INTO document_chunks VALUES ('c2', NULL)")
        conn.execute("INSERT INTO document_chunks VALUES ('c3', 'invalid-json')")

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.row_factory = sqlite3.Row

    mock_pg = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"column_name": "id"},
        {"column_name": "embedding_json"},
    ]
    mock_cur.rowcount = 3
    mock_pg.cursor.return_value.__enter__.return_value = mock_cur

    migrated, skipped = migrate_table(
        sqlite_conn=sqlite_conn,
        pg_conn=mock_pg,
        table_name="document_chunks",
        batch_size=10,
    )

    assert migrated == 3
    call_args = mock_cur.executemany.call_args[0]
    sql, batch = call_args[0], call_args[1]
    assert "INSERT INTO document_chunks" in sql
    assert len(batch) == 3
    assert batch[0] == ("c1", "[0.1, 0.2, 0.3]")
    assert batch[1] == ("c2", "null")
    assert batch[2] == ("c3", "null")
    sqlite_conn.close()


def test_verify_migration_comparison(tmp_path: Path):
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE libraries (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO libraries VALUES ('lib-1')")

    sqlite_conn = sqlite3.connect(str(db_file))
    sqlite_conn.row_factory = sqlite3.Row

    mock_pg = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {"count": 1}
    mock_pg.cursor.return_value.__enter__.return_value = mock_cur

    stats = verify_migration(sqlite_conn, mock_pg)
    assert "libraries" in stats
    assert stats["libraries"]["sqlite_count"] == 1
    assert stats["libraries"]["postgres_count"] == 1
    assert stats["libraries"]["matched"] is True
    sqlite_conn.close()


def test_claim_next_ingestion_job_postgres_skip_locked(monkeypatch):
    """Verifica che claim_next_ingestion_job esegua la query con FOR UPDATE SKIP LOCKED su Postgres."""
    store = LibraryStore.__new__(LibraryStore)
    store._is_postgres = True
    mock_backend = MagicMock()
    mock_backend.execute_returning.return_value = {
        "id": "job-123",
        "library_id": "lib-1",
        "status": "processing",
        "filename": "doc.pdf",
    }
    store._backend = mock_backend

    claimed = store.claim_next_ingestion_job(worker_id="worker-1")
    assert claimed is not None
    assert claimed["id"] == "job-123"
    assert claimed["status"] == "processing"

    mock_backend.execute_returning.assert_called_once()
    sql = mock_backend.execute_returning.call_args[0][0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "UPDATE ingestion_jobs" in sql
