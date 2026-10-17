"""CSP: l'interfaccia non deve poter caricare nulla da altri domini."""

from fastapi.testclient import TestClient

from api import app
from api.security_headers import content_security_policy


def test_the_app_policy_allows_only_this_origin_for_scripts_fonts_and_connections():
    policy = content_security_policy("/")
    assert "script-src 'self'" in policy
    assert "font-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "https://" not in policy, "nessun dominio esterno nella politica dell'interfaccia"
    assert "'unsafe-eval'" not in policy
    assert "script-src 'self' 'unsafe-inline'" not in policy


def test_only_the_generated_api_docs_may_load_from_the_cdn():
    assert "cdn.jsdelivr.net" in content_security_policy("/docs")
    assert "cdn.jsdelivr.net" in content_security_policy("/redoc")
    assert "cdn.jsdelivr.net" not in content_security_policy("/api/libraries")
    assert "cdn.jsdelivr.net" not in content_security_policy("/docsx")


def test_every_response_carries_the_policy():
    client = TestClient(app)
    assert "script-src 'self'" in client.get("/health").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in client.get("/docs").headers["content-security-policy"]
