# Contributing to Ermes Knowledge

Thank you for improving the project. Keep changes focused on the local-first document-library product.

## Before opening a pull request

1. Never commit credentials, customer files, generated databases, logs or `storage/`.
2. Use synthetic documents in tests and examples.
3. Preserve the evidence-first contract: responses must cite authorized sources or abstain.
4. Do not introduce an automatic fallback that can send documents to a cloud provider.
5. Run the relevant checks:

```powershell
.\.venv-ermes\Scripts\python.exe -m pytest -q tests/test_library_store.py tests/test_document_parser.py tests/test_evidence_assistant.py tests/test_library_evaluation.py tests/test_local_auth.py
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
```

## Pull request expectations

Describe the user outcome, security implications, test evidence and any migration or configuration change. Keep the legacy WinSarp material isolated from the Ermes Knowledge product flow unless a change explicitly concerns archival compatibility.
