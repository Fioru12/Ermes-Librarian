"""Parità schema SQLite <-> PostgreSQL (Fase 1 del piano PG).

Gira live contro il container `ermes-pg` (postgres:16-alpine su :5433).
Se il database non è raggiungibile, i test vengono saltati con una
ragione chiara: la parità va verificata, non presunta.
"""

import functools

import pytest

from core.postgres_backend import DEFAULT_PG_DSN, EXPECTED_TABLES, connect, ensure_schema

pytestmark = pytest.mark.postgres


@functools.cache
def _pg_available() -> bool:
    """Sondaggio con timeout breve, non quello di produzione.

    Con i 10 secondi predefiniti — e psycopg che tenta IPv6 e poi IPv4 — questo
    controllo impiegava venti secondi ogni volta che PostgreSQL non c'e', cioe'
    sempre in locale. Un sondaggio vuole fallire in fretta; una connessione
    vera vuole il margine.
    """
    try:
        connection = connect(DEFAULT_PG_DSN, timeout=2)
    except Exception:
        return False
    connection.close()
    return True


@pytest.fixture
def _richiede_postgres():
    """Il sondaggio avviene qui, non all'import del modulo.

    Era `pytest.mark.skipif(not _pg_available(), ...)`, che valuta la
    condizione mentre pytest raccoglie i test: la connessione partiva prima di
    qualunque test, in ogni esecuzione della suite, anche filtrando su un
    altro file. Su Windows, senza un server in ascolto, psycopg fa cadere
    l'interprete a intermittenza durante quel sondaggio ("Windows fatal
    exception: access violation" dentro il selector), e la suite muore in
    raccolta invece di dire quanti test sono passati. Rinviarlo al primo test
    che ne ha bisogno lo evita del tutto quando questi test si saltano, e
    `functools.cache` mantiene un solo tentativo per sessione.
    """
    if not _pg_available():
        pytest.skip("PostgreSQL non raggiungibile su localhost:5433")


requires_pg = pytest.mark.usefixtures("_richiede_postgres")


@pytest.fixture()
def pg_connection():
    connection = connect(DEFAULT_PG_DSN)
    ensure_schema(connection)
    # Schema pulito per ogni test: ordine di cancellazione inverso alle FK.
    yield connection
    connection.rollback()
    for table in [
        "chat_integrations",
        "import_sources",
        "ingestion_jobs",
        "document_acls",
        "document_versions",
        "document_chunks",
        "library_members",
        "documents",
        "libraries",
    ]:
        connection.execute(f"DELETE FROM {table}")
    connection.commit()
    connection.close()


@requires_pg
def test_schema_contains_all_sqlite_tables(pg_connection):
    rows = pg_connection.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    tables = {row["tablename"] for row in rows}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Tabelle mancanti in PG: {missing}"


@requires_pg
def test_role_check_constraint_enforced(pg_connection):
    """Il vincolo CHECK su library_members.role deve valere anche in PG."""
    now = "2026-09-06T10:00:00+00:00"
    pg_connection.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
        ("lib-check", "Test", now, now),
    )
    with pytest.raises(Exception):
        pg_connection.execute(
            "INSERT INTO library_members (library_id, username, role, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            ("lib-check", "carol", "admin", now, now),
        )
    pg_connection.rollback()


@requires_pg
def test_cascade_delete_documents(pg_connection):
    """ON DELETE CASCADE documents->chunks come in SQLite."""
    now = "2026-09-06T10:00:00+00:00"
    pg_connection.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
        ("lib-casc", "Test", now, now),
    )
    pg_connection.execute(
        "INSERT INTO documents (id, library_id, filename, size_bytes, content_hash, storage_path, created_at, updated_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        ("doc-1", "lib-casc", "a.txt", 10, "h", "lib-casc/a.txt", now, now),
    )
    pg_connection.execute(
        "INSERT INTO document_chunks (id, document_id, ordinal, text, created_at) VALUES (%s, %s, %s, %s, %s)",
        ("ch-1", "doc-1", 0, "Il contratto scade a dicembre.", now),
    )
    pg_connection.commit()
    pg_connection.execute("DELETE FROM documents WHERE id = 'doc-1'")
    pg_connection.commit()
    remaining = pg_connection.execute(
        "SELECT COUNT(*) AS n FROM document_chunks WHERE document_id = 'doc-1'"
    ).fetchone()
    assert remaining["n"] == 0


@requires_pg
def test_fts_generated_column_matches_simple_tokenizer(pg_connection):
    """La colonna search_tsv sostituisce FTS5: la ricerca full-text di base
    deve trovare i chunk per parola, indipendentemente dal casing."""
    now = "2026-09-06T10:00:00+00:00"
    pg_connection.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
        ("lib-fts", "Test", now, now),
    )
    pg_connection.execute(
        "INSERT INTO documents (id, library_id, filename, size_bytes, content_hash, storage_path, created_at, updated_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        ("doc-fts", "lib-fts", "policy.txt", 10, "h", "lib-fts/policy.txt", now, now),
    )
    pg_connection.execute(
        "INSERT INTO document_chunks (id, document_id, ordinal, text, created_at) VALUES (%s, %s, %s, %s, %s)",
        ("ch-fts", "doc-fts", 0, "La pausa pranzo dura sessanta minuti.", now),
    )
    pg_connection.commit()
    hits = pg_connection.execute(
        "SELECT id FROM document_chunks WHERE search_tsv @@ plainto_tsquery('simple', 'pausa PRANZO')"
    ).fetchall()
    assert [h["id"] for h in hits] == ["ch-fts"]


@requires_pg
def test_embedding_jsonb_roundtrip(pg_connection):
    now = "2026-09-06T10:00:00+00:00"
    pg_connection.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) VALUES (%s, %s, %s, %s)",
        ("lib-emb", "Test", now, now),
    )
    pg_connection.execute(
        "INSERT INTO documents (id, library_id, filename, size_bytes, content_hash, storage_path, created_at, updated_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        ("doc-emb", "lib-emb", "a.txt", 10, "h", "lib-emb/a.txt", now, now),
    )
    pg_connection.execute(
        "INSERT INTO document_chunks (id, document_id, ordinal, text, embedding_json, created_at)"
        " VALUES (%s, %s, %s, %s, %s::jsonb, %s)",
        ("ch-emb", "doc-emb", 0, "test", "[0.1, 0.2, 0.3]", now),
    )
    pg_connection.commit()
    row = pg_connection.execute("SELECT embedding_json FROM document_chunks WHERE id = 'ch-emb'").fetchone()
    assert row["embedding_json"] == [0.1, 0.2, 0.3]  # psycopg decodifica JSONB nativamente


# ============================================================
# Fase 2: dual-backend LibraryStore live su PostgreSQL
# ============================================================

import os as _os


@pytest.fixture()
def pg_store(tmp_path):
    """LibraryStore con backend PostgreSQL (DATABASE_URL pointing to test container)."""
    dsn = _os.environ.get("ERMES_TEST_DATABASE_URL", DEFAULT_PG_DSN)
    if not _pg_available():
        pytest.skip("PostgreSQL non raggiungibile")
    from core.database_backend import PostgresBackend

    backend = PostgresBackend(dsn)
    from core.postgres_backend import POSTGRES_SCHEMA

    backend.execute_script(POSTGRES_SCHEMA)
    backend.close()
    from core.library_store import LibraryStore

    # Fino al 18 settembre 2026 questo fixture impostava ERMES_DATABASE_URL
    # nell'ambiente e costruiva `LibraryStore(database_path=None)`. Ma `cfg`
    # e' un frozen dataclass letto all'import: la variabile arrivava troppo
    # tardi, cfg.DATABASE_URL restava vuoto e lo store apriva SQLite. Tre
    # test "PostgreSQL" passavano in CI su SQLite, mentre su Postgres vero
    # ogni `connection.execute("... ?")` dello store falliva. L'asserzione
    # sotto impedisce che succeda di nuovo.
    store = LibraryStore(database_url=dsn)
    assert store._is_postgres, "il fixture pg_store deve usare PostgreSQL, non SQLite"
    yield store


@requires_pg
def test_pg_library_crud(pg_store):
    """CRUD base su biblioteche via backend PostgreSQL."""
    lib = pg_store.create_library("Test PG", "desc", "private", owner_id="owner")
    assert lib["name"] == "Test PG"
    fetched = pg_store.get_library(lib["id"])
    assert fetched["id"] == lib["id"]


@requires_pg
def test_pg_search_with_profile(pg_store):
    """La ricerca full-text via tsvector trova i chunk correttamente."""
    lib = pg_store.create_library("Search PG", "", "private", owner_id="owner")
    _doc = pg_store.add_document(
        library_id=lib["id"],
        filename="policy.txt",
        media_type="text/plain",
        content=b"La pausa pranzo dura sessanta minuti.",
        storage_path="policy.txt",
        status="ready",
        chunks=["La pausa pranzo dura sessanta minuti."],
    )
    results, profile = pg_store.search_with_profile(lib["id"], "pausa pranzo")
    assert len(results) == 1
    assert results[0]["citation"]["filename"] == "policy.txt"
    assert profile["mode"] == "keyword"


@requires_pg
def test_pg_search_case_insensitive(pg_store):
    """La ricerca tsvector è case-insensitive (config 'simple')."""
    lib = pg_store.create_library("Case PG", "", "private", owner_id="owner")
    pg_store.add_document(
        library_id=lib["id"],
        filename="doc.txt",
        media_type="text/plain",
        content=b"Procedura di Sicurezza.",
        storage_path="doc.txt",
        status="ready",
        chunks=["Procedura di Sicurezza."],
    )
    results, _ = pg_store.search_with_profile(lib["id"], "SICUREZZA")
    assert len(results) == 1


# ============================================================
# Driver assente: non si ripiega in silenzio
# ============================================================


def test_a_missing_driver_refuses_instead_of_falling_back_to_sqlite(monkeypatch):
    """Il codice precedente registrava un avviso e usava SQLite.

    Chi imposta ERMES_DATABASE_URL lo fa per spostare i dati su un database
    condiviso, tipicamente per servire piu' istanze. Ripiegare in silenzio
    significa che ogni istanza continua a usare il proprio file locale: dati e
    sessioni non condivisi, con la configurazione che dice il contrario. E'
    il difetto peggiore possibile, perche' si presenta come funzionante.

    Questo test non richiede PostgreSQL: simula l'assenza del driver.
    """
    import builtins

    import pytest as _pytest

    from core.database_backend import create_backend

    importa_vero = builtins.__import__

    def senza_psycopg(nome, *args, **kwargs):
        if nome == "psycopg" or nome.startswith("psycopg."):
            raise ImportError("psycopg assente (simulato)")
        return importa_vero(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", senza_psycopg)

    with _pytest.raises(RuntimeError) as errore:
        create_backend("postgresql://postgres:x@localhost:5433/qualsiasi")

    messaggio = str(errore.value)
    assert "psycopg" in messaggio
    assert "SQLite" in messaggio, "il messaggio deve spiegare perche' il ripiego non viene fatto"


def test_the_connection_has_an_explicit_timeout():
    """Senza timeout psycopg attende indefinitamente: misurato oltre un minuto
    verso un host irraggiungibile, cioe' un'applicazione appesa all'avvio
    invece di un errore leggibile."""
    from core.database_backend import PostgresBackend

    assert getattr(PostgresBackend, "_CONNECT_TIMEOUT_SECONDI", 0) > 0
    assert PostgresBackend._CONNECT_TIMEOUT_SECONDI <= 30, "un timeout lungo riporta il problema che risolve"


# ============================================================
# I percorsi `with self._connection()` — quelli scritti con `?` — su Postgres
# ============================================================


@requires_pg
def test_pg_document_lifecycle_through_raw_connection_paths(pg_store):
    """add_document, list, replace_document_index, versioni, members, delete:
    tutti passano da `_connection()` con segnaposto `?`. Prima
    dell'adapter ognuno di questi falliva con "the query has 0
    placeholders"."""
    lib = pg_store.create_library("Ciclo PG", "", "private", owner_id="owner")
    doc = pg_store.add_document(
        library_id=lib["id"],
        filename="ferie.md",
        media_type="text/markdown",
        content=b"Le ferie vanno richieste con 15 giorni di anticipo.",
        storage_path=f"{lib['id']}/ferie.md",
        status="ready",
        chunks=[("Le ferie vanno richieste con 15 giorni di anticipo.", "Sezione: Ferie")],
    )
    assert [d["id"] for d in pg_store.list_documents(lib["id"])] == [doc["id"]]

    results, _ = pg_store.search_with_profile(lib["id"], "ferie anticipo")
    assert results and results[0]["citation"]["locator"] == "Sezione: Ferie"

    aggiornato = pg_store.replace_document_index(
        lib["id"],
        doc["id"],
        "Le ferie vanno richieste con 30 giorni di anticipo.",
        1,
        [("Le ferie vanno richieste con 30 giorni di anticipo.", "Sezione: Ferie")],
    )
    assert aggiornato["status"] == "ready"
    results, _ = pg_store.search_with_profile(lib["id"], "ferie anticipo")
    assert "30 giorni" in results[0]["excerpt"]

    pg_store.set_library_member(lib["id"], "collega", "viewer")
    assert pg_store.get_library(lib["id"], {"username": "collega", "role": "viewer"})["id"] == lib["id"]

    pg_store.delete_document(lib["id"], doc["id"])
    assert pg_store.list_documents(lib["id"]) == []
    pg_store.delete_library(lib["id"])


@requires_pg
def test_pg_duplicate_member_is_an_integrity_error_not_a_500(pg_store):
    """`except sqlite3.IntegrityError` non cattura psycopg.IntegrityError."""
    lib = pg_store.create_library("Vincoli PG", "", "private", owner_id="owner")
    pg_store.set_library_member(lib["id"], "collega", "viewer")
    # La seconda scrittura e' un upsert o un errore gestito: mai un'eccezione
    # del driver che risale fino alla rotta.
    pg_store.set_library_member(lib["id"], "collega", "editor")
    pg_store.delete_library(lib["id"])
