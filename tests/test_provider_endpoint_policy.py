import pytest
from fastapi import HTTPException

from api.providers import validate_provider_base_url


def test_provider_endpoint_policy_allows_only_approved_hosts_over_safe_transport():
    assert validate_provider_base_url("https://openrouter.ai/api/v1/") == "https://openrouter.ai/api/v1"
    assert validate_provider_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


@pytest.mark.parametrize("url", [
    "http://openrouter.ai/api/v1",
    "http://169.254.169.254/latest/meta-data",
    "https://unapproved.example.test/v1",
    "file:///etc/passwd",
    "https://user:password@openrouter.ai/v1",
])
def test_provider_endpoint_policy_rejects_unapproved_or_unsafe_urls(url):
    with pytest.raises(HTTPException):
        validate_provider_base_url(url)
