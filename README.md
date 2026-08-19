# Ermes Knowledge

Ermes Knowledge is a local-first document library for small and medium businesses. It turns company files into a governed, searchable knowledge base: users upload documents, ask questions in natural language, and receive answers that point back to the supporting source.

The product is designed to be useful before any cloud AI is enabled. Its default mode is evidence-only: documents remain local and the application returns the most relevant passages with traceable citations. An administrator may explicitly enable a local Ollama model or an approved OpenRouter provider for a single library.

> Status: active MVP / portfolio project. The current implementation is single-tenant and local-first; it is not yet a complete enterprise SaaS platform.

## Why it exists

Teams often have procedures, policies, manuals, contracts and internal know-how spread across folders. Finding the right version is slow and unreliable. Ermes Knowledge provides one controlled entry point where the answer is tied to the source document instead of presented as unexplained AI output.

## Current capabilities

- Separate libraries with private or shared visibility.
- Upload, parse and index PDF, DOCX, TXT and Markdown documents.
- Version history, restore and protected download of original files.
- Chunk-level retrieval scoped to the selected library.
- Evidence-first answers with citations, document version, locator and excerpt.
- Clear abstention when the selected library does not contain enough evidence.
- Local web accounts (viewer, editor or administrator), API keys for integrations, and audit metadata for library operations.
- Per-library assistant policy:
  - `evidence_only` — default; no LLM receives document content.
  - `local_ollama` — sends selected passages only to an Ollama endpoint under your control.
  - `approved_openrouter` — requires an explicit global consent and an administrator's per-library choice.
- React interface, FastAPI API, automated backend and frontend tests.

## Product principles

1. **Local first.** A cloud API key alone never enables cloud processing.
2. **Evidence before generation.** Every substantive answer must cite an accessible document or abstain.
3. **Library isolation.** Retrieval is constrained to the chosen library before context reaches the assistant.
4. **Documents are untrusted data.** Retrieved text cannot authorize tools or actions.
5. **Originals and versions matter.** Citations remain linked to the document version that supported the answer.

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

The project desktop shortcut, if created with `scripts/CREA_COLLEGAMENTO_DESKTOP.ps1`, launches the same official script.
The provisioning command is opt-in and writes first-run credentials only to untracked `.env` and `LOCAL_LOGIN.txt` files.

### Run checks

```powershell
.\.venv-ermes\Scripts\python.exe -m pytest -q tests/
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
```

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

## License

MIT — see [LICENSE](LICENSE).

## Repository hygiene before publishing

This workspace intentionally contains development history and local artifacts. Before making a public repository, use the release checklist in [docs/GITHUB_RELEASE_PLAN.md](docs/GITHUB_RELEASE_PLAN.md). A full-history secret scan has been run and one sensitive non-public document was found and purged from Git history entirely (not just deleted); re-scan before publishing if the history changes further.

## Documentation

- [One-pager](docs/ONE_PAGER.md) — the short version, written for someone evaluating this project in two minutes
- [Product strategy](docs/PRODUCT_STRATEGY.md)
- [Project plan](docs/PROJECT_PLAN.md) (historical) and [Roadmap v2](docs/ROADMAP_V2.md) (current, phase-by-phase log)
- [Target architecture](docs/ARCHITECTURE_TARGET.md)
- [Team audit](docs/AUDIT_2026-08-19.md) — architecture, security and design findings with file:line references
- [RAG retrieval evaluation](docs/RETRIEVAL_EVALUATION.md)
- [Demo guide](docs/DEMO_GUIDE.md)
- [GitHub release plan](docs/GITHUB_RELEASE_PLAN.md)
