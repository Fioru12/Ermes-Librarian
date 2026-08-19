from dataclasses import replace

from core import evidence_assistant


def _citations():
    return [{
        "excerpt": "Le ferie vanno richieste cinque giorni prima.",
        "citation": {"filename": "ferie.md", "locator": "Sezione: Ferie"},
    }]


def test_evidence_only_never_calls_a_provider(monkeypatch):
    monkeypatch.setattr(evidence_assistant, "cfg", replace(evidence_assistant.cfg, LIBRARY_ASSISTANT_MODE="evidence_only"))
    monkeypatch.setattr(evidence_assistant, "_call_ollama", lambda _: (_ for _ in ()).throw(AssertionError()))

    answer, coverage, reason = evidence_assistant.answer_from_evidence("Quando ferie?", _citations(), mode="evidence_only")

    assert coverage == "supported"
    assert reason is None
    assert "[1]" in answer


def test_local_answer_keeps_evidence_markers(monkeypatch):
    monkeypatch.setattr(evidence_assistant, "cfg", replace(evidence_assistant.cfg, LIBRARY_ASSISTANT_MODE="local_ollama"))
    monkeypatch.setattr(evidence_assistant, "_call_ollama", lambda _: "Richiedile cinque giorni prima.[1]")

    answer, coverage, reason = evidence_assistant.answer_from_evidence("Quando ferie?", _citations(), mode="local_ollama")

    assert answer.endswith("[1]")
    assert coverage == "supported"
    assert reason is None


def test_provider_failure_falls_back_to_evidence_not_another_provider(monkeypatch):
    monkeypatch.setattr(evidence_assistant, "cfg", replace(evidence_assistant.cfg, LIBRARY_ASSISTANT_MODE="local_ollama"))
    monkeypatch.setattr(evidence_assistant, "_call_ollama", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))

    answer, coverage, reason = evidence_assistant.answer_from_evidence("Quando ferie?", _citations(), mode="local_ollama")

    assert "cinque giorni" in answer
    assert coverage == "supported"
    assert reason is not None


def test_approved_provider_is_explicit_and_keeps_evidence_markers(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(evidence_assistant, "_call_approved_provider", lambda _, name: calls.append(name) or "Richiedile cinque giorni prima.[1]")

    answer, coverage, reason = evidence_assistant.answer_from_evidence(
        "Quando ferie?", _citations(), mode="approved_provider", provider_name="OpenRouter aziendale",
    )

    assert calls == ["OpenRouter aziendale"]
    assert answer.endswith("[1]")
    assert coverage == "supported"
    assert reason is None


def test_answer_without_valid_citation_marker_falls_back(monkeypatch):
    monkeypatch.setattr(evidence_assistant, "cfg", replace(evidence_assistant.cfg, LIBRARY_ASSISTANT_MODE="local_ollama"))
    monkeypatch.setattr(evidence_assistant, "_call_ollama", lambda _: "Le ferie si chiedono in anticipo.")

    answer, coverage, reason = evidence_assistant.answer_from_evidence("Quando ferie?", _citations(), mode="local_ollama")

    assert "[1]" in answer
    assert coverage == "supported"
    assert reason is not None
