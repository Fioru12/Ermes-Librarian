"""Regression guard: a secret-gated verification must fail closed.

Prompted by a real bug found while debugging this project: api/chat_webhooks.py
wrote `if cfg.SLACK_SIGNING_SECRET: ...verify signature...` with no `else`.
When the secret was left at its factory-default empty value, the whole
verification step was silently skipped and the endpoint processed the
request unauthenticated -- reachable by anyone who knew or guessed a bound
channel id, no session, no API key, no signature. Same "fails open instead
of closed" shape as bugs found elsewhere in this project's history (the
folder-import isolation bypass, the evidence_only bypass) and in a sibling
repo (Astralis-Bot's is_authorized).

This walks the AST of every product source file (core/, api/, excluding
legacy_winsarp/, which is frozen and out of scope) looking for that exact
shape: an `if cfg.<SOMETHING_SECRET_OR_TOKEN_OR_KEY>:` with no `else`, whose
body calls something that looks like a verification routine. Such a
condition can only ever run the check when the secret happens to be
configured -- when it is not, the code proceeds as if verification
succeeded. The fix is always the same: invert the condition to
`if not cfg.X: raise/return` (fail closed) and run the verification
unconditionally afterward, exactly what api/chat_webhooks.py does today.

A hit here does not always mean a live vulnerability -- it means a human
should look at the specific code and confirm the missing branch is safe
(e.g. genuinely optional behaviour, not a security check). It should not
be silenced by loosening the pattern, only by fixing or explicitly
allowlisting the specific line with a comment explaining why it is safe.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["api", "core"]
EXCLUDE_PARTS = {"legacy_winsarp", "__pycache__"}

# cfg attribute name fragments that denote something meant to gate a
# verification step. Kept narrow and uppercase-only (matches config.py's own
# naming convention) so this does not flag unrelated boolean flags.
SECRET_LIKE_SUFFIXES = ("SECRET", "TOKEN", "API_KEY", "SIGNING_KEY")

# Call names that look like a verification/authentication routine. Matched
# as a substring of the called function's name, case-insensitive.
VERIFY_NAME_HINTS = ("verify", "authenticate", "check_signature")


def _cfg_secret_attr(node: ast.expr) -> str | None:
    """If `node` is (a boolean-and chain rooted at) `cfg.<NAME>` where NAME
    looks secret-like, return NAME. Handles bare `cfg.X` and `cfg.X and ...`."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) and node.values:
        node = node.values[0]
    if (
        isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "cfg"
        and node.attr.isupper() and any(node.attr.endswith(suffix) for suffix in SECRET_LIKE_SUFFIXES)
    ):
        return node.attr
    return None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def _body_calls_something_verify_like(body: list[ast.stmt]) -> bool:
    for stmt in ast.walk(ast.Module(body=body, type_ignores=[])):
        name = _call_name(stmt)
        if name and any(hint in name.lower() for hint in VERIFY_NAME_HINTS):
            return True
    return False


def _find_violations(tree: ast.AST, path: Path) -> list[str]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or node.orelse:
            continue  # has an else/elif: not the "silently skip" shape
        secret_name = _cfg_secret_attr(node.test)
        if secret_name is None:
            continue
        if _body_calls_something_verify_like(node.body):
            violations.append(f"{path}:{node.lineno}: `if cfg.{secret_name}:` guards a verification call with no else — fails open when {secret_name} is unset")
    return violations


def test_no_secret_gated_verification_fails_open():
    all_violations: list[str] = []
    for scan_dir in SCAN_DIRS:
        for py_file in (ROOT / scan_dir).rglob("*.py"):
            if EXCLUDE_PARTS & set(py_file.parts):
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            all_violations.extend(_find_violations(tree, py_file.relative_to(ROOT)))

    assert not all_violations, (
        "Found verification steps that silently no-op when their secret is unconfigured "
        "instead of refusing the request (fail-open, not fail-closed):\n"
        + "\n".join(all_violations)
        + "\n\nFix: invert to `if not cfg.X: raise/return` before the verification, "
        "then verify unconditionally — see api/chat_webhooks.py for the corrected shape."
    )
