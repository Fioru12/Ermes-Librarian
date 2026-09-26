# Enterprise Integrations & Client SDKs

Questa cartella contiene esempi pratici e pronti all'uso per integrare **Ermes Knowledge** con applicazioni, servizi e banche dati esterne.

Per la documentazione architetturale completa, consulta la [Guida alle Integrazioni](../../docs/INTEGRATION_GUIDE.md).

---

## File inclusi

| File | Linguaggio | Descrizione |
|---|---|---|
| [`client_sdk_example.py`](client_sdk_example.py) | Python 3.11+ | Client SDK tipizzato (HTTPX) per interagire con le API di Ermes (Q&A con citazioni, lista librerie, upload documenti). |
| [`client_sdk_example.ts`](client_sdk_example.ts) | TypeScript / Node.js | Client SDK TypeScript fortemente tipizzato con supporto nativo allo streaming real-time SSE. |
| [`custom_connector_template.py`](custom_connector_template.py) | Python 3.11+ | Template di partenza per creare un connettore dati verso DB SQL aziendali, ERP (SAP/Dynamics) o CRM. |
