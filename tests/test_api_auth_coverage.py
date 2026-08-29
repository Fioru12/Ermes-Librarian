"""Regression guard: every product API route requires authentication.

Prompted by the team audit finding that api/documents.py (now isolated in
legacy_winsarp/) had no per-route auth check at all. This walks the live
FastAPI route table instead of grepping source, so it also catches an
endpoint that "looks" guarded but wires the dependency wrong.
"""
from api import app
from api.auth import _verify_api_key

# Routes that are intentionally public, or serve a login/discovery purpose
# where requiring auth would be circular or pointless.
PUBLIC_PATHS = {
    ("GET", "/health"),
    ("GET", "/v1/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/v1/api/auth/login"),
    # Logout only ever clears the cookie the caller already holds and
    # always returns success, including for an already-invalid session —
    # requiring auth here would be circular, not safer.
    ("POST", "/api/auth/logout"),
    ("POST", "/v1/api/auth/logout"),
    ("GET", "/openapi.json"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("GET", "/metrics"),
    # The SPA catch-all that serves the compiled frontend shell (index.html
    # and static assets) — no application data, must be reachable pre-login.
    ("GET", "/{full_path:path}"),
    # Slack/Teams webhooks: the caller is Slack or Teams, not an Ermes user —
    # there is no session or API key to present. Authentication here is the
    # platform's own request signature (HMAC), checked inside the handler
    # against a channel explicitly bound to one library by that library's
    # owner (see api/libraries.py: add_library_chat_integration). Requiring
    # _verify_api_key would make the route unreachable by design, not safer.
    ("POST", "/api/integrations/slack"),
    ("POST", "/v1/api/integrations/slack"),
    ("POST", "/api/integrations/teams"),
    ("POST", "/v1/api/integrations/teams"),
}


def _dependency_tree_calls(dependant, seen=None):
    """Recursively collect every dependency callable in this route's tree."""
    if seen is None:
        seen = set()
    if id(dependant) in seen:
        return []
    seen.add(id(dependant))
    calls = [dependant.call] if dependant.call else []
    for sub in dependant.dependencies:
        calls.extend(_dependency_tree_calls(sub, seen))
    return calls


def test_every_product_route_requires_authentication():
    unguarded = []
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        dependant = getattr(route, "dependant", None)
        if path is None or dependant is None:
            continue  # static file mounts, websocket routes, etc.
        for method in methods:
            if method == "HEAD":
                continue
            if (method, path) in PUBLIC_PATHS:
                continue
            calls = _dependency_tree_calls(dependant)
            if _verify_api_key not in calls:
                unguarded.append(f"{method} {path}")

    assert not unguarded, (
        "These routes have no _verify_api_key (directly or via _require_role) "
        f"anywhere in their dependency tree: {sorted(set(unguarded))}. "
        "If a route is genuinely meant to be public, add it to PUBLIC_PATHS "
        "in this test deliberately, not by accident."
    )
