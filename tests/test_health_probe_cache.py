"""La sonda di Ollama e' memorizzata per pochi secondi, ma solo se ha riuscito."""

import httpx

from api import health


class _Risposta:
    def raise_for_status(self):
        return None

    def json(self):
        return {"models": [{"name": "qwen3.5:4b"}]}


def test_a_successful_probe_is_reused_within_the_ttl(monkeypatch):
    chiamate = []

    def finto(url, timeout):
        chiamate.append(url)
        return _Risposta()

    monkeypatch.setattr(health.httpx, "get", finto)

    primo = health._ollama_models()
    secondo = health._ollama_models()

    assert primo == secondo == (True, {"qwen3.5:4b"}, "Ollama raggiungibile")
    assert len(chiamate) == 1


def test_a_failure_is_not_cached_so_recovery_shows_immediately(monkeypatch):
    stato = {"giu": True}

    def finto(url, timeout):
        if stato["giu"]:
            raise httpx.ConnectError("giu")
        return _Risposta()

    monkeypatch.setattr(health.httpx, "get", finto)

    assert health._ollama_models()[0] is False
    stato["giu"] = False
    assert health._ollama_models()[0] is True
