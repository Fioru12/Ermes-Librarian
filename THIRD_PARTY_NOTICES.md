# Third-party notices

Ermes Knowledge is distributed under the MIT License (see `LICENSE`). It bundles
no third-party source code, but depends on the open-source packages listed here.
Each remains under its own license, held by its respective authors.

Generated from installed package metadata and `frontend/package-lock.json` by
`scripts/generate_third_party_notices.py`. Do not edit by hand: regenerate it.
`tests/test_third_party_notices.py` fails when it no longer matches
`requirements.txt`, which is how four missing entries were found.

## Licence summary

Most dependencies are permissive (MIT, BSD, Apache-2.0, ISC). The exceptions
are listed here rather than averaged away, because an organisation with a
policy on copyleft needs to see them before adopting the product.

| Package | License | Where it applies |
|---|---|---|
| `psycopg` (Python) | GNU Lesser General Public License v3 (LGPLv3) | see the note below |
| `caniuse-lite` (JavaScript) | CC-BY-4.0 | build time only, not shipped in the bundle |
| `lightningcss`, `lightningcss-android-arm64`, `lightningcss-darwin-arm64` (+9 more) (JavaScript) | MPL-2.0 | build time only, not shipped in the bundle |

**`psycopg` (LGPL-3.0) is optional.** It is the PostgreSQL driver: the product
runs entirely on SQLite without it, and `ERMES_DATABASE_URL` is what turns the
PostgreSQL backend on. Used unmodified as an imported library, the LGPL does
not extend its terms to Ermes; it does require that whoever receives the
software can replace that library, which a `pip install` already allows.
An organisation that forbids (L)GPL outright can drop the line from
`requirements.txt` and stay on SQLite — nothing else depends on it.

**MPL-2.0 and CC-BY-4.0 on the JavaScript side** come from build tooling
(`lightningcss`, pulled in by Tailwind, and the `caniuse-lite` data set).
They are not modified and not redistributed in the built frontend.

## Python — runtime and test dependencies

Declared in `requirements.txt`.

| Package | Version | License |
|---|---|---|
| `fastapi` | 0.136.1 | MIT |
| `filelock` | 3.29.0 | MIT |
| `httpx` | 0.28.1 | BSD-3-Clause |
| `langfuse` | 4.14.4 | MIT |
| `lark` | 1.3.1 | MIT |
| `prometheus-client` | 0.26.0 | Apache-2.0 AND BSD-2-Clause |
| `psycopg` | 3.2.10 | GNU Lesser General Public License v3 (LGPLv3) |
| `pydantic` | 2.13.4 | MIT |
| `PyJWT` | 2.13.0 | MIT |
| `pypdf` | 6.10.2 | BSD-3-Clause |
| `pytest` | 9.0.3 | MIT |
| `pytest-asyncio` | 1.3.0 | Apache-2.0 |
| `pytest-benchmark` | 5.3.0 | BSD-2-Clause |
| `pytest-timeout` | 2.4.0 | MIT |
| `python-docx` | 1.2.0 | MIT |
| `python-dotenv` | 1.2.2 | BSD-3-Clause |
| `python-multipart` | 0.0.22 | Apache-2.0 |
| `uvicorn` | 0.47.0 | BSD-3-Clause |

## JavaScript — application and build dependencies

Declared in `frontend/package.json` (26 direct, 499 resolved in the lock file).

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

Licenses across the full resolved tree: MIT (387), ISC (51), Apache-2.0 (24), MPL-2.0 (12), BSD-2-Clause (8), BSD-3-Clause (5), BlueOak-1.0.0 (4), MIT-0 (2), Python-2.0 (1), CC-BY-4.0 (1), CC0-1.0 (1), Unlicense (1), 0BSD (1), (MIT OR CC0-1.0) (1).

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

- **Ollama** — local model server, contacted only for embeddings, evidence
  verification, question rewriting or `local_ollama` answers.
- **OpenRouter and approved cloud providers** — contacted only when both the
  global consent flag and the per-library policy authorise it.
- **Slack, Microsoft Teams, Telegram** — contacted only for libraries with a
  registered chat integration.
