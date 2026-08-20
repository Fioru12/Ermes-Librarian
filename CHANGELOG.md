# Changelog

Registro leggibile del lavoro su questo branch (`codex/ermes-knowledge-v01`). Per il dettaglio fase-per-fase con motivazioni, vedi [docs/ROADMAP_V2.md](docs/ROADMAP_V2.md); per i finding tecnici completi, [docs/AUDIT_2026-08-19.md](docs/AUDIT_2026-08-19.md).

## 2026-08-20

- **Trovato e risolto un bug reale di isolamento tra test** (`tests/test_e2e_api.py`): un `importlib.reload(config)` a tempo di collezione lasciava alcuni moduli agganciati alla config vecchia a seconda dell'ordine di raccolta dei test, causando un fallimento intermittente. Corretto mutando il singleton esistente dentro una fixture a tempo di esecuzione, con ripristino garantito. Verificato 3 volte di fila: 171 test passati, 0 falliti.
- Chiusa la lacuna di test su `core/backup_manager.py`: aggiunti test su restore (dry-run e reale), scrittura atomica, ed exclusione dei metadati, più un test di concorrenza reale su `_backup_lock`.
- Favicon collegato: esisteva già un logo brandizzato (`frontend/public/favicon.svg`) mai wireato — l'app usava un'emoji placeholder.
- **Recuperati file persi per un incidente durante la pulizia della cronologia git**: un'operazione di `git stash` + riscrittura della history + garbage collection ha temporaneamente reso irraggiungibili alcuni file non tracciati (`Ermes.ico`, `Ermes.png`, la scansione PDF personale, alcuni documenti legacy). Recuperati integralmente da un commit "orfano" rimasto nel repository prima che venisse definitivamente rimosso.
- Riorganizzati tre documenti legacy WinSarp trovati in root (`REQUIREMENTS_MATRIX.md`, `GO_LIVE_CHECKLIST.md`, `README_ENTERPRISE.md`) sotto `legacy_winsarp/`.

## 2026-08-19 — sessione principale

- **Isolamento completo di WinSarp**: l'intero motore formule legacy (core, UI Streamlit, endpoint, script, dati di valutazione, ~45 file di test) spostato sotto `legacy_winsarp/`, dietro un flag esplicito (`ENABLE_LEGACY_WINSARP`, spento di default). Nessuna cancellazione.
- **Commit del prodotto reale per la prima volta**: gran parte del backend (`api/`, moduli nuovi di `core/`) e l'intero frontend React non erano mai stati committati — messi in sicurezza dopo revisione, non alla cieca.
- **Trovati e corretti due bug che avrebbero rotto CI/Docker**: un `COPY` nel Dockerfile puntava a una cartella spostata; la CI usava un flag pytest senza la dipendenza corrispondente.
- **Scansione completa della cronologia git per segreti**: nessuna credenziale reale trovata. Trovato un documento di lavoro riservato committato dal primo commit — rimosso dall'intera cronologia (non solo cancellato), con force-push.
- **Retrieval misurato onestamente**: golden set espanso da 16 a 27 query (dirette, parafrasate, di astensione); numeri pubblicati con i limiti espliciti, non solo il caso migliore.
- **Aggiunto il recupero del documento originale in chat** (non solo dalla tab documenti), con audit log su ogni download.
- **Corpus demo con due biblioteche**, per dimostrare dal vivo l'isolamento tra biblioteche — non solo dichiararlo.
- Licenza MIT, one-pager di presentazione, guardia di regressione che blocca la CI se un endpoint viene spedito senza autenticazione.

## Prima del 2026-08-19

Vedi `git log` per la cronologia del progetto prima di questo lavoro di consolidamento (introduzione dell'HybridRetriever, upgrade modelli, framework di valutazione iniziale).
