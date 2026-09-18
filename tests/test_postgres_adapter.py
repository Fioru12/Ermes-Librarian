"""L'adapter che PostgresBackend.transaction() consegna a LibraryStore.

Non serve un server: si verifica cio' che arriva al driver. LibraryStore ha
circa cento `connection.execute("... ?", params)` dentro `with
self._connection()`, scritti per sqlite3; psycopg rifiuta `?`. Fino al 18
settembre 2026 transaction() yieldava la connessione psycopg nuda, quindi
ognuna di quelle chiamate falliva su Postgres — e nessun test lo vedeva,
perche' i test di parita' a livello store giravano su SQLite (vedi
tests/test_postgres_parity.py::pg_store).
"""

import sqlite3

from core.database_backend import INTEGRITY_ERRORS, PostgresConnectionAdapter, _translate_params


class _FakeCursor:
    def __init__(self, log):
        self._log = log
        self.description = None
        self.rowcount = 0

    def executemany(self, sql, seq):
        self._log.append(("many", sql, list(seq)))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakePsycopgConnection:
    def __init__(self):
        self.log = []
        self.committed = 0

    def execute(self, sql, params=None):
        if "?" in sql:
            raise AssertionError(f"segnaposto qmark arrivato al driver: {sql}")
        self.log.append(("one", sql, params))
        return _FakeCursor(self.log)

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        self.committed += 1


def _adapter(conn):
    return PostgresConnectionAdapter(conn, lambda sql, params: _translate_params(sql, params, "format"))


def test_qmark_placeholders_are_translated_before_reaching_the_driver():
    conn = _FakePsycopgConnection()
    _adapter(conn).execute("SELECT * FROM libraries WHERE id = ? AND owner_id = ?", ("l1", "u1"))
    assert conn.log == [("one", "SELECT * FROM libraries WHERE id = %s AND owner_id = %s", ("l1", "u1"))]


def test_executemany_is_translated_too():
    conn = _FakePsycopgConnection()
    _adapter(conn).executemany("INSERT INTO t (a, b) VALUES (?, ?)", [(1, 2), (3, 4)])
    assert conn.log == [("many", "INSERT INTO t (a, b) VALUES (%s, %s)", [(1, 2), (3, 4)])]


def test_a_query_without_parameters_is_passed_through_untouched():
    """Un `?` dentro un letterale senza parametri non va toccato."""
    conn = _FakePsycopgConnection()
    _adapter(conn).execute("SELECT 1")
    assert conn.log == [("one", "SELECT 1", None)]


def test_integrity_errors_cover_both_drivers():
    assert sqlite3.IntegrityError in INTEGRITY_ERRORS
    import psycopg

    assert psycopg.IntegrityError in INTEGRITY_ERRORS
    assert issubclass(psycopg.errors.UniqueViolation, INTEGRITY_ERRORS)


def test_named_placeholders_become_pyformat_and_casts_are_left_alone():
    """`VALUES (:id, :name)` con un dict -> `%(id)s, %(name)s`; `::text` resta."""
    conn = _FakePsycopgConnection()
    _adapter(conn).execute(
        "INSERT INTO t (id, name) VALUES (:id, :name) RETURNING embedding_json::text",
        {"id": "x", "name": "y"},
    )
    assert conn.log == [
        (
            "one",
            "INSERT INTO t (id, name) VALUES (%(id)s, %(name)s) RETURNING embedding_json::text",
            {"id": "x", "name": "y"},
        )
    ]
