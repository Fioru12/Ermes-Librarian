"""Load test per Ermes Knowledge — valida performance sotto carico.

Testa le operazioni principali:
- /api/libraries (listing biblioteche)
- /api/libraries/{id}/search (ricerca full-text, il cuore del prodotto)
- /api/libraries/{id}/documents/{doc_id}/search (ricerca per documento)

Uso:
    locust -f tests/load/locustfile.py --host http://localhost:8502 -u 10 -r 2 -t 30s

Dopo aver avviato il server con `uvicorn api:app`.
"""

import random
import tempfile
from pathlib import Path

from locust import HttpUser, between, task, events


# Dati di test per le query di ricerca
SEARCH_QUERIES = [
    "contratto",
    "pagamento",
    "scadenza",
    "procedura",
    "policy",
    "sicurezza",
    "ferie",
    "pausa pranzo",
    "lavoro",
    "dimissioni",
    "assunzione",
    "formazione",
    "rilascio",
    "budget",
    "fattura",
    "preavviso",
    "reclamo",
    "garanzia",
    "conferma",
    "urgenza",
]


class ErmesAPIUser(HttpUser):
    """Utente simulata che usa l'API Ermes."""

    wait_time = between(0.5, 2.0)  # pausa tra le richieste

    def on_start(self):
        """Setup: crea utente, login, crea biblioteca con documento di test."""
        self.username = f"loadtest_{self.user_id}"
        self.password = "StrongPassword!123!"
        self.api_key = None
        self.library_id = None
        self.document_ids = []

        # Crea utente direttamente nel governance
        try:
            from core.governance import create_or_update_user

            create_or_update_user(
                Path(tempfile.gettempdir()) / "ermes_loadtest_users.json", self.username, "admin", self.password
            )
        except Exception:
            pass

        # Login
        with self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.api_key = data.get("api_key")

        # Crea biblioteca
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with self.client.post(
            "/api/libraries",
            json={"name": f"LoadTest {self.user_id}", "visibility": "private"},
            headers=headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                self.library_id = resp.json().get("id")
                if self.library_id:
                    self._add_test_document(headers)

    def _add_test_document(self, headers):
        """Aggiunge un documento con contenuto ricercabile."""
        contents = [
            b"Il contratto di lavoro scade il 31 dicembre con preavviso di trenta giorni.",
            b"La procedura di pagamento prevede fattura entro 60 giorni dalla consegna.",
            b"La policy di sicurezza richiede formazione obbligatoria per i nuovi assunti.",
            b"Le ferie maturano in base ai mesi lavorati secondo il CCNL.",
            b"La pausa pranzo dura 60 minuti secondo l'articolo 8 del regolamento.",
        ]
        content = random.choice(contents)
        with self.client.post(
            f"/api/libraries/{self.library_id}/documents",
            files={"file": ("test.txt", content, "text/plain")},
            headers=headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                new_id = resp.json().get("id")
                if new_id:
                    self.document_ids.append(new_id)

    @task(10)
    def search_library(self):
        """Ricerca full-text nella biblioteca (operazione principale)."""
        if not self.library_id:
            return
        query = random.choice(SEARCH_QUERIES)
        with self.client.get(
            f"/api/libraries/{self.library_id}/search?q={query}",
            catch_response=True,
            name="/api/libraries/[id]/search",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(5)
    def list_libraries(self):
        """Listing biblioteche."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with self.client.get(
            "/api/libraries",
            headers=headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()

    @task(3)
    def search_in_document(self):
        """Ricerca all'interno di un documento specifico."""
        if not self.library_id or not self.document_ids:
            return
        doc_id = random.choice(self.document_ids)
        query = random.choice(SEARCH_QUERIES)
        with self.client.get(
            f"/api/libraries/{self.library_id}/documents/{doc_id}/search?q={query}",
            catch_response=True,
            name="/api/libraries/[id]/documents/[doc_id]/search",
        ) as resp:
            if resp.status_code == 200:
                resp.success()

    @task(1)
    def upload_document(self):
        """Upload nuovo documento (meno frequente)."""
        if not self.library_id:
            return
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        content = f"Documento di test numerato {random.randint(1, 10000)} per load testing.".encode()
        with self.client.post(
            f"/api/libraries/{self.library_id}/documents",
            files={"file": (f"load_{random.randint(1, 100000)}.txt", content, "text/plain")},
            headers=headers,
            catch_response=True,
            name="/api/libraries/[id]/documents",
        ) as resp:
            if resp.status_code == 201:
                new_id = resp.json().get("id")
                if new_id:
                    self.document_ids.append(new_id)
                resp.success()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Pulizia alla fine del test."""
    users_file = Path(tempfile.gettempdir()) / "ermes_loadtest_users.json"
    if users_file.exists():
        users_file.unlink()
