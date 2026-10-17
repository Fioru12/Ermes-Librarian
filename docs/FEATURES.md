# Features and product principles

> Moved here from the README. The front page keeps a one-screen summary; this is the complete list.

## Why it exists

Teams often have procedures, policies, manuals, contracts and internal know-how spread across folders. Finding the right version is slow and unreliable. Ermes Knowledge provides one controlled entry point where the answer is tied to the source document instead of presented as unexplained AI output.

## Current capabilities

- Separate libraries with private or shared visibility.
- Upload, parse and index PDF, DOCX, TXT, Markdown, XLSX, PPTX, CSV and RTF documents — with per-cell and per-slide locators for precise citations.
- Version history, restore and protected download of original files.
- Chunk-level retrieval scoped to the selected library, hybrid (full-text + embeddings). A neural cross-encoder reranker is implemented and available, but **off by default**: measured on the project's own gold set it makes every configuration worse (recall@3 0.815 vs 0.852, paraphrases 0.375 vs 0.500). The comparison that decided it is reproducible with `python evaluation/run_library_eval.py --compare` — see [docs/RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md).
- Per-user semantic search cache (TTL + LRU) with automatic invalidation on writes — scoped per user so ACL boundaries are never cached across.
- Evidence-first answers with citations, document version, locator and excerpt.
- Clear abstention when the selected library does not contain enough evidence.
- Optional evidence verification: a model is asked whether each retrieved passage actually answers the question, and passages that do not are dropped before the answer is composed. It is the only mechanism measured that improves paraphrased questions **without** destroying abstention — recall@3 0.889 with abstention still at 1.000, against 0.852 for the shipped default. Off by default because it costs a model call per candidate passage; see [docs/RETRIEVAL_EVALUATION.md](RETRIEVAL_EVALUATION.md) for the four score-based signals that were measured first and did not work.
- Conversation memory for follow-up questions: "and for managers?" is rewritten into a standalone question using the last few questions **before** retrieval, so the evidence pipeline — retrieval, verification, abstention — runs on the rewritten question exactly as on a new one. The conversation never enters the answer prompt, and the rewritten question is shown to the user and recorded in the audit entry. Off by default (needs a model); see [docs/THREAT_MODEL.md, T5c](THREAT_MODEL.md).
- Prompt-injection quarantine: before any passage reaches a model, a deterministic check flags instructions aimed at the assistant ("ignore previous instructions", "reveal the system prompt", role markers, in English and Italian). A flagged passage is replaced by a quarantine note in the prompt, dropped as evidence by the verifier, and returned to the user as a citation marked *not used* — the source stays visible, its text does not reach the model. It is pattern-based and says so: a novel paraphrase gets through to the structural limits (retrieval scoped to one library, an assistant with no tools). See [docs/THREAT_MODEL.md, T4](THREAT_MODEL.md).
- Data-subject export and erasure (GDPR art. 15 and 17): `GET /api/privacy/users/{u}/export` returns everything referable to an account; `DELETE /api/privacy/users/{u}` removes the person's data, reassigns the organisation's libraries to the administrator, and retains the signed audit entries — stating so, because rewriting a signed record would make it indistinguishable from a tampered one.
- OIDC/SSO group-to-library ACL propagation: mapped groups grant viewer/editor roles (never admin), direct memberships always win, and SSO-only reachable libraries appear in the user's list.
- Dual database backend: SQLite by default, PostgreSQL via `ERMES_DATABASE_URL` (psycopg 3, jsonb embeddings, tsvector full-text, `SKIP LOCKED` job claims) — see [docs/POSTGRES_MIGRATION_PLAN.md](POSTGRES_MIGRATION_PLAN.md). Eight parity tests compare the two backends and now run against a real PostgreSQL in CI; until 10 September 2026 they skipped themselves everywhere, the driver was missing from `requirements.txt`, and setting `ERMES_DATABASE_URL` silently fell back to SQLite — so every instance kept its own local database while the configuration said otherwise.
- Prometheus metrics at `/metrics` (auth required): request latency, RAG questions, rerank mode, ingestion outcomes, and counters for the features that fail silently — evidence verification that could not run, question rewrites that fell back, passages quarantined for injection. `/health` reports `degraded` (not just `healthy`/down) with a reason when an enabled feature cannot work because its model is unreachable.
- Rate-limit counters on the shared store by default (`ERMES_RATE_LIMIT_BACKEND`), so instances behind a load balancer share one threshold instead of multiplying it — like sessions and login attempts, without a separate component.
- Enterprise Connectors: Local NAS / Network Shared Folders (`local_folder`), Web Scraper, and Microsoft Graph (SharePoint / OneDrive) — all configurable from the React UI, with a folder-watcher status bar and one-click sync.
- Model Context Protocol (MCP) Server: native JSON-RPC 2.0 (`/api/mcp/rpc`) and REST (`/api/mcp/tools`) for AI agents (Claude Desktop, Cursor, Antigravity, LangChain).
- Automation Webhook Gateway: API Key-authenticated REST endpoints (`/api/integrations/automation/ask` and `/ingest`) tailored for n8n, Zapier, Make, and microservices.
- Multi-channel Chat Integrations: Slack Slash Commands / Events, Microsoft Teams Outgoing Webhooks, and Telegram Bot API.
- Real-time Server-Sent Events (SSE) Streaming: `/api/libraries/{library_id}/ask/stream` streams live status steps (`retrieving`, `verifying`, `composing`), verified citations, and generated answers directly to the React UI with zero polling.
- Dynamic Enterprise Glossary & Synonym Disambiguation: configurable corporate acronyms, abbreviations and domain glossaries (`/api/synonyms`, `config/synonyms.json`), with multi-word phrase prioritization and interactive management in the Settings tab.
- Advanced Chat & Document Actions: export full conversations with citations to Markdown (`.md`), reset active chat session without page reload, copy answers and citations with visual feedback, and real-time document filtering by extension (`PDF`, `DOCX`, `PPTX`, `XLSX`, `TXT`, `MD`) and filename.
- Enterprise Documentation: Italian operational and deployment manual in [docs/GUIDA_OPERATIVA_AZIENDA.md](GUIDA_OPERATIVA_AZIENDA.md) and English administrator guide in [docs/RUNBOOK.md](RUNBOOK.md).
- Dedicated React Interface with real-time streaming feedback, first-access onboarding wizard, Connectors & Automations tab, FastAPI backend, automated test suite (backend `pytest`, frontend `vitest`, Locust load scenarios, pytest performance benchmarks).



## Product principles

1. **Local first.** A cloud API key alone never enables cloud processing.
2. **Evidence before generation.** Every substantive answer must cite an accessible document or abstain.
3. **Library isolation.** Retrieval is constrained to the chosen library before context reaches the assistant.
4. **Documents are untrusted data.** Retrieved text cannot authorize tools or actions.
5. **Originals and versions matter.** Citations remain linked to the document version that supported the answer.
