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

### T2b — An allowlisted route's own check was optional

*Found 10 September 2026.* The defence under T2 has a blind spot, and the
Telegram webhook fell straight into it. Three chat routes sit on the
allowlist in `tests/test_api_auth_coverage.py` because their authentication is
the platform's signature, not an Ermes session — that is correct, and the
allowlist is the right place for them. But the allowlist only records that
these routes authenticate *some other way*; nothing checked that the other way
actually runs.

Slack and Teams verify an HMAC and fail closed when the secret is unset. The
Telegram route, added later, read:

```python
secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
if secret_token and secret_token != cfg.TELEGRAM_BOT_TOKEN:
    raise HTTPException(403, ...)
```

With the header **absent**, the comparison never happens. Anyone who could
reach the port could ask questions of the bound library and read the answers
with their citations — no session, no API key, no signature. The single
existing test always sent the header, so the open branch was covered by
nothing. The exposure is the same one the comment on `slack_webhook` describes
having found and closed on that route; the third sibling reintroduced it.

Two further defects in the same three lines. The expected value was the **bot
token** — the credential that can post as the bot and read every update — so
enabling the integration as documented meant registering that token as the
webhook secret and having Telegram echo it in a header on every request, where
any proxy that logs headers would keep it. And the comparison used `!=`
instead of `hmac.compare_digest`, which both siblings use: a byte-by-byte
comparison leaks the secret through response timing, and it was the only thing
protecting the route.

*Posture:* the route now fails closed on a missing `ERMES_TELEGRAM_WEBHOOK_SECRET`,
requires the header, and compares in constant time against a secret dedicated
to the webhook. `tests/test_telegram_webhook_guards.py` covers the missing
header, the wrong secret, the unset secret, and the bot token being refused as
the secret; five of its twelve tests fail on the previous code. The Teams entry
in `.env.example` also described its secret as optional, which the code has not
allowed for some time; `tests/test_env_example_matches_config.py` now asserts
that each of the three secrets gating a public route is documented.

*Remaining gap:* the allowlist still says only "authenticated some other way".
A route can be added to it with a signature check that is wrong or absent, and
nothing in the build would object.

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

### T1c — A third ingestion path, and a read-only user could plant evidence

*Posture:* fixed on 10 September 2026, after being demonstrated.
`POST /api/integrations/automation/ingest` exists so n8n, Zapier and similar
tools can push documents in. It required only `_verify_api_key` — any
authenticated user — while the browser upload requires the `editor` role, and it
applied none of that path's four guards: filename sanitisation with an extension
allowlist, the upload size ceiling, and a magic-byte check against the declared
type.

Demonstrated: the same `viewer` account refused with 403 by the normal upload
ingested a document here and received 200. That is worse than ordinary
privilege escalation, because ingested documents become the evidence the
librarian cites to other users as authoritative — a read-only account could put
arbitrary content into the system's mouth. An unsupported extension also
produced a 500 rather than a refusal, because the parser's exception escaped.

All four guards now apply, reused from `upload_document` rather than rewritten.
`tests/test_webhook_ingest_guards.py` fails five ways on the previous code and
confirms that an editor pushing a document through the gateway — the reason the
route exists — still works.

### T1b — A second ingestion path bypasses the guards of the first

*Posture:* fixed on 10 September 2026, after being demonstrated.
`POST /api/connectors/sync` pulls documents into a library by reading the
server's filesystem — exactly what a registered folder source does. That twin
path in `api/libraries.py` carries two deliberate guards with explanatory
comments: owner-or-admin (because filesystem read access is a larger blast
radius than a browser upload) and a refusal of paths inside the application's
own tree (because pointing a source at `storage/libraries/<other-id>` imports
another library's documents verbatim — a complete bypass of T1, reached without
touching the read path the isolation tests cover).

The connector route honoured **neither**. Demonstrated: a user holding the
global `editor` role and *not* owning the target library pointed it at an
arbitrary server folder, imported a payslip file, and read salary, tax code and
IBAN back through search. Both guards now apply, and
`tests/test_connector_sync_authorization.py` fails on the previous code while
confirming the legitimate case — an owner importing an external network folder —
still works.

Residual risk, stated rather than fixed: an owner or admin can still point a
source at any external folder the server process can read. There is no allowlist
of permitted roots. That is the feature working as designed, but a deployment
handling sensitive filesystems should consider constraining it.

### T5b — Sensitive data reaches a model despite the PII filter

The product claims that personal data is masked before any text reaches a
language model. That claim held for the main answer path and not for the others.

*Posture:* `core/pii_filter.py` is genuinely wired into `evidence_assistant.py`
at three points — the question, every excerpt entering the prompt, and the
answer coming back. But three other modules also send text to a model and none
applied the filter: `document_summary.py` (the passages of a document being
summarised), `hyde.py` (the user's question, which a person types and may
contain a tax code or an IBAN), and `evidence_verifier.py` (the retrieved
excerpts). The last of those was written on 9 September 2026 during this work
and shipped without the filter — a new path around an existing control.

All three now apply it. Covered by
`tests/test_evidence_verifier.py::test_the_text_sent_to_the_model_is_pii_filtered`,
which fails on the previous code. The general lesson is the one this project
keeps repeating: a control is only as wide as the paths that call it, and adding
a path is how you get around it without noticing.

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
integrity.

**This section previously described a caveat that did not exist, and omitted the
one that did.** It said that with `ERMES_AUDIT_SECRET` unset a fresh key would be
generated at each restart, so older entries would stop verifying. Neither half was
true: the setting was never unset, because `AUDIT_SECRET` carried a non-empty
default, and the unreachable fallback behind it persisted its key to
`security/.audit_secret` rather than regenerating one. What actually happened is
worse than the documented caveat: every installation signed its audit log with
`ermes-audit-secret-change-in-production` — a string committed to this repository
— or, for anyone who copied `.env.example`, with `CHANGE_ME_TO_AUDIT_SECRET`.
Both are public, so anyone holding the repository could forge an entry that
verified as authentic. Demonstrated before the fix by signing a fabricated
`library_deleted` entry with the repository key alone; it verified.

The default is now empty, which makes the existing per-installation key
generation reachable, and known placeholder values are refused rather than used.
Set `ERMES_AUDIT_SECRET` explicitly only when several instances must verify the
same entries, or when a secrets manager owns the key. Covered by
`tests/test_audit_secret.py`.

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

### T7b — The restore path wrote wherever the archive said

*Found 10 September 2026, in the automatic-backup subsystem.*
`core/backup_manager.py` restored each member with
`target = os.path.join(cfg.BASE_DIR, member.name)`. An absolute member name
makes `os.path.join` discard the base entirely, and `../..` walks out of it —
the classic tar-slip. The usual mitigation does not apply here: the code does
not call `extractall`, so tarfile's own extraction filter never runs.

It did not need a hostile archive to be reached. Member names come from
`os.path.relpath(path, cfg.BASE_DIR)`, so a legitimate configuration — the
document storage on a network share, the database on another disk — produces
names beginning `../`, and restoring wrote outside the application directory.
The archive name was also unvalidated, arriving straight from the route path
`POST /api/backup/restore/{backup_name}`; on Windows a backslash is a
separator, so `..\..\elsewhere\archive` selected an arbitrary `.tar.gz` from
anywhere on disk. Restore is admin-only, so this is privilege *escalation*
from admin to arbitrary file write as the server account, not a hole open to
any user.

*Posture:* every member's resolved target must now sit inside `BASE_DIR`
(checked before the dry-run branch too, so a dry run does not list what the
real restore refuses), and the archive name must match
`ermes_backup_<...>` with no separators. Items genuinely outside `BASE_DIR` are
archived under `external/` and the metadata says so, rather than entering the
archive with a name the restore would reject. Covered by
`tests/test_backup_guards.py`.

*Unchanged and worth stating plainly:* the archive is a plain `.tar.gz` that
contains `.env` and the whole `security/` directory — that is, the audit
signing key and the user file. It is not encrypted. Anyone who can read the
backup directory holds those secrets, so the backup directory needs the same
protection as `security/` itself, and a backup copied to a network share or a
USB disk carries them along.

### T8 — Denial of service

*Posture:* this section once described per-identifier rate limiting as an
active defence, citing `tests/test_rate_limiter.py`. The limiter was real and
those tests passed, but it was applied to no route at all: the tests exercise the
class, not the server, so nothing went red while the server was unprotected.

It is now wired to the three routes where abuse costs real resources — document
upload, search and ask — and `tests/test_rate_limiting_applied.py` exercises the
endpoints rather than the class, so removing the wiring turns it red. Cheap routes
are deliberately excluded: rate limiting `/health` would let a readiness probe
declare a healthy instance dead.

Requests are counted **per authenticated user**, with the client address only as a
fallback. Counting by address alone — as the unused version did — is wrong for
this product's deployment model: behind a company NAT the whole office shares one
address, so the first person to upload something would block their colleagues.

*Correction, 10 September 2026.* "The three routes where abuse costs real
resources" was wrong when written: the same two expensive operations are also
exposed by the MCP server (`api/mcp_server.py`), on `POST /api/mcp/call` and
`POST /api/mcp/rpc`, and neither was limited. That is the worst place to miss
it — the intended caller of those routes is not a person clicking but an agent
in a loop, which is precisely the traffic the limiter exists for. Both are now
limited; `/info` and `/tools` deliberately are not, because a client queries
discovery on every connection and throttling it would break the handshake
while protecting nothing. On the JSON-RPC route the limiter is applied to
`tools/call` only, for the same reason: `initialize` and `tools/list` are the
handshake.

The same two omissions held for the three chat webhooks (Slack, Teams,
Telegram), which call the same expensive operation with no Ermes session at
all — so the per-user limiter cannot cover them. They now count per bound
channel, which is the unit of traffic that exists there, and the question is
capped at the same 2000 characters. A Telegram reply is also truncated to 4096
characters: beyond that Telegram refuses the message outright, so a long
answer was not delivered at all and the failure was visible only in the
channel.

The MCP path also skipped the argument limits that the HTTP routes get from
their Pydantic models. A question is capped at 2000 characters on
`/ask`; through MCP a question of any length went whole into the model prompt,
and a non-numeric `top_k` raised `ValueError`, so a malformed agent argument
became a server error. Covered by `tests/test_mcp_server_guards.py`, which
fails on the previous code.

Also holding: an upload size ceiling, the archive limits under T3, and a per-IP
block on repeated failed logins (`core/login_guard.py`). No protection against a
distributed attack, and none is intended at this scale. The counters are still per
process, so several instances multiply every threshold.

### T9 — The system answers when it should abstain

The product's promise is that it says "I don't know" rather than citing
something irrelevant. That promise is weaker than the headline number suggests.

*Posture:* measured, and the measurement is unflattering. On the 16-passage demo
corpus abstention is perfect (1.000). Add 100 passages of ordinary prose and it
falls to 0.333 — two abstention questions out of three get a confident citation
to unrelated text. The cause is in `core/library_store.py`: a chunk is admitted
as evidence if it shares **any single term** with the question, and every term
weighs the same — and the shared terms are often function words. One abstention
question matched an unrelated technical paragraph on *sempre*, *senza* and *mai*
alone.

Enabling `ERMES_EVIDENCE_VERIFIER=1` restores abstention to 1.000 at every
corpus size measured, and at 388 added passages also improves overall recall.
It is off by default because it needs a reachable model, so **a deployment that
relies on abstention must turn it on**. Covered by
`evaluation/scale_check.py --verify`; the analysis, including a threshold-based
fix that was measured and rejected, is in `RETRIEVAL_EVALUATION.md`.

## Known gaps

Stated plainly, because a threat model that lists only solved problems is
marketing:

1. **No prompt-injection mitigation** in the modes that involve a model (T4).
2. **OIDC identity is verified but minimal.** ID tokens are checked against the
   provider's published JWKS (`core/oidc_keys.py`): asymmetric algorithms only,
   `exp` required, `iss`/`aud` enforced, and no code path that falls back to an
   unverified decode. This replaced an earlier implementation that decoded the
   payload without checking the signature at all — a hand-written token was
   enough to obtain an administrator, demonstrated before the fix and now held
   shut by `tests/test_oidc_signature.py`. What is still missing: no token
   revocation or introspection (a stolen token stays usable until `exp`), no
   refresh flow, and a single configured audience per instance.
3. **Rate limiting is per process, and covers only the expensive routes.**
   Upload, search and ask are limited per authenticated user (T8); repeated failed
   logins are blocked separately (`core/login_guard.py`) — before that change 50
   wrong passwords in a row all returned 401, never 429. Everything else is
   unlimited, and the counters live in process memory, so N instances allow N
   times each threshold.
4. **Horizontal scaling is only partly real.** Sessions and login attempts now
   live on the shared store, so a second instance recognises them
   (`core/session_store.py`, `core/login_guard.py`). The request rate limiter and
   the search cache remain per process: N instances multiply every rate
   threshold by N, and each instance keeps its own cache. Until 10 September 2026
   the shared *database* was also an illusion: `psycopg` was absent from
   `requirements.txt` and `create_backend` answered a missing driver by falling
   back to SQLite with a log line, so an operator who configured PostgreSQL for a
   multi-instance deployment got one local database per instance. It now refuses
   to start instead, and the parity tests run against a real PostgreSQL in CI.
5. **Deleting a library removes its rows, not its history.** `DELETE
   /api/libraries/{id}` exists and cascades to documents, chunks, ACLs, import
   sources and chat integrations (`tests/test_library_deletion.py`). What is
   still missing is a retention story: the audit entries naming the deleted
   library stay, by design, and there is no "export everything about this
   library then erase it" operation of the kind a GDPR request would need.
   (This entry previously claimed no deletion path existed at all; that stopped
   being true and nobody updated it.)
6. **Logs carry no tamper protection.** Application logs are now structured and
   correlated by request id (`core/logging_setup.py`), which makes them usable in
   an aggregator, but they are ordinary output: unlike the audit log they are not
   signed, and an operator with host access can edit them.
7. **Type debt is fenced, not paid off.** `mypy` and `bandit` now block the
   build instead of reporting advisories nobody could triage — 92 findings with
   no way to tell new from old were, in practice, ignored. `legacy_winsarp` is
   excluded (it is out of scope, and produced 40 of them by itself), and the 18
   product modules that still carry findings are listed by name in
   `pyproject.toml`. Everything else must stay clean, so new code starts clean;
   that list can only shrink. `pip-audit` stays advisory on purpose: it depends
   on an external vulnerability feed that can go red overnight without anything
   changing here.
8. **The full Compose stack has never been started end to end** on a clean
   machine, and [RUNBOOK.md](RUNBOOK.md) marks that step unverified rather than
   implying otherwise. The image builds in CI and the Compose file validates, but
   `docker compose up` remains unverified.
