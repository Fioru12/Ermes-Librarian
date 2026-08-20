# Third-party notices

Ermes Knowledge is distributed under the MIT License (see `LICENSE`). It bundles
no third-party source code, but depends on the open-source packages listed here.
Each remains under its own license, held by its respective authors.

The inventory was generated from installed package metadata and from
`frontend/package-lock.json` — not hand-written — so it reflects the versions
actually resolved. Regenerate it when dependencies change.

**Every declared dependency is under a permissive license** (MIT, BSD-3-Clause,
Apache-2.0 or ISC). None imposes a copyleft obligation on this project or on
work that builds upon it.

## Python — runtime and test dependencies

Declared in `requirements.txt`.

| Package | Version | License |
|---|---|---|
| `chromadb` | 1.5.8 | Apache-2.0 |
| `fastapi` | 0.136.1 | MIT |
| `filelock` | 3.29.0 | MIT |
| `httpx` | 0.28.1 | BSD-3-Clause |
| `langfuse` | 4.14.4 | MIT |
| `lark` | 1.3.1 | MIT |
| `llama-index-core` | 0.14.20 | MIT |
| `llama-index-embeddings-ollama` | 0.9.0 | MIT |
| `llama-index-llms-ollama` | 0.10.1 | MIT |
| `llama-index-readers-file` | 0.6.0 | MIT |
| `llama-index-vector-stores-chroma` | 0.5.5 | MIT |
| `ollama` | 0.6.2 | MIT |
| `pydantic` | 2.13.4 | MIT |
| `pypdf` | 6.10.2 | BSD-3-Clause |
| `pytest` | 9.0.3 | MIT |
| `pytest-asyncio` | 1.3.0 | Apache-2.0 |
| `pytest-timeout` | 2.4.0 | MIT |
| `python-docx` | 1.2.0 | MIT |
| `python-dotenv` | 1.2.2 | BSD-3-Clause |
| `python-multipart` | 0.0.22 | Apache-2.0 |
| `uvicorn` | 0.47.0 | BSD-3-Clause |

## JavaScript — application and build dependencies

Declared in `frontend/package.json`.

| Package | Version | License |
|---|---|---|
| `@eslint/js` | 10.0.1 | MIT |
| `@playwright/test` | 1.62.1 | Apache-2.0 |
| `@testing-library/jest-dom` | 6.9.1 | MIT |
| `@testing-library/react` | 16.3.2 | MIT |
| `@testing-library/user-event` | 14.6.1 | MIT |
| `@types/d3` | 7.4.3 | MIT |
| `@types/react` | 18.3.31 | MIT |
| `@types/react-dom` | 18.3.7 | MIT |
| `@vitejs/plugin-react` | 4.7.0 | MIT |
| `autoprefixer` | 10.5.0 | MIT |
| `d3` | 7.9.0 | ISC |
| `eslint` | 10.8.1 | MIT |
| `eslint-plugin-react-hooks` | 7.1.1 | MIT |
| `eslint-plugin-react-refresh` | 0.5.4 | MIT |
| `globals` | 17.11.0 | MIT |
| `jsdom` | 29.1.1 | MIT |
| `lucide-react` | 0.344.0 | ISC |
| `openapi-typescript` | 7.13.0 | MIT |
| `postcss` | 8.5.20 | MIT |
| `react` | 18.3.1 | MIT |
| `react-dom` | 18.3.1 | MIT |
| `tailwindcss` | 3.4.19 | MIT |
| `typescript` | 5.9.3 | Apache-2.0 |
| `typescript-eslint` | 8.67.0 | MIT |
| `vite` | 7.3.6 | MIT |
| `vitest` | 4.1.10 | MIT |

Transitive dependencies are not listed individually; they are pinned in
`frontend/package-lock.json` and resolved from `requirements.txt`.

## Machine-readable SBOM

`sbom.json` is a CycloneDX 1.6 software bill of materials for the Python
dependency surface. Regenerate it whenever `requirements.txt` changes:

```powershell
.\.venv-ermes\Scripts\python.exe -m pip install cyclonedx-bom
.\.venv-ermes\Scripts\python.exe -m cyclonedx_py requirements requirements.txt -o sbom.json --output-format JSON
```

The generator warns about any dependency without an exact version, which is how
two unpinned requirements (`httpx`, `langfuse`) were found: `langfuse>=2.60.0`
was resolving to 4.14.4, two major versions past the declared floor, so CI and a
developer machine could install different code with nothing reporting it. Both
are now pinned.

## External services

These are not dependencies and are not redistributed. They run under their own
terms, and Ermes contacts them only when an administrator explicitly enables the
corresponding mode:

- **Ollama** — local model runtime, contacted only in `local_ollama` mode or
  when local semantic search is enabled.
- **OpenRouter** and other approved providers — contacted only in
  `approved_openrouter` / `approved_provider` mode, which additionally requires
  the global `ERMES_LIBRARY_CLOUD_CONSENT` flag.
- **Langfuse** — optional LLM tracing, inactive unless keys are configured.

A configured API key alone never enables cloud processing; see the product
principles in `README.md`.
