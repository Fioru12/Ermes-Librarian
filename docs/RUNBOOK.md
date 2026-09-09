# Runbook

For whoever has to install Ermes Knowledge, keep it running, and fix it at
08:30 on a Monday. It assumes no familiarity with the codebase.

Everything here has been executed against this version, except where a step is
explicitly marked as unverified.

---

## 1. What you are deploying

A document library that answers questions with citations, and abstains when it
finds no evidence. One instance serves one organisation: there is no
multi-tenancy, and none is planned — separate customers get separate instances.

In the default configuration no document text leaves the machine. Sending text
to a model requires two independent decisions (a global consent flag and a
per-library setting), so a configured API key alone changes nothing.

**Components.** A FastAPI backend, a React frontend, a SQLite or PostgreSQL
database, and optionally a local Ollama server for embeddings and generation.
Ollama is not required: without it the system runs keyword retrieval and says so.

---

## 2. Before you install: check the configuration

```powershell
python -m config.validation
```

Prints every problem with the variable to set and what to do about it, and exits
non-zero if any of them would make the application unusable. Run it after
editing `.env` and before restarting. The same check runs at startup — a
configuration that cannot serve requests stops the application instead of
turning into scattered runtime errors.

Minimum to get a working instance:

| Variable | Why |
|---|---|
| `ERMES_ADMIN_PASSWORD` | Without it (and without `ERMES_API_KEY` or SSO) every request answers 503 |
| `ERMES_HOST` | Leave `127.0.0.1` unless a TLS reverse proxy sits in front |

Leave `ERMES_AUDIT_SECRET` unset. The instance generates its own signing key on
first run and keeps it in `security/.audit_secret`. Set it explicitly only when
several instances must verify the same audit entries, or when a secrets manager
owns the key.

---

## 3. Install

### Docker (recommended for a server)

```bash
cp .env.example .env      # then edit it: set ERMES_ADMIN_PASSWORD
docker compose up -d
```

Optional profiles: `--profile postgres` for PostgreSQL instead of SQLite,
`--profile public` for a Caddy reverse proxy that terminates TLS.

> **Unverified.** The image builds in CI and the Compose file validates, but the
> full stack has never been started end to end on a clean machine. Budget time
> for the first run and read the logs.

### Windows, without Docker

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv-ermes
.\.venv-ermes\Scripts\Activate.ps1
pip install -r requirements.txt
npm.cmd --prefix frontend install
.\scripts\avvia_ermes.ps1
```

The interface is on <http://127.0.0.1:3000>, the API on
<http://127.0.0.1:8502>.

---

## 4. Daily operation

### Is it healthy?

```bash
curl http://127.0.0.1:8502/health
```

`/health` answers 200 when the process is serving. It does **not** prove that
retrieval works or that Ollama is reachable — check the logs for that.

`/metrics` exposes Prometheus metrics. Set `ERMES_METRICS_TOKEN` when Prometheus
scrapes from another host; without a token the endpoint only answers on loopback.

### Reading the logs

Set `ERMES_LOG_FORMAT=json` (already the default inside Docker) and every event
becomes one line with separate fields:

```json
{"ts":"2026-09-09T17:37:15+00:00","level":"INFO","logger":"api",
 "message":"GET /health -> 200","event":"http_request","method":"GET",
 "path":"/health","status":200,"duration_ms":12.4,"request_id":"proxy-7f3a"}
```

Every line produced while handling a request carries the same `request_id`, and
that id is returned to the caller in the `X-Request-ID` header. **When a user
reports a problem, ask for that header value** — it takes you straight to their
request. If a reverse proxy already sets `X-Request-ID`, Ermes keeps it, so the
same id spans both.

`ERMES_LOG_LEVEL` accepts the usual names; `INFO` is the default.

---

## 5. Backup

Back up these, from the application directory:

| Path | Contains | Losing it means |
|---|---|---|
| `data/ermes_knowledge.sqlite3` | Libraries, documents, chunks, sessions | Everything |
| `documenti/` and `storage/` | The uploaded files | The originals |
| `security/` | Accounts, API key hashes, group mappings, **`.audit_secret`** | Nobody can log in; the audit log stops verifying |
| `logs/audit_admin.jsonl` | The audit trail | The record of who did what |
| `.env` | Configuration and secrets | The instance's identity |

**`security/.audit_secret` is the one people forget.** It is generated per
installation, and every audit entry is signed with it. Restore the audit log
without it and every entry reports as tampered — indistinguishable, to whoever
reads it, from actual tampering.

With PostgreSQL, replace the first row with your usual `pg_dump`.

Stop the application before copying the SQLite file, or use `sqlite3 .backup`.

### Restore

Stop the application, put the files back in the same relative positions, start
it. Then open the administrative audit view and confirm the signatures verify:
that is the check that tells you the restore was complete.

---

## 6. Upgrade

1. Back up as above.
2. Pull the new version.
3. `python -m config.validation` — new versions may require new settings.
4. Restart.

Database schema changes are applied automatically at startup (`CREATE TABLE IF
NOT EXISTS`). There is no down-migration: to roll back, restore the backup.

Sessions survive a restart — they live in the shared database, not in process
memory — so an upgrade does not log everyone out.

---

## 7. When something is wrong

**The application refuses to start.** Read the first line of output: it names
the variable and the fix. This is deliberate; a configuration that cannot serve
requests stops the instance rather than failing one request at a time.

**Nobody can log in via SSO.** Almost always the provider's keys cannot be
fetched. Check `ERMES_OIDC_ISSUER` (or `ERMES_OIDC_JWKS_URL`) and that the
instance can reach the discovery URL. Tokens are rejected with a logged reason —
search the logs for `OIDC:`.

**A user is locked out after failed passwords.** Expected: repeated failures
from one address are blocked for `ERMES_LOGIN_LOCKOUT_MINUTES` (default 15).
A correct password does not lift the block early; waiting does. The count is per
IP and per IP+username, never by username alone, so one person cannot lock out
another.

**Answers say there is no evidence.** That is the designed behaviour when
retrieval finds nothing, not a fault. Check that the documents are in the
library being queried, and remember that semantic search is off by default —
questions worded very differently from the source text are the known weak case
(see [RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md)).

**Everything is slow.** Generation with a local model on CPU takes tens of
seconds; that is the model, not the application. `duration_ms` in the logs
separates the two.

**One particular search is slow, the rest are fast.** Expected, and measured:
a term that appears in most documents makes every matching passage load and
score in memory. At 50,000 passages that is about three seconds, against three
milliseconds for a normal search. Indexing runs at roughly 1.5 s per thousand
passages, so a fifty-thousand-passage archive takes about a minute to load,
once. Reproduce on your own hardware with
`python evaluation/archive_scale.py --sizes 1000,10000,50000`.

---

## 8. Known limits

State these to whoever is deciding on the deployment, before they find out:

- **One instance per organisation.** No multi-tenancy.
- **One instance, full stop, for rate limiting and caching.** Sessions and login
  attempts are shared across instances; the request rate limiter and the search
  cache are not, so running several instances multiplies rate thresholds.
- **Search scales to tens of thousands of passages, not to millions.** Measured
  up to 50,000: typical searches stay at milliseconds, but a query on a very
  common term takes seconds because scoring happens in memory over every
  candidate. Beyond roughly 200,000 passages that becomes the limiting factor.
- **Rate limiting covers only upload, search and ask**, counted per
  authenticated user, plus a separate block on repeated failed logins. Everything
  else is unlimited. See the threat model, T8.
- **Abstention degrades sharply once the library holds unrelated text.**
  Measured: with 100 extra passages of real prose the system stops abstaining in
  two cases out of three, because a single shared term is enough to be returned
  as evidence. Enabling `ERMES_EVIDENCE_VERIFIER=1` restores it to 1.000 and, at
  that corpus size, also improves overall recall. If you care about "it says
  I don't know instead of guessing" — and that is the reason to buy this — turn
  the verifier on and budget for the extra model calls.
- **Retrieval quality has been measured on a synthetic corpus**, with real prose
  used only as noise. The numbers in
  [RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md) are honest for that corpus
  and prove nothing about yours. Measure on your own documents before promising
  anything: `python evaluation/scale_check.py` is the starting point.
- **The Compose stack has never been run end to end.** See section 3.

The full analysis of what is defended and what is not is in
[THREAT_MODEL.md](THREAT_MODEL.md), including the gaps.
