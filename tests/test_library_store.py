from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
from api.auth import _verify_api_key
from api.libraries import get_library_store
from config import cfg
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
    resolve_storage_path,
    storage_relative_path,
)
import core.library_store as library_store_module


def test_creates_library_and_lists_documents(tmp_path: Path):
    store = LibraryStore(tmp_path / "knowledge.sqlite3")
    library = store.create_library("Procedure HR", "Policy interne", "shared")

    assert library["name"] == "Procedure HR"
    assert store.list_libraries()[0]["document_count"] == 0

    document = store.add_document(
        library_id=library["id"],
        filename="ferie.md",
        media_type="text/markdown",
        content=b"# Ferie\nProcedura per richiedere ferie.",
        storage_path="/tmp/ferie.md",
        extracted_text="# Ferie\nProcedura per richiedere ferie.",
        chunks=[("# Ferie\nProcedura per richiedere ferie.", "Sezione: Ferie")],
    )

    assert document["status"] == "ready"

    results = store.search_documents(library["id"], "ferie")
    assert results[0]["filename"] == "ferie.md"
    assert "richiedere ferie" in results[0]["excerpt"]
    assert results[0]["citation"]["locator"] == "Sezione: Ferie"
    assert results[0]["citation"]["content_hash"].startswith("sha256:")
    assert results[0]["citation"]["chunk_id"]
    assert results[0]["relevance_score"] > 0
    assert store.search_documents(library["id"], "Come richiedere le ferie")[0]["filename"] == "ferie.md"

    updated = store.replace_document_index(
        library["id"],
        document["id"],
        "Nuova procedura ferie approvata.",
        1,
        [("Nuova procedura ferie approvata.", "Sezione: Approvazione")],
    )
    assert updated["status"] == "ready"
    assert store.search_documents(library["id"], "approvata")[0]["citation"]["locator"] == "Sezione: Approvazione"


def test_local_search_matches_simple_singular_plural_variants(tmp_path: Path):
    store = LibraryStore(tmp_path / "morphology.sqlite3")
    library = store.create_library("Procedure")
    store.add_document(
        library["id"], "ferie.md", "text/markdown", b"ferie", "/tmp/ferie",
        chunks=[("Le richieste vengono inviate cinque giorni prima.", "Sezione: Ferie")],
    )

    results = store.search_documents(library["id"], "Quando invio la richiesta?")

    assert results[0]["citation"]["locator"] == "Sezione: Ferie"


def test_local_search_does_not_treat_common_question_words_as_evidence(tmp_path: Path):
    store = LibraryStore(tmp_path / "abstention.sqlite3")
    library = store.create_library("Procedure")
    store.add_document(
        library["id"], "expense-policy.md", "text/markdown", b"policy", "/tmp/policy",
        chunks=[("The report must include a receipt.", "Section: Expenses")],
    )

    assert store.search_documents(library["id"], "What is the warranty period for customer hardware?") == []

def test_uploading_same_filename_creates_a_new_version(tmp_path: Path):
    store = LibraryStore(tmp_path / "versions.sqlite3")
    library = store.create_library("Qualità")
    first = store.add_document(library["id"], "policy.md", "text/markdown", b"versione uno", "/tmp/v1", chunks=[("versione uno", "Sezione: Uno")])
    second = store.add_document(library["id"], "policy.md", "text/markdown", b"versione due", "/tmp/v2", chunks=[("versione due", "Sezione: Due")])

    assert second["id"] == first["id"]
    assert second["version"] == 2
    assert [version["version"] for version in store.list_document_versions(library["id"], first["id"])] == [2, 1]
    assert len(store.list_documents(library["id"])) == 1
    assert store.list_libraries()[0]["document_count"] == 1


def test_semantic_score_can_return_a_chunk_without_keyword_overlap(tmp_path: Path, monkeypatch):
    store = LibraryStore(tmp_path / "semantic.sqlite3")
    library = store.create_library("Procedure")
    document = store.add_document(
        library["id"], "ferie.md", "text/markdown", b"ferie", "/tmp/ferie",
        chunks=[("Le assenze programmate richiedono approvazione.", "Sezione: Assenze")],
    )
    assert store.store_chunk_embeddings(library["id"], document["id"], [[1.0, 0.0]], "test") == 1
    monkeypatch.setattr(library_store_module, "embed_texts", lambda _: [[1.0, 0.0]])

    results, profile = store.search_with_profile(library["id"], "vacanze")

    assert len(results) == 1
    assert results[0]["citation"]["filename"] == "ferie.md"
    assert profile == {"mode": "hybrid_local", "semantic_indexed_chunks": 1, "semantic_used": True}


def test_keyword_profile_is_reported_without_a_local_vector_index(tmp_path: Path):
    store = LibraryStore(tmp_path / "keyword-profile.sqlite3")
    library = store.create_library("Procedure")
    store.add_document(
        library["id"], "ferie.md", "text/markdown", b"ferie", "/tmp/ferie",
        chunks=[("Le richieste ferie passano dal portale.", "Sezione: Ferie")],
    )

    results, profile = store.search_with_profile(library["id"], "richieste ferie")

    assert results
    assert profile == {"mode": "keyword", "semantic_indexed_chunks": 0, "semantic_used": False}


def test_library_assistant_policy_is_local_by_default_and_persisted(tmp_path: Path):
    store = LibraryStore(tmp_path / "policy.sqlite3")
    library = store.create_library("Risorse umane", owner_id="owner")

    assert library["assistant_mode"] == "evidence_only"
    updated = store.set_assistant_mode(library["id"], "approved_openrouter")

    assert updated["assistant_mode"] == "approved_openrouter"
    assert store.get_library(library["id"])["assistant_mode"] == "approved_openrouter"

    provider_updated = store.set_assistant_policy(library["id"], "approved_provider", "OpenRouter aziendale")
    assert provider_updated["assistant_provider"] == "OpenRouter aziendale"


def test_restored_content_can_be_saved_as_a_new_version(tmp_path: Path):
    store = LibraryStore(tmp_path / "restore.sqlite3")
    library = store.create_library("Manuali")
    first = store.add_document(library["id"], "manuale.md", "text/markdown", b"prima", "/tmp/first", chunks=[("prima", "Sezione: Prima")])
    store.add_document(library["id"], "manuale.md", "text/markdown", b"seconda", "/tmp/second", chunks=[("seconda", "Sezione: Seconda")])
    restored = store.add_document(library["id"], "manuale.md", "text/markdown", b"prima", "/tmp/first", chunks=[("prima", "Sezione: Prima")])

    assert restored["id"] == first["id"]
    assert restored["version"] == 3
    assert [item["version"] for item in store.list_document_versions(library["id"], first["id"])] == [3, 2, 1]


def test_ingestion_job_tracks_success_and_failure(tmp_path: Path):
    store = LibraryStore(tmp_path / "jobs.sqlite3")
    library = store.create_library("Procedure")
    job = store.start_ingestion_job(library["id"], "procedura.md")
    store.finish_ingestion_job(job["id"], "failed", error_message="Parser non disponibile")

    recorded = store.list_ingestion_jobs(library["id"])[0]
    assert recorded["status"] == "failed"
    assert recorded["error_message"] == "Parser non disponibile"


def test_private_library_is_hidden_from_another_user(tmp_path: Path):
    store = LibraryStore(tmp_path / "access.sqlite3")
    library = store.create_library("HR riservato", owner_id="alice")
    bob = {"username": "bob", "role": "editor"}

    assert store.list_libraries(bob) == []
    try:
        store.get_library(library["id"], bob)
    except LibraryAccessError:
        pass
    else:
        raise AssertionError("Expected LibraryAccessError")


def test_library_member_roles_are_enforced_before_access(tmp_path: Path):
    store = LibraryStore(tmp_path / "members.sqlite3")
    library = store.create_library("HR riservato", owner_id="alice")
    bob = {"username": "bob", "role": "viewer"}

    store.set_library_member(library["id"], "bob", "viewer")
    assert store.get_library(library["id"], bob)["access_role"] == "viewer"
    assert store.list_libraries(bob)[0]["id"] == library["id"]
    try:
        store.get_library(library["id"], bob, write=True)
    except LibraryAccessError:
        pass
    else:
        raise AssertionError("A viewer member must not have write access")

    store.set_library_member(library["id"], "bob", "editor")
    assert store.get_library(library["id"], bob, write=True)["access_role"] == "editor"
    assert store.list_library_members(library["id"])[1]["role"] == "editor"

    assert store.remove_library_member(library["id"], "bob") is True
    assert store.list_libraries(bob) == []


def test_unknown_library_is_rejected(tmp_path: Path):
    store = LibraryStore(tmp_path / "knowledge.sqlite3")

    try:
        store.list_documents("missing")
    except LibraryNotFoundError:
        pass
    else:
        raise AssertionError("Expected LibraryNotFoundError")


def test_library_api_creates_and_uploads_a_document(tmp_path: Path, monkeypatch):
    # Il profilo "keyword" richiede che l'ingestion non produca embeddings:
    # quando il modello locale è scaricato (cache .embed_cache) il profilo
    # legittimo diventa "hybrid_local", quindi forziamo il fallback qui sotto
    # per mantenere il test deterministico su qualsiasi macchina.
    monkeypatch.setattr("core.ingestion_service.embed_texts", lambda _texts: [])
    app.dependency_overrides[get_library_store] = lambda: LibraryStore(tmp_path / "api.sqlite3")
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "test", "role": "admin"}
    try:
        client = TestClient(app)
        created = client.post("/api/libraries", json={"name": "Qualità", "visibility": "shared"})
        assert created.status_code == 201
        library = created.json()

        uploaded = client.post(
            f"/api/libraries/{library['id']}/documents",
            files={"file": ("procedura.md", b"# Procedura\nContenuto demo", "text/markdown")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["filename"] == "procedura.md"

        documents = client.get(f"/api/libraries/{library['id']}/documents")
        assert documents.status_code == 200
        assert len(documents.json()["items"]) == 1

        downloaded = client.get(f"/api/libraries/{library['id']}/documents/{documents.json()['items'][0]['id']}/download")
        assert downloaded.status_code == 200
        assert downloaded.content == b"# Procedura\nContenuto demo"

        answer = client.post(f"/api/libraries/{library['id']}/ask", json={"question": "Contenuto demo"})
        assert answer.status_code == 200
        assert answer.json()["status"] == "answered"
        assert answer.json()["evidence"]["coverage"] == "supported"
        assert answer.json()["citations"][0]["filename"] == "procedura.md"
        assert answer.json()["meta"]["retrieval_profile"]["mode"] == "keyword"

        member = client.put(f"/api/libraries/{library['id']}/members", json={"username": "bob", "role": "viewer"})
        assert member.status_code == 200
        assert member.json() == {"username": "bob", "role": "viewer"}
        members = client.get(f"/api/libraries/{library['id']}/members")
        assert members.status_code == 200
        assert {item["username"] for item in members.json()["items"]} == {"test", "bob"}
        assert client.delete(f"/api/libraries/{library['id']}/members/bob").status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_download_is_denied_to_a_non_member_of_a_private_library(tmp_path: Path, monkeypatch):
    """The download endpoint must check membership before serving the file, not after."""
    store = LibraryStore(tmp_path / "download_acl.sqlite3")
    app.dependency_overrides[get_library_store] = lambda: store
    audit_calls: list[tuple] = []
    monkeypatch.setattr("api.libraries.append_audit", lambda *args, **kwargs: audit_calls.append((args, kwargs)))
    try:
        client = TestClient(app)

        app.dependency_overrides[_verify_api_key] = lambda: {"username": "alice", "role": "admin"}
        created = client.post("/api/libraries", json={"name": "HR riservato", "visibility": "private"})
        assert created.status_code == 201
        library_id = created.json()["id"]
        uploaded = client.post(
            f"/api/libraries/{library_id}/documents",
            files={"file": ("policy.md", b"# Policy interna", "text/markdown")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        as_owner = client.get(f"/api/libraries/{library_id}/documents/{document_id}/download")
        assert as_owner.status_code == 200
        assert as_owner.content == b"# Policy interna"

        download_audit_entries = [
            call for call in audit_calls if len(call[0]) >= 2 and call[0][1] == "document_downloaded"
        ]
        assert any(
            call[0][2] == "alice" and call[0][3].get("document_id") == document_id
            for call in download_audit_entries
        )

        # A user with no membership on this library (and no global admin
        # role, which intentionally bypasses per-library ACL) must not be
        # able to tell it exists, let alone read its content — 404, not 403.
        app.dependency_overrides[_verify_api_key] = lambda: {"username": "eve", "role": "viewer"}
        as_stranger = client.get(f"/api/libraries/{library_id}/documents/{document_id}/download")
        assert as_stranger.status_code == 404

        # A viewer explicitly added to the (still private) library can read it.
        app.dependency_overrides[_verify_api_key] = lambda: {"username": "alice", "role": "admin"}
        member = client.put(f"/api/libraries/{library_id}/members", json={"username": "bob", "role": "viewer"})
        assert member.status_code == 200
        app.dependency_overrides[_verify_api_key] = lambda: {"username": "bob", "role": "viewer"}
        as_member = client.get(f"/api/libraries/{library_id}/documents/{document_id}/download")
        assert as_member.status_code == 200
        assert as_member.content == b"# Policy interna"
    finally:
        app.dependency_overrides.clear()


def test_download_of_a_shared_library_is_open_to_any_authenticated_user(tmp_path: Path):
    store = LibraryStore(tmp_path / "download_shared.sqlite3")
    app.dependency_overrides[get_library_store] = lambda: store
    try:
        client = TestClient(app)

        app.dependency_overrides[_verify_api_key] = lambda: {"username": "alice", "role": "admin"}
        created = client.post("/api/libraries", json={"name": "Procedure comuni", "visibility": "shared"})
        assert created.status_code == 201
        library_id = created.json()["id"]
        uploaded = client.post(
            f"/api/libraries/{library_id}/documents",
            files={"file": ("procedura.md", b"# Procedura comune", "text/markdown")},
        )
        document_id = uploaded.json()["id"]

        app.dependency_overrides[_verify_api_key] = lambda: {"username": "carol", "role": "viewer"}
        as_other_user = client.get(f"/api/libraries/{library_id}/documents/{document_id}/download")
        assert as_other_user.status_code == 200
        assert as_other_user.content == b"# Procedura comune"
    finally:
        app.dependency_overrides.clear()


def test_viewer_cannot_change_a_library(tmp_path: Path):
    app.dependency_overrides[get_library_store] = lambda: LibraryStore(tmp_path / "viewer.sqlite3")
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "viewer", "role": "viewer"}
    try:
        client = TestClient(app)
        response = client.post("/api/libraries", json={"name": "Non consentita"})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()

def test_reindex_recomputes_embeddings_instead_of_silently_dropping_them(tmp_path: Path, monkeypatch):
    """Regressione: replace_document_index ricrea i chunk da zero, quindi un
    reindex che non ricalcola gli embedding degrada la biblioteca da
    hybrid_local a keyword senza alcun errore visibile. Il fix chiama
    embed_texts + store_chunk_embeddings dopo la ricostruzione, come fa
    process_ingestion_job: qui verifichiamo che dopo un reindex ogni chunk
    abbia il suo vettore."""
    test_cfg = replace(cfg, BASE_DIR=str(tmp_path), API_KEY="")
    monkeypatch.setattr("api.libraries.cfg", test_cfg)
    vector = [0.1, 0.2, 0.3]
    fake_embed = lambda texts: [vector for _ in texts]  # noqa: E731 — mock deterministico
    monkeypatch.setattr("api.libraries.embed_texts", fake_embed)
    # L'upload lancia process_ingestion_job in background: anche il suo
    # percorso deve restare deterministico su macchine con o senza Ollama.
    monkeypatch.setattr("core.ingestion_service.embed_texts", fake_embed)

    store = LibraryStore(tmp_path / "reindex.sqlite3")
    app.dependency_overrides[get_library_store] = lambda: store
    app.dependency_overrides[_verify_api_key] = lambda: {"username": "test", "role": "admin"}
    try:
        client = TestClient(app)
        created = client.post("/api/libraries", json={"name": "Reindex", "visibility": "private"})
        assert created.status_code == 201
        library_id = created.json()["id"]
        uploaded = client.post(
            f"/api/libraries/{library_id}/documents",
            files={"file": ("policy.md", b"# Policy\nContenuto di prova per il reindex.", "text/markdown")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        reindexed = client.post(f"/api/libraries/{library_id}/documents/{document_id}/reindex")
        assert reindexed.status_code == 200

        with store._connection() as connection:
            rows = connection.execute(
                "SELECT embedding_json FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        assert rows, "il reindex deve ricreare i chunk"
        assert all(row[0] for row in rows), "dopo il reindex ogni chunk deve avere un embedding"
    finally:
        app.dependency_overrides.clear()



class TestStoragePathPortability:
    """The database must not pin documents to the machine that ingested them.

    Absolute paths were being written, so the same SQLite file moved into a
    container (or restored from backup into another directory) kept pointing at
    the original filesystem: every original became unreachable while the rows
    still looked healthy. Found by actually running `docker compose up`.
    """

    def test_new_documents_record_a_relative_location(self):
        assert storage_relative_path("lib-1", "abc_manuale.pdf") == "lib-1/abc_manuale.pdf"
        assert not Path(storage_relative_path("lib-1", "x.pdf")).is_absolute()

    def test_a_relative_location_resolves_under_the_current_root(self, tmp_path):
        resolved = resolve_storage_path("lib-1/abc_manuale.pdf", tmp_path)
        assert resolved == tmp_path / "lib-1" / "abc_manuale.pdf"

    def test_an_absolute_path_that_still_exists_is_kept(self, tmp_path):
        real = tmp_path / "lib-1" / "abc.pdf"
        real.parent.mkdir(parents=True)
        real.write_bytes(b"%PDF-1.7")

        assert resolve_storage_path(str(real), tmp_path) == real

    def test_a_windows_path_from_another_machine_is_re_anchored(self, tmp_path):
        # Seen from Linux this whole string is a single POSIX component, which
        # is exactly why the container could not find any document.
        stored = r"C:\Progetti\ProgettoRAG_DEV\storage\libraries\lib-1\abc_manuale.pdf"

        assert resolve_storage_path(stored, tmp_path) == tmp_path / "lib-1" / "abc_manuale.pdf"

    def test_a_posix_path_from_another_machine_is_re_anchored(self, tmp_path):
        stored = "/srv/ermes/storage/libraries/lib-9/def_policy.md"

        assert resolve_storage_path(stored, tmp_path) == tmp_path / "lib-9" / "def_policy.md"

    def test_resolution_does_not_by_itself_escape_the_storage_root(self, tmp_path):
        # Re-anchoring keeps only the last two segments, so a crafted value
        # cannot climb out of the root through this path.
        resolved = resolve_storage_path("/etc/../../root/.ssh/id_rsa", tmp_path)

        assert tmp_path in resolved.parents or resolved.parent.parent == tmp_path

    def test_an_unreadable_absolute_path_does_not_raise(self, tmp_path, monkeypatch):
        # On Linux, stat() of an unreadable location raises PermissionError
        # instead of returning False. CI caught this; Windows could not.
        def boom(self):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(Path, "is_file", boom)
        resolved = resolve_storage_path("/root/.ssh/lib-1/segreto.pdf", tmp_path)

        assert resolved == tmp_path / "lib-1" / "segreto.pdf"
