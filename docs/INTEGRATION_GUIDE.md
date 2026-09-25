# Guida all'integrazione

Come un sistema esterno (script, microservizio, n8n/Zapier, bot di chat,
agente AI) parla con Ermes Knowledge. Ogni percorso, campo e variabile qui
sotto corrisponde al codice in `api/` e `config/`: se diverge, ha ragione il
codice, e questa guida va corretta.

La documentazione OpenAPI generata dal server resta il riferimento completo:
`http://<host>:8502/docs` (Swagger) e `http://<host>:8502/redoc`. La porta
predefinita è `8502` (`ERMES_PORT`).

## Indice

1. [Autenticazione](#1-autenticazione)
2. [Domande a una biblioteca](#2-domande-a-una-biblioteca)
3. [Streaming SSE](#3-streaming-sse)
4. [Caricamento documenti](#4-caricamento-documenti)
5. [Automazioni: n8n, Zapier, Make](#5-automazioni-n8n-zapier-make)
6. [Bot di chat: Slack, Teams, Telegram](#6-bot-di-chat-slack-teams-telegram)
7. [MCP per agenti AI](#7-mcp-per-agenti-ai)
8. [Connettori custom](#8-connettori-custom)
9. [SCIM 2.0](#9-scim-20)

---

## 1. Autenticazione

Tutte le rotte `/api/*` falliscono chiuse: senza credenziali valide rispondono
`401`. Da un client esterno si usa un header Bearer:

```http
Authorization: Bearer <chiave>
```

La chiave può essere:

- la chiave di sistema `ERMES_API_KEY` (break-glass, da tenere fuori dal codice);
- una chiave personale gestita per utente (ruotabile dall'amministrazione);
- un token OIDC, se `ERMES_OIDC_ENABLED` è attivo.

Le chiavi personali ereditano i permessi dell'utente: una chiave di un
`viewer` non può caricare documenti.

## 2. Domande a una biblioteca

```bash
curl -X POST "http://localhost:8502/api/libraries/$LIBRARY_ID/ask" \
  -H "Authorization: Bearer $ERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Entro quando va consegnata la nota spese?", "top_k": 3}'
```

Corpo della richiesta (`AskLibraryRequest`):

| Campo | Tipo | Note |
|---|---|---|
| `question` | string | 2–2000 caratteri |
| `top_k` | int | 1–10, default 3 |
| `conversation_id` | string \| null | opzionale |
| `history` | `[{"question": "..."}]` | al massimo 3 domande precedenti, usate solo per riscrivere una domanda di raffinamento |

Risposta (campi principali):

```json
{
  "answer_id": "…",
  "library": {"id": "…", "name": "Amministrazione"},
  "question": "Entro quando va consegnata la nota spese?",
  "answer": "…",
  "status": "answered",
  "evidence": {"coverage": "supported", "reason": ""},
  "citations": [
    {
      "document_id": "…",
      "filename": "nota-spese.md",
      "version": 1,
      "content_hash": "sha256:…",
      "chunk_id": "…",
      "locator": "Sezione: Scadenze",
      "excerpt": "La nota spese va consegnata entro il quinto giorno lavorativo…",
      "marker": 1,
      "relevance_score": 0.8123,
      "injection_suspected": false
    }
  ],
  "meta": {"assistant_mode": "evidence_only", "…": "…"}
}
```

`status` vale `"abstained"` quando la biblioteca non contiene evidenza
sufficiente: in quel caso l'integrazione deve mostrare l'astensione, non
inventare una risposta. `injection_suspected: true` segnala una fonte che
contiene istruzioni rivolte al modello e il cui testo non è stato usato.

Esistono anche `POST /api/libraries/federated/search` e
`POST /api/libraries/federated/ask/stream`, che cercano su più biblioteche
(`library_ids`, fino a 20) rispettando i permessi di ciascuna.

## 3. Streaming SSE

`POST /api/libraries/{library_id}/ask/stream` accetta lo stesso corpo di
`/ask` e risponde `text/event-stream` con eventi nominati:

| Evento | `data` |
|---|---|
| `status` | `{"step": "retrieving" \| "verifying" \| "composing"}` |
| `citations` | `{"citations": [...]}` |
| `answer` | `{"chunk": "..."}` |
| `done` | la risposta finale, stessa forma di `/ask` |
| `error` | `{"detail": "..."}` |

Un evento `done` può arrivare subito dopo `verifying`, senza `citations` né
`answer`: è il caso dell'astensione. Un esempio completo di parsing è in
[`examples/integrations/client_sdk_example.ts`](../examples/integrations/client_sdk_example.ts).

## 4. Caricamento documenti

```bash
curl -X POST "http://localhost:8502/api/libraries/$LIBRARY_ID/documents" \
  -H "Authorization: Bearer $ERMES_API_KEY" \
  -F "file=@./procedura.pdf"
```

Richiede il ruolo `editor` sulla biblioteca. Il file passa per validazione
del tipo, limite di dimensione (`ERMES_ADMIN_MAX_UPLOAD_MB`, oltre il quale
risponde `413`) e scansione antivirus prima dell'indicizzazione, che avviene
in background: lo stato si segue su
`GET /api/libraries/{library_id}/ingestion-jobs`.

## 5. Automazioni: n8n, Zapier, Make

Rotte pensate per i nodi HTTP delle piattaforme di automazione, sotto
`/api/integrations/automation`, con la stessa autenticazione Bearer:

| Rotta | Scopo |
|---|---|
| `GET /libraries` | elenco delle biblioteche visibili, per popolare le tendine |
| `POST /ask` | `{"library_id", "question"}` → risposta, citazioni e `evidence_found` |
| `POST /ingest` | `{"library_id", "filename", "content", "is_base64", "media_type"}` |

`/ingest` applica le stesse guardie del caricamento normale (ruolo, tipo,
dimensione, antivirus): non è una scorciatoia.

## 6. Bot di chat: Slack, Teams, Telegram

Webhook in ingresso sotto `/api/integrations`:

| Rotta | Segreto richiesto |
|---|---|
| `POST /api/integrations/slack` | `ERMES_SLACK_SIGNING_SECRET` |
| `POST /api/integrations/teams` | `ERMES_TEAMS_WEBHOOK_SECRET` |
| `POST /api/integrations/telegram` | `ERMES_TELEGRAM_BOT_TOKEN`, `ERMES_TELEGRAM_WEBHOOK_SECRET` |

Senza il segreto la rotta risponde `503`: non accetta richieste non firmate.
Il canale esterno va collegato a una biblioteca con
`POST /api/libraries/{library_id}/integrations`
(`{"platform": "slack", "external_channel_id": "..."}`).

## 7. MCP per agenti AI

Il server MCP è esposto via HTTP sotto `/api/mcp` (non è un processo stdio):

| Rotta | Scopo |
|---|---|
| `GET /api/mcp/info` | metadati del server |
| `GET /api/mcp/tools` | strumenti disponibili |
| `POST /api/mcp/call` | `{"name", "arguments"}` → esegue uno strumento |
| `POST /api/mcp/rpc` | JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`) |

Strumenti: `list_libraries`, `ask_library`, `search_documents`. Ogni chiamata
usa l'identità della chiave Bearer, quindi l'agente vede solo ciò che vedrebbe
l'utente proprietario della chiave.

## 8. Connettori custom

I connettori stanno in `core/connectors/` ed estendono `BaseConnector`
(`core/connectors/base.py`): implementano `test_connection()` e
`fetch_documents()`, che restituisce oggetti `RemoteDocument`; `fetch_delta()`
è facoltativo e di default ripiega sulla scansione completa.

Un connettore aziendale non richiede di modificare Ermes: si scrive in un
modulo Python importabile che chiama
`core.connectors.registry.register_connector("nome_tipo", Classe)` all'import,
e si elenca il modulo in `ERMES_CONNECTOR_PLUGINS` (più moduli separati da
virgola). `GET /api/connectors/types` (solo admin) mostra i tipi disponibili,
integrati e plugin.

Due regole volute:

- si caricano **solo** i moduli elencati, non tutto ciò che è installato:
  importare un modulo ne esegue il codice con i permessi di Ermes;
- un plugin non può sostituire un tipo integrato (`local_folder` ha controlli
  sui percorsi che un sostituto potrebbe non avere), e un plugin che non si
  importa o non registra nulla fa rispondere `503` alle rotte dei connettori
  invece di sparire in silenzio.

Punto di partenza:
[`examples/integrations/custom_connector_template.py`](../examples/integrations/custom_connector_template.py).

## 9. SCIM 2.0

Provisioning utenti da un identity provider (Entra ID, Okta, Keycloak) sotto
`/scim/v2` (senza prefisso `/api`):

- `GET /scim/v2/ServiceProviderConfig`, `GET /scim/v2/Schemas`
- `GET|POST /scim/v2/Users`, `GET|PUT|PATCH|DELETE /scim/v2/Users/{id}`

Autenticazione Bearer con `ERMES_SCIM_TOKEN` (o, in alternativa,
`ERMES_API_KEY`). Si disattiva con `ERMES_SCIM_ENABLED=0`. Oggi è implementata
la risorsa `Users`; `Groups` non c'è ancora.
