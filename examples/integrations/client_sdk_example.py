"""Client Python minimo per le API di Ermes Knowledge.

Mostra i tre usi più comuni da un servizio esterno: elencare le biblioteche,
fare una domanda con citazioni, caricare un documento. I campi letti sono
quelli restituiti davvero da api/libraries.py (vedi docs/INTEGRATION_GUIDE.md).

    ERMES_BASE_URL=http://localhost:8502 ERMES_API_KEY=... python client_sdk_example.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class Citation:
    filename: str
    version: int
    locator: str
    excerpt: str
    relevance_score: float
    injection_suspected: bool


@dataclass(frozen=True)
class Answer:
    answer: str
    status: str  # "answered" oppure "abstained"
    citations: list[Citation]
    raw: dict[str, Any]

    @property
    def abstained(self) -> bool:
        return self.status == "abstained"


class ErmesClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self._client = httpx.Client(
            base_url=(base_url or os.getenv("ERMES_BASE_URL", "http://localhost:8502")).rstrip("/"),
            headers={"Authorization": f"Bearer {api_key or os.environ['ERMES_API_KEY']}"},
            timeout=60.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ErmesClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_libraries(self) -> list[dict[str, Any]]:
        resp = self._client.get("/api/libraries")
        resp.raise_for_status()
        return resp.json()["items"]

    def ask(self, library_id: str, question: str, top_k: int = 3) -> Answer:
        resp = self._client.post(
            f"/api/libraries/{library_id}/ask",
            json={"question": question, "top_k": top_k},
        )
        resp.raise_for_status()
        data = resp.json()
        return Answer(
            answer=data.get("answer", ""),
            status=data.get("status", "abstained"),
            citations=[
                Citation(
                    filename=c["filename"],
                    version=c.get("version", 1),
                    locator=c.get("locator", ""),
                    excerpt=c.get("excerpt", ""),
                    relevance_score=c.get("relevance_score", 0.0),
                    injection_suspected=c.get("injection_suspected", False),
                )
                for c in data.get("citations", [])
            ],
            raw=data,
        )

    def upload_document(self, library_id: str, file_path: str | Path) -> dict[str, Any]:
        """Richiede il ruolo editor; l'indicizzazione prosegue in background."""
        path = Path(file_path)
        with path.open("rb") as handle:
            resp = self._client.post(
                f"/api/libraries/{library_id}/documents",
                files={"file": (path.name, handle)},
                timeout=120.0,
            )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    with ErmesClient() as client:
        libraries = client.list_libraries()
        print(f"Biblioteche visibili: {len(libraries)}")
        if libraries:
            result = client.ask(libraries[0]["id"], "Quali sono le procedure principali?")
            if result.abstained:
                print("Nessuna evidenza sufficiente: il sistema si astiene.")
            else:
                print(result.answer)
                for c in result.citations:
                    print(f"  [{c.filename} v{c.version} · {c.locator}] {c.excerpt[:80]}")
