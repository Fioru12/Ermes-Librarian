# Ermes Knowledge

Ermes Knowledge is a local-first document library for small and medium businesses. It turns company files into a governed, searchable knowledge base: users upload documents, ask questions in natural language, and receive answers that point back to the supporting source.

The product is designed to be useful before any cloud AI is enabled. Its default mode is evidence-only: documents remain local and the application returns the most relevant passages with traceable citations. An administrator may explicitly enable a local Ollama model or an approved OpenRouter provider for a single library.

> Status: active MVP / portfolio project. The current implementation is single-tenant and local-first; it is not yet a complete enterprise SaaS platform.

## Measured, not claimed

Every number below was produced by a command in this repository, and every
command can be re-run by anyone who clones it. The unflattering results are
here too — they are the reason several features are switched off.

**Retrieval quality** — 27 questions over a demo corpus, three categories
(`python evaluation/run_library_eval.py`):

| | Shipped default | With semantic search | With evidence verification |
|---|---|---|---|
| Direct questions | **1.000** | 1.000 | 1.000 |
| Paraphrased questions | 0.500 | **0.875** | 0.625 |
| Correctly refusing to answer | **1.000** | 0.000 | **1.000** |

**Speed on an office-sized archive** (`python evaluation/archive_scale.py`):

| Passages | Indexing | Typical search | Worst-case search |
|---|---|---|---|
| 10.000 | 11,5 s | 1,4 ms | 281 ms |
| 50.000 | 68,8 s | **3,2 ms** | 3,3 s |

### What does not work, stated here rather than discovered later

- **Abstention degrades as the library grows.** Perfect on the demo corpus,
  0.333 once 100 passages of unrelated prose are added: any single shared term
  is enough to be cited as evidence. Evidence verification restores it to
  1.000, and at that size also improves overall recall — but it needs a model
  running, so it is off by default. Reproduce with
  `python evaluation/scale_check.py --sizes 0,25,97`.
- **The neural reranker is disabled**, because measuring it showed it makes
  every configuration worse — the previously shipped default was the worst of
  the five.
- **Semantic search is disabled**, because it doubles paraphrase recall and
  destroys abstention. Four score-based signals were measured looking for a
  cutoff that keeps both; none separates the two populations, and the analysis
  is written up rather than glossed over.
- **The corpus is synthetic.** These numbers are honest for it and prove
  nothing about yours. `evaluation/scale_check.py` is the starting point for
  measuring on real documents.

The full analysis, including three attempted fixes that were measured and
rejected, is in [docs/RETRIEVAL_EVALUATION.md](docs/RETRIEVAL_EVALUATION.md).
What the system defends against, and what it does not, is in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). How to install, back up and
operate it is in [docs/RUNBOOK.md](docs/RUNBOOK.md).

![Walkthrough: login, browsing a library's documents, asking a question that gets cited, and honest abstention on two different out-of-scope questions — including one that only a different library could answer](docs/assets/demo.gif)

*The full sequence from [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md), recorded end-to-end against a running instance: two answered questions with real citations, then two correct abstentions — the second one proving retrieval never crosses a library boundary, not just asserting it.*

![The assistant answering from a document library, with every passage tied to a file, version and section](docs/screenshots/assistant-with-citations.png)

*Every substantive answer names its sources: file, version, section and the exact excerpt it relied on — and the original document is one click away. When the library cannot support an answer, the assistant says so instead of inventing one.*

## Why it exists

Teams often have procedures, policies, manuals, contracts and internal know-how spread across folders. Finding the right version is slow and unreliable. Ermes Knowledge provides one controlled entry point where the answer is tied to the source document instead of presented as unexplained AI output.

## Current capabilities

- Separate libraries with private or shared visibility.
- Upload, parse and index PDF, DOCX, TXT, Markdown, XLSX, PPTX, CSV and RTF documents — with per-cell and per-slide locators for precise citations.
- Version history, restore and protected download of original files.
- Chunk-level retrieval scoped to the selected library, hybrid (full-text + embeddings). A neural cross-encoder reranker is implemented and available, but **off by default**: measured on the project's own gold set it makes every configuration worse (recall@3 0.815 vs 0.852, paraphrases 0.375 vs 0.500). The comparison that decided it is reproducible with `python evaluation/run_library_eval.py --compare` — see [docs/RETRIEVAL_EVALUATION.md](docs/RETRIEVAL_EVALUATION.md).
- Per-user semantic search cache (TTL + LRU) with automatic invalidation on writes — scoped per user so ACL boundaries are never cached across.
- Evidence-first answers with citations, document version, locator and excerpt.
- Clear abstention when the selected library does not contain enough evidence.
- Optional evidence verification: a model is asked whether each retrieved passage actually answers the question, and passages that do not are dropped before the answer is composed. It is the only mechanism measured that improves paraphrased questions **without** destroying abstention — recall@3 0.889 with abstention still at 1.000, against 0.852 for the shipped default. Off by default because it costs a model call per candidate passage; see [docs/RETRIEVAL_EVALUATION.md](docs/RETRIEVAL_EVALUATION.md) for the four score-based signals that were measured first and did not work.
- Conversation memory for follow-up questions: "and for managers?" is rewritten into a standalone question using the last few questions **before** retrieval, so the evidence pipeline — retrieval, verification, abstention — runs on the rewritten question exactly as on a new one. The conversation never enters the answer prompt, and the rewritten question is shown to the user and recorded in the audit entry. Off by default (needs a model); see [docs/THREAT_MODEL.md, T5c](docs/THREAT_MODEL.md).
- Prompt-injection quarantine: before any passage reaches a model, a deterministic check flags instructions aimed at the assistant ("ignore previous instructions", "reveal the system prompt", role markers, in English and Italian). A flagged passage is replaced by a quarantine note in the prompt, dropped as evidence by the verifier, and returned to the user as a citation marked *not used* — the source stays visible, its text does not reach the model. It is pattern-based and says so: a novel paraphrase gets through to the structural limits (retrieval scoped to one library, an assistant with no tools). See [docs/THREAT_MODEL.md, T4](docs/THREAT_MODEL.md).
- Data-subject export and erasure (GDPR art. 15 and 17): `GET /api/privacy/users/{u}/export` returns everything referable to an account; `DELETE /api/privacy/users/{u}` removes the person's data, reassigns the organisation's libraries to the administrator, and retains the signed audit entries — stating so, because rewriting a signed record would make it indistinguishable from a tampered one.
- OIDC/SSO group-to-library ACL propagation: mapped groups grant viewer/editor roles (never admin), direct memberships always win, and SSO-only reachable libraries appear in the user's list.
- Dual database backend: SQLite by default, PostgreSQL via `ERMES_DATABASE_URL` (psycopg 3, jsonb embeddings, tsvector full-text, `SKIP LOCKED` job claims) — see [docs/POSTGRES_MIGRATION_PLAN.md](docs/POSTGRES_MIGRATION_PLAN.md). Eight parity tests compare the two backends and now run against a real PostgreSQL in CI; until 10 September 2026 they skipped themselves everywhere, the driver was missing from `requirements.txt`, and setting `ERMES_DATABASE_URL` silently fell back to SQLite — so every instance kept its own local database while the configuration said otherwise.
- Prometheus metrics at `/metrics` (auth required): request latency, RAG questions, rerank mode, ingestion outcomes, and counters for the features that fail silently — evidence verification that could not run, question rewrites that fell back, passages quarantined for injection. `/health` reports `degraded` (not just `healthy`/down) with a reason when an enabled feature cannot work because its model is unreachable.
- Rate-limit counters on the shared store by default (`ERMES_RATE_LIMIT_BACKEND`), so instances behind a load balancer share one threshold instead of multiplying it — like sessions and login attempts, without a separate component.
- Enterprise Connectors: Local NAS / Network Shared Folders (`local_folder`), Web Scraper, and Microsoft Graph (SharePoint / OneDrive) — all configurable from the React UI, with a folder-watcher status bar and one-click sync.
- Model Context Protocol (MCP) Server: native JSON-RPC 2.0 (`/api/mcp/rpc`) and REST (`/api/mcp/tools`) for AI agents (Claude Desktop, Cursor, Antigravity, LangChain).
- Automation Webhook Gateway: API Key-authenticated REST endpoints (`/api/integrations/automation/ask` and `/ingest`) tailored for n8n, Zapier, Make, and microservices.
- Multi-channel Chat Integrations: Slack Slash Commands / Events, Microsoft Teams Outgoing Webhooks, and Telegram Bot API.
- Real-time Server-Sent Events (SSE) Streaming: `/api/libraries/{library_id}/ask/stream` streams live status steps (`retrieving`, `verifying`, `composing`), verified citations, and generated answers directly to the React UI with zero polling.
- Dynamic Enterprise Glossary & Synonym Disambiguation: configurable corporate acronyms, abbreviations and domain glossaries (`/api/synonyms`, `config/synonyms.json`), with multi-word phrase prioritization and interactive management in the Settings tab.
- Advanced Chat & Document Actions: export full conversations with citations to Markdown (`.md`), reset active chat session without page reload, copy answers and citations with visual feedback, and real-time document filtering by extension (`PDF`, `DOCX`, `PPTX`, `XLSX`, `TXT`, `MD`) and filename.
- Enterprise Documentation: Italian operational and deployment manual in [docs/GUIDA_OPERATIVA_AZIENDA.md](docs/GUIDA_OPERATIVA_AZIENDA.md) and English administrator guide in [docs/RUNBOOK.md](docs/RUNBOOK.md).
- Dedicated React Interface with real-time streaming feedback, first-access onboarding wizard, Connectors & Automations tab, FastAPI backend, automated test suite (backend `pytest`, frontend `vitest`, Locust load scenarios, pytest performance benchmarks).

![Libraries and documents, each with version, indexing state and a per-library assistant policy](docs/screenshots/libraries-and-documents.png)

*Each library is a separate boundary: its own documents, its own collaborators, and its own assistant policy. Retrieval is constrained to the selected library before any context reaches the assistant — the demo corpus ships with a check that proves it, rather than asserting it.*

## Product principles

1. **Local first.** A cloud API key alone never enables cloud processing.
2. **Evidence before generation.** Every substantive answer must cite an accessible document or abstain.
3. **Library isolation.** Retrieval is constrained to the chosen library before context reaches the assistant.
4. **Documents are untrusted data.** Retrieved text cannot authorize tools or actions.
5. **Originals and versions matter.** Citations remain linked to the document version that supported the answer.

![Administrative audit log reporting that the HMAC signature on every entry verifies](docs/screenshots/audit-log-integrity.png)

*Library operations are recorded in an append-only audit log, each entry signed with HMAC. The interface verifies every signature and reports tampering rather than assuming the record is intact. Each installation generates and keeps its own signing key on first run — earlier versions shipped a default key that was committed to this repository, which made the signature forgeable by anyone holding a copy (see [threat model, T6](docs/THREAT_MODEL.md)). Set `ERMES_AUDIT_SECRET` yourself only when several instances must verify the same entries.*

## Quick start (Windows)

Prerequisites: Python 3.11+, Node.js 18+ and npm. Ollama is optional unless you select `local_ollama` or local semantic search.

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv-ermes
.\.venv-ermes\Scripts\Activate.ps1
pip install -r requirements.txt
npm.cmd --prefix frontend install
.\.venv-ermes\Scripts\python.exe scripts\provision_local_demo_auth.py --write
.\scripts\avvia_ermes.ps1
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The API health endpoint is [http://127.0.0.1:8502/health](http://127.0.0.1:8502/health).

To check a configuration before starting anything — useful when deploying
somewhere new, or in a CI gate:

```powershell
.\.venv-ermes\Scripts\python.exe -m config.validation
```

It prints each problem with the variable to set and what to do about it, and
exits non-zero if any of them would make the application unusable. The same
check runs at startup: a configuration that cannot serve requests stops the
application rather than turning into scattered runtime errors. That mattered in
practice — with SSO enabled but no issuer or JWKS the application used to start
happily and answer `200` on `/health` while every single login was already
guaranteed to fail.

The project desktop shortcut, if created with `scripts/CREA_COLLEGAMENTO_DESKTOP.ps1`, launches the same official script.
The provisioning command is opt-in and writes first-run credentials only to untracked `.env` and `LOCAL_LOGIN.txt` files.

### Run checks

```powershell
.\.venv-ermes\Scripts\python.exe -m pytest -q tests/
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
```

End-to-end tests run against a **running** instance and exercise the real API,
store and retrieval path — they are what caught unit tests that passed without
verifying anything (see [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md), finding 17).
Start the stack, load the demo corpora, then:

```powershell
.\.venv-ermes\Scripts\python.exe scripts\run_demo_validation.py
npm.cmd --prefix frontend run e2e
```

They read the administrator credentials from `ERMES_ADMIN_USERNAME` and
`ERMES_ADMIN_PASSWORD`, and skip themselves if no password is set.

## Docker

```powershell
docker compose up --build
```

Runtime documents and the SQLite library database are mounted in `storage/` and are intentionally ignored by Git. For a corporate TLS-inspection network, pass the internal root certificate as a Docker BuildKit secret rather than copying it into the image:

```powershell
docker build --secret id=corporate_ca,src=company-ca.crt -t ermes-knowledge .
```

## Cloud AI policy

Cloud AI is optional. Before enabling it, set `ERMES_LIBRARY_CLOUD_CONSENT=1` in the local environment and configure a provider through the admin interface using a secret manager or untracked `.env`. A library owner explicitly selects either the dedicated OpenRouter setup or one enabled approved provider; Ermes sends only the retrieved, authorized excerpts to that exact provider. There is no automatic local-to-cloud or provider-to-provider fallback.

Never commit `.env`, document uploads, storage data, API keys or customer content. Rotate any key that may have been exposed in terminal history or source control.

## Architecture

```text
Browser
  -> React UI
  -> FastAPI
       -> Library store (metadata, versions, jobs, audit)
       -> Local storage (original documents)
       -> Parser and chunker
       -> Retrieval limited to the selected library
       -> Evidence answer / explicit local or approved-cloud LLM
```

The target architecture, security principles and planned evolution are documented in [docs/ARCHITECTURE_TARGET.md](docs/ARCHITECTURE_TARGET.md) and [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

### Why abstention is the hard part

The number that degrades with corpus size is abstention, and it is the
product's central claim. `evaluation/scale_check.py` isolates that single
variable — same 27 questions, same expected answers, only the amount of
surrounding text changes, using real prose from this repository as noise.

Direct questions hold up as the archive grows; abstention falls to 0.333 as
soon as the library contains other text. The cause is not statistical: a
question about a colleague working *sempre da casa senza mai* venire in sede
matched an unrelated technical paragraph on *sempre*, *senza* and *mai* alone —
three words that carry no meaning — because any single shared term is enough to
be returned as evidence. A question about the *codice etico* matched a sentence
about source code, which is a genuine ambiguity rather than a bug.

Three fixes were tried and measured: a lexical-coverage floor, term-rarity
(IDF) weighting, and a wider stopword list. None restores abstention; the
weighting was kept anyway because it improves ranking at scale, the other two
were dropped. Evidence verification is the only mechanism that works, and its
advantage grows with the corpus. All of it, including the numbers for the
rejected attempts, is in
[docs/RETRIEVAL_EVALUATION.md](docs/RETRIEVAL_EVALUATION.md).

## Demo corpus

Two fictional demo libraries, safe to upload and screenshot: [Northstar Works](examples/demo-corpus/README.md) (HR/IT/expense policies) and [Meridian Precision Works](examples/demo-corpus-quality/README.md) (manufacturing quality procedures). Loading both and asking a question that only the *other* library can answer is the fastest way to show that retrieval never crosses a library boundary — it is not just a design principle, the demo validation script checks it.

For a short presentation sequence, use the [five-minute demo guide](docs/DEMO_GUIDE.md).

With the local application running and an administrator password or API key configured only in `.env`, validate the complete demo flow:

```powershell
.\.venv-ermes\Scripts\python.exe scripts\run_demo_validation.py
```

## Roadmap

Done: a safe two-library demo corpus with a live-verified isolation check; local hybrid keyword+embedding search with a measured, published retrieval quality number (see [docs/RETRIEVAL_EVALUATION.md](docs/RETRIEVAL_EVALUATION.md)). See [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md) for the full phase-by-phase log, including what was found and fixed along the way, not just what shipped.

Still ahead:

1. Replace local-only identity with OIDC and propagate ACLs to retrieval.
2. Add connectors for shared folders, Google Drive and SharePoint behind the same permission model.
3. Move production metadata/storage to PostgreSQL and object storage for multi-user deployments.

The legacy WinSarp formula work is personal historical material, physically isolated under `legacy_winsarp/` and gated behind a dev-only flag (`ERMES_ENABLE_LEGACY_WINSARP`). It is not part of the Ermes Knowledge product path and must not be used as a public demo corpus or as a claim about the current product.

The isolation used to stop at the source tree. Its dependencies — LlamaIndex, ChromaDB, the Ollama client — sat in `requirements.txt` until 11 September 2026, so every install of the product, the container included, pulled in 94 extra packages (kubernetes, onnxruntime, grpcio, pandas, nltk, tokenizers) for an engine that is off by default and that CI never runs: 150 packages instead of 56. They now live in `requirements-legacy.txt`, which includes the product file, and `tests/test_legacy_is_isolated.py` fails if they come back or if product code imports them at module level. The full suite — 564 tests — passes with all three packages blocked at import, which is the evidence that the product never needed them.

## License

MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Almost every dependency is
permissive (MIT, BSD, Apache-2.0, ISC). The exceptions are named rather than
averaged away: `psycopg` is LGPL-3.0, and it is the optional PostgreSQL driver —
the product runs on SQLite without it, so an organisation whose policy forbids
(L)GPL can drop that one line from `requirements.txt`. On the JavaScript side
MPL-2.0 (`lightningcss`) and CC-BY-4.0 (`caniuse-lite`) appear in build tooling
only and are not shipped in the bundle. The full inventory with versions is in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), generated by
`scripts/generate_third_party_notices.py` and guarded by
`tests/test_third_party_notices.py` — which is how four missing entries and that
false "every dependency is permissive" claim were found.

## Repository hygiene before publishing

This workspace intentionally contains development history and local artifacts. Before making a public repository, use the release checklist in [docs/GITHUB_RELEASE_PLAN.md](docs/GITHUB_RELEASE_PLAN.md). A full-history secret scan has been run and one sensitive non-public document was found and purged from Git history entirely (not just deleted); re-scan before publishing if the history changes further.

## Documentation

- [Runbook](docs/RUNBOOK.md) — install, back up, upgrade and diagnose, written for whoever operates it
- [Changelog](CHANGELOG.md) — a readable log of this work, not a raw commit list
- [One-pager](docs/ONE_PAGER.md) — the short version, written for someone evaluating this project in two minutes
- [Product strategy](docs/PRODUCT_STRATEGY.md)
- [Project plan](docs/PROJECT_PLAN.md) (historical) and [Roadmap v2](docs/ROADMAP_V2.md) (current, phase-by-phase log)
- [Target architecture](docs/ARCHITECTURE_TARGET.md)
- [Threat model](docs/THREAT_MODEL.md) — assets, trust boundaries, what is defended and what is not, with the test proving each claim
- [Team audit](docs/AUDIT_2026-08-19.md) — architecture, security and design findings with file:line references
- [Code review](docs/CODE_REVIEW.md) — a verification-driven review: what was found, what was fixed, and what could not be verified
- [RAG retrieval evaluation](docs/RETRIEVAL_EVALUATION.md)
- [Demo guide](docs/DEMO_GUIDE.md)
- [GitHub release plan](docs/GITHUB_RELEASE_PLAN.md)
