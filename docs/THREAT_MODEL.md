# Threat model

Scope: Ermes Knowledge as it exists today — a single-tenant, local-first
document library. This describes what the current implementation actually
defends against and what it does not. Where a defence is claimed, the test that
proves it is named; where there is none, that is stated rather than omitted.

Out of scope: the frozen WinSarp engine under `legacy_winsarp/`, reachable only
with `ENABLE_LEGACY_WINSARP=1`. That path has no per-library ACL and is not
intended for shared or production deployments.

## Assets

| Asset | Why it matters |
|---|---|
| Uploaded documents and their extracted chunks | The confidential material the product exists to hold |
| Library membership and visibility | Determines who may read what |
| Local account passwords and API keys | Grant access to everything above |
| Audit log | The record of who did what; its value depends on being tamper-evident |
| `.env` (admin password, provider keys, audit secret) | Compromise grants full control |

## Trust boundaries

```text
Browser  ──①──▶  FastAPI  ──②──▶  SQLite + local file storage
                    │
                    └──③──▶  Ollama (local) or approved cloud provider
```

① Untrusted. Anything from the browser is attacker-controlled input.
② Trusted, but only because the API enforces access control *before* reading.
③ Egress boundary: the only point where document content can leave the machine.

**Uploaded documents are untrusted data on both sides of ②.** They are attacker
input at upload time and remain attacker input when their text is later shown to
a user or sent to a model.

## Threats and current posture

### T1 — Retrieval crosses a library boundary

The product's central claim. A user with access to library A obtains content
from library B, either directly or through an assistant answer.

*Posture:* the library is resolved and access-checked in `core/library_store.py`
before any chunk is read; retrieval is scoped by `library_id` in SQL rather than
filtered afterwards. Covered by `tests/test_library_store.py`, by
`scripts/run_demo_validation.py` against two live corpora, and end-to-end
through the browser in `frontend/e2e/evidence-and-isolation.spec.ts`.

### T2 — An endpoint ships without authorisation

A new route is added and nobody notices it is public.

*Posture:* `tests/test_api_auth_coverage.py` walks every route on the app and
fails the build unless the auth dependency is present, with an explicit
allowlist of public paths. Adding an unprotected endpoint requires deliberately
editing that allowlist.

### T3 — A malicious document attacks the parser

An uploaded file is crafted to exhaust memory, escape the storage directory, or
be something other than it claims.

*Posture:* size and magic-byte checks before parsing; filename sanitisation that
strips directory components and enforces an extension allowlist; Office archives
rejected on entry count, uncompressed size and compression ratio; XML parts
rejected if they carry a document type declaration. All covered by
`tests/test_upload_hardening.py` and `tests/test_document_parser.py`.

**A real instance of this threat was found and fixed on 21 August 2026**: the
`.xlsx` parser expanded XML entities, so 1.157 bytes of input produced 10.001
characters — a billion-laughs denial of service reachable by any user allowed to
upload. See `docs/CODE_REVIEW.md`.

### T4 — Prompt injection through document content

A document contains text instructing the assistant to ignore its constraints,
reveal other content, or take an action.

*Posture:* partial. In the default `evidence_only` mode no model is involved, so
the threat does not arise: retrieved passages are shown verbatim with citations.
Document text is rendered as escaped React nodes, never as HTML, so it cannot
inject markup into the page (`InlineMarkdown.test.tsx`). In `local_ollama` and
approved-provider modes, document text does reach a model prompt, and **there is
no injection-specific mitigation today**. The structural limits are that
retrieval is already scoped to one library, and that the assistant has no tools
and can take no action — an injected instruction can influence wording, not
cause access or side effects.

### T5 — Document content reaches a third party unintentionally

*Posture:* cloud processing requires two independent decisions: the global
`ERMES_LIBRARY_CLOUD_CONSENT` flag, and an administrator selecting the mode for
that specific library. A configured API key alone changes nothing. There is no
automatic fallback from local to cloud, nor between providers: a failure surfaces
as an error rather than silently rerouting data. Approved endpoints are checked
against an allowlist over safe transport (`tests/test_provider_endpoint_policy.py`,
which also rejects the cloud metadata address and `file://`).

### T6 — Audit log tampering

*Posture:* entries are append-only and individually HMAC-signed; the admin
interface verifies every signature and reports mismatches rather than assuming
integrity. **Operational caveat, and a real one:** if `ERMES_AUDIT_SECRET` is
unset, a fresh key is generated at each restart and all earlier entries stop
verifying — which is indistinguishable, to the reader, from tampering. Set it
persistently. This is documented in `README.md` beside the audit screenshot.

### T7 — Credential and secret exposure

*Posture:* passwords are hashed, API keys stored hashed and shown once at
creation. `.env`, `LOCAL_LOGIN.txt` and runtime data are excluded from Git; the
ignore rules were tightened on 20 August 2026 after `.env.test` was found to be
trackable. The full Git history has been scanned for secrets, and one
confidential third-party document was purged from it entirely.

Residual risk: the session cookie is not marked `Secure` when the host is
`0.0.0.0` or localhost, because local development is served over plain HTTP.
**A deployment reachable beyond localhost must terminate TLS in front of the
application**; the `public` Compose profile provides Caddy for this.

### T8 — Denial of service

*Posture:* per-identifier request and upload rate limiting
(`tests/test_rate_limiter.py`), an upload size ceiling, and the archive limits
under T3. No protection against a distributed attack, and none is intended at
this scale.

## Known gaps

Stated plainly, because a threat model that lists only solved problems is
marketing:

1. **No prompt-injection mitigation** in the modes that involve a model (T4).
2. **Single-tenant identity.** Local accounts only; no OIDC, no group mapping,
   no propagation of an external directory's permissions into retrieval.
3. **No deletion path for a library.** Removing one currently requires touching
   the database directly, which is both a usability and a governance gap.
4. **`mypy` and `bandit` are advisory in CI**, not blocking. Their findings are
   reviewed manually; the last review left zero high-severity issues.
5. **The full Compose stack has never been started end to end** on a clean
   machine. The image builds in CI and the Compose file validates, but
   `docker compose up` remains unverified.
