"""Studio di una biblioteca (core/library_studio.py).

Il modello e' sostituito: qui si verifica cio' che Ermes garantisce attorno a
lui — punti senza citazione scartati, documenti riservati fuori dal prompt,
domande suggerite tenute solo se trovano evidenza, nessun ripiego su un
fornitore diverso da quello scelto per la biblioteca.
"""

import pytest

import config
import core.library_studio as studio
from core.library_store import LibraryStore


def _library(tmp_path, mode="local_ollama", db_path=None) -> tuple[LibraryStore, dict]:
    store = LibraryStore(db_path or tmp_path / "s.sqlite3")
    library = store.create_library("Amministrazione", "", "private", owner_id="alice")
    for name, text in (
        ("nota-spese.md", "La nota spese va consegnata entro il quinto giorno lavorativo del mese successivo."),
        ("anticipi.md", "Un anticipo trasferta si richiede almeno sette giorni prima della partenza."),
    ):
        store.add_document(
            library["id"], name, "text/markdown", text.encode(), f"x/{name}", chunks=[(text, "Sezione 1")]
        )
    store.set_assistant_mode(library["id"], mode)
    return store, store.get_library(library["id"])


@pytest.fixture
def fake_model(monkeypatch):
    calls: list[dict] = []

    def install(reply: str):
        def generate(prompt, mode, provider_name=""):
            calls.append({"prompt": prompt, "mode": mode})
            return reply

        monkeypatch.setattr(studio, "_genera", generate)
        return calls

    return install


def test_points_without_a_valid_citation_are_dropped(tmp_path, fake_model):
    store, library = _library(tmp_path)
    fake_model(
        "La nota spese si consegna entro il quinto giorno lavorativo. [1]\n\n"
        "I rimborsi arrivano in 48 ore.\n\n"  # nessuna citazione: inventato
        "Gli anticipi vanno chiesti una settimana prima. [9]"  # passaggio inesistente
    )

    result = studio.genera_studio(store, library, "briefing", None)

    assert result["status"] == "answered"
    assert [item["text"] for item in result["items"]] == ["La nota spese si consegna entro il quinto giorno lavorativo."]
    assert result["discarded"] == 2
    # Solo il passaggio citato compare fra le fonti.
    assert [s["marker"] for s in result["sources"]] == [1]


def test_faq_and_study_guide_are_parsed_into_cited_items(tmp_path, fake_model):
    store, library = _library(tmp_path)
    fake_model("D: Quando consegno la nota spese? [1]\nR: Entro il quinto giorno lavorativo. [1]")
    faq = studio.genera_studio(store, library, "faq", None)
    assert faq["items"] == [
        {"question": "Quando consegno la nota spese?", "text": "Entro il quinto giorno lavorativo.", "citations": [1]}
    ]

    fake_model("## Scadenze\n- Nota spese entro il quinto giorno [1]\n## Anticipi\n- Sette giorni prima [2]")
    guide = studio.genera_studio(store, library, "study_guide", None)
    assert [(i["section"], i["citations"]) for i in guide["items"]] == [("Scadenze", [1]), ("Anticipi", [2])]


def test_suggested_questions_are_kept_only_if_retrieval_finds_evidence(tmp_path, fake_model):
    store, library = _library(tmp_path)
    fake_model("- Entro quando va consegnata la nota spese? [1]\n- Qual e' il menu della mensa aziendale?")

    result = studio.genera_studio(store, library, "questions", None)

    assert [i["text"] for i in result["items"]] == ["Entro quando va consegnata la nota spese?"]
    assert result["discarded"] == 1


def test_evidence_only_library_never_reaches_a_model(tmp_path, fake_model):
    store, library = _library(tmp_path, mode="evidence_only")
    calls = fake_model("qualunque cosa [1]")

    result = studio.genera_studio(store, library, "briefing", None)

    assert result["status"] == "unavailable"
    assert calls == []


def test_restricted_documents_stay_out_of_the_prompt(tmp_path, fake_model):
    store, library = _library(tmp_path)
    riservato = store.add_document(
        library["id"],
        "stipendi.md",
        "text/markdown",
        b"Gli stipendi dei dirigenti sono riservati.",
        "x/stipendi.md",
        chunks=[("Gli stipendi dei dirigenti sono riservati.", "Sezione 1")],
    )
    store.set_library_member(library["id"], "bob", "viewer")
    store.set_document_acl(library["id"], riservato["id"], ["carol"])
    calls = fake_model("Nota spese entro il quinto giorno. [1]")

    studio.genera_studio(store, library, "briefing", {"username": "bob", "role": "viewer"})

    assert "stipendi" not in calls[0]["prompt"]
    assert "nota-spese.md" in calls[0]["prompt"]


def test_the_librarys_provider_is_used_and_nothing_else(tmp_path, fake_model):
    store, library = _library(tmp_path, mode="approved_openrouter")
    calls = fake_model("Nota spese entro il quinto giorno. [1]")
    studio.genera_studio(store, library, "briefing", None)
    assert calls[0]["mode"] == "approved_openrouter"


def test_openrouter_without_cloud_consent_is_unavailable_not_rerouted(tmp_path, monkeypatch):
    store, library = _library(tmp_path, mode="approved_openrouter")
    monkeypatch.setattr(config, "cfg", config.cfg.replace(LIBRARY_CLOUD_CONSENT=False, OPENROUTER_API_KEY="k"))

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("nessuna chiamata di rete senza consenso")

    monkeypatch.setattr(studio.httpx, "post", must_not_be_called)

    result = studio.genera_studio(store, library, "briefing", None)

    assert result["status"] == "unavailable"


def test_passages_are_spread_across_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "_MAX_PASSAGGI", 2)
    store, library = _library(tmp_path)
    store.add_document(
        library["id"],
        "lungo.md",
        "text/markdown",
        b"x",
        "x/lungo.md",
        chunks=[(f"Paragrafo lungo numero {i}.", f"S{i}") for i in range(10)],
    )
    passaggi = studio.raccogli_passaggi(store, library["id"], None)
    assert len({p.filename for p in passaggi}) == 2


def test_unknown_kind_is_rejected(tmp_path):
    store, library = _library(tmp_path)
    with pytest.raises(ValueError):
        studio.genera_studio(store, library, "podcast", None)


def test_studio_route_respects_library_access(tmp_path, monkeypatch, fake_model):
    from fastapi.testclient import TestClient

    import api.auth
    import api.libraries
    from api import app

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="", API_KEY="chiave-di-test-studio-7c1")
    for module in (config, api.auth, api.libraries):
        monkeypatch.setattr(module, "cfg", test_cfg)
    store, library = _library(tmp_path, db_path=test_cfg.LIBRARY_DB_PATH)
    monkeypatch.setattr(api.libraries, "_store", store)
    fake_model("Nota spese entro il quinto giorno. [1]")
    client = TestClient(app)

    ok = client.post(
        f"/api/libraries/{library['id']}/studio/briefing",
        headers={"Authorization": "Bearer chiave-di-test-studio-7c1"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "answered"

    assert client.post(f"/api/libraries/{library['id']}/studio/briefing").status_code == 401
    assert (
        client.post(
            f"/api/libraries/{library['id']}/studio/podcast",
            headers={"Authorization": "Bearer chiave-di-test-studio-7c1"},
        ).status_code
        == 422
    )
