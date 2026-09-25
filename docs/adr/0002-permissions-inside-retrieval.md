# ADR 0002 — I permessi si applicano dentro il recupero, non dopo

**Stato:** accettata · **Data:** formalizzata il 25 settembre 2026

## Contesto

In un RAG aziendale un documento riservato non deve solo restare fuori
dall'elenco dei file: non deve influenzare la risposta. Se il filtro si
applica *dopo* il recupero, il testo riservato ha già occupato un posto fra i
primi k, e può essere passato al modello, finire in una cache o nei log di
tracciamento, oppure spingere fuori un passaggio legittimo.

## Decisione

Il filtro dei permessi è un argomento del recupero stesso.

- Le biblioteche sono il primo confine: `get_library(library_id, actor)`
  fallisce per chi non ne è membro, prima di qualunque ricerca. Le query
  federate cercano solo sulle biblioteche visibili all'utente.
- Dentro una biblioteca, `_hidden_document_ids()` in `core/library_store.py`
  calcola i documenti con una allow-list (`document_acls`) che non include
  l'utente. L'insieme viene passato a `_keyword_candidates()`, e le righe
  candidate lette dal database (anche quelle del percorso semantico) vengono
  scartate se appartengono a un documento nascosto **prima** del calcolo dei
  punteggi, della pesatura per rarità e del reranking. Un documento nascosto
  non può quindi comparire né influenzare il punteggio degli altri.
- Il principio vale per tutte le vie d'accesso: API REST, streaming SSE,
  webhook di automazione, bot di chat e strumenti MCP usano la stessa
  identità autenticata e la stessa funzione di recupero, non una copia.

## Conseguenze

- Una chiave API o un token MCP vedono esattamente ciò che vedrebbe il loro
  proprietario: un agente AI esterno non ha privilegi propri.
- La cache di ricerca è partizionata per utente e invalidata per biblioteca
  quando cambiano documenti o ACL. L'invalidazione sulle ACL mancava fino al
  25 settembre 2026: un utente appena escluso da un documento continuava a
  riceverne gli estratti dalla propria cache fino al TTL (5 minuti). Trovato
  scrivendo questo documento e verificandone le affermazioni sul codice.
- La cache vive nel processo, ma l'invalidazione vale per tutte le repliche:
  ogni modifica a documenti o permessi incrementa, nella stessa transazione,
  un contatore per biblioteca sul database condiviso
  (`search_cache_generations`), che la ricerca legge insieme alla riga della
  biblioteca. Senza, con le due repliche predefinite del chart Helm la revoca
  valeva solo sulla replica che l'aveva ricevuta
  (`tests/test_search_cache_replicas.py`).
- Test di riferimento: `tests/test_document_acl.py`,
  `tests/test_connector_sync_authorization.py`,
  `tests/test_api_auth_coverage.py` (ogni rotta `/api/*` rifiuta le richieste
  non autenticate).

## Alternative scartate

- **Filtrare i risultati dopo il ranking**: più semplice, ma riduce i
  risultati sotto k e lascia il testo riservato nel percorso di calcolo.
- **Un indice per utente o per gruppo**: isolamento perfetto, ma moltiplica
  lo spazio e l'indicizzazione per il numero di combinazioni di permessi.
