"""Template per lo sviluppo di un Connettore Dati Personalizzato per Ermes Knowledge.

Utilizza questo file come punto di partenza per connettere Ermes a qualsiasi sorgente
dati aziendale proprietaria: Database SQL (PostgreSQL, Oracle, SQL Server), ERP (SAP, Dynamics),
CRM (Salesforce, HubSpot) o API REST interne.

Per renderlo utilizzabile dalle API senza modificare Ermes: metterlo in un
modulo importabile (es. azienda_connettori/erp.py) ed elencarlo in
ERMES_CONNECTOR_PLUGINS=azienda_connettori.erp. La chiamata a
register_connector() in fondo al file lo registra all'import; da quel momento
il tipo compare in GET /api/connectors/types e si usa con /test, /sync e
/sync/delta come quelli integrati.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Assicura che la root del progetto sia nel sys.path se eseguito come script standalone
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core.connectors.base import BaseConnector, DeltaSyncResult, RemoteDocument  # noqa: E402
from core.connectors.registry import register_connector  # noqa: E402


class CustomEnterpriseConnector(BaseConnector):
    """Connettore personalizzato verso una sorgente dati aziendale."""

    connector_type = "custom_enterprise_source"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config=config)
        self.api_endpoint = self.config.get("api_endpoint", "https://api.intranet.azienda.it")
        self.api_token = self.config.get("api_token", "")
        self.category_filter = self.config.get("category_filter", "ALL")

    def test_connection(self) -> tuple[bool, str]:
        """Verifica se le credenziali e l'endpoint sorgente sono validi e raggiungibili."""
        try:
            if not self.api_endpoint:
                return False, "Endpoint API non configurato."
            # In produzione: eseguire un ping HTTP o handshake verso il sistema
            return True, "Connessione riuscita alla sorgente aziendale."
        except Exception as exc:
            return False, f"Errore di connessione: {exc}"

    def fetch_documents(self) -> list[RemoteDocument]:
        """Estrae l'elenco completo dei documenti dal sistema sorgente.

        Ogni RemoteDocument restituito verrà automaticamente elaborato, chunkato
        e indicizzato nella biblioteca di destinazione configurata.
        """
        ok, msg = self.test_connection()
        if not ok:
            raise RuntimeError(f"Test connessione fallito: {msg}")

        # Esempio: record estratti da database SQL o API REST
        sample_records = [
            {
                "id": "DOC-9001",
                "name": "Procedura_Gestione_Incidenti_Sicurezza.txt",
                "content": (
                    "In caso di violazione o incidente di sicurezza, il dipendente deve "
                    "notificare immediatamente il Security Operations Center (SOC) entro 60 minuti. "
                    "È fatto divieto assoluto di spegnere i dispositivi coinvolti per preservare i log."
                ).encode(),
                "media_type": "text/plain",
                "source_url": "https://intranet.azienda.it/docs/DOC-9001",
                "updated_at": datetime.now(UTC).isoformat(),
                "author": "Security Team",
                "department": "Cybersecurity",
            },
            {
                "id": "DOC-9002",
                "name": "Policy_Rimborsi_Spese_Trasferta.txt",
                "content": (
                    "I rimborsi spese per trasferte aziendali devono essere inviati entro il giorno 5 "
                    "del mese successivo. È richiesta la ricevuta fiscale per qualsiasi spesa superiore a 10 Euro. "
                    "Il massimale per il vitto giornaliero è fissato a 60 Euro."
                ).encode(),
                "media_type": "text/plain",
                "source_url": "https://intranet.azienda.it/docs/DOC-9002",
                "updated_at": datetime.now(UTC).isoformat(),
                "author": "HR & Finance",
                "department": "Amministrazione",
            },
        ]

        documents: list[RemoteDocument] = []
        for rec in sample_records:
            doc = RemoteDocument(
                id=rec["id"],
                name=rec["name"],
                content=rec["content"],
                media_type=rec["media_type"],
                source_url=rec["source_url"],
                last_modified=rec["updated_at"],
                metadata={
                    "author": rec["author"],
                    "department": rec["department"],
                    "connector": self.connector_type,
                },
            )
            documents.append(doc)

        return documents

    def fetch_delta(self, delta_token: str | None = None) -> DeltaSyncResult:
        """Estrae solo i documenti modificati o eliminati rispetto all'ultimo sync."""
        # Se il sistema esterno supporta una sync incrementale (es. updated_at > delta_token),
        # è possibile restituire solo il delta, altrimenti fallback automatico su fetch_documents.
        return super().fetch_delta(delta_token=delta_token)


register_connector(CustomEnterpriseConnector.connector_type, CustomEnterpriseConnector)


# Test standalone:
if __name__ == "__main__":
    connector = CustomEnterpriseConnector(
        config={"api_endpoint": "https://api.intranet.example.com", "api_token": "secret_token_123"}
    )

    print(f"Test connessione connettore '{connector.connector_type}':")
    success, message = connector.test_connection()
    print(f"Stato: {'OK' if success else 'KO'} - {message}")

    print("\nEstrazione documenti...")
    docs = connector.fetch_documents()
    print(f"Documenti estratti: {len(docs)}")
    for d in docs:
        print(f"- [{d.id}] {d.name} ({len(d.content)} bytes) -> URL: {d.source_url}")
