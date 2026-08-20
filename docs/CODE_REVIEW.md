# Revisione del codice — 20 agosto 2026

Revisione sistematica del codice di prodotto di Ermes Knowledge, condotta dopo che
tre bug nello script di avvio si sono rivelati istanze della **stessa causa radice**.
Questo documento riporta cosa è stato trovato, cosa è stato corretto, cosa è stato
verificato sano e cosa non è stato possibile verificare.

## Metodo

La revisione non si è basata sulla rilettura del codice. I bug che l'hanno
motivata erano tutti invisibili a lettura e visibili solo a runtime, quindi il
metodo è stato:

- ricostruzione del **grafo reale degli import** a partire da `api/`, per separare
  il codice eseguito dal codice presente;
- esecuzione della suite (più volte, per escludere intermittenza), del type-check
  del frontend e della build di produzione;
- confronto tra ciò che il repository **dichiara** e ciò che contiene davvero
  (build Docker, contratto OpenAPI, documentazione, script di avvio);
- distinzione esplicita tra `TRACKED` e `untracked`, perché è la differenza tra
  "funziona sulla mia macchina" e "funziona per chi clona".

## La causa radice comune: il fallimento silenzioso

I tre bug iniziali di `scripts/avvia_ermes.ps1` erano lo stesso errore in tre forme:

1. `try { curl.exe ... } catch {}` — `curl.exe` è un processo esterno: una
   connessione rifiutata imposta un exit code, **non** solleva un'eccezione
   PowerShell. Il `catch` non si attivava mai e i passi 1–3 riportavano `OK`
   senza aver verificato nulla.
2. `ConvertFrom-Json` su stringa vuota restituisce `$null` senza sollevare
   eccezioni, quindi l'health check stampava `Sistema:  (ollama= chroma=)`
   invece di un errore.
3. `Start-Process -FilePath "npx"` risolve a `npx.ps1`; su una macchina dove
   l'estensione `.ps1` è associata a un editor di testo, il comando apriva
   silenziosamente l'editor invece di avviare Vite.

In tutti e tre i casi il codice *sembrava* corretto e riportava successo senza
aver eseguito il controllo. La revisione ha cercato questa categoria — non i tre
casi specifici — in tutto il repository, e l'ha ritrovata altrove.

A revisione già conclusa se n'è manifestato un quarto caso, nello stesso script:
la riga finale `$Host.UI.RawUI.ReadKey(...)`, protetta da un `try/catch` con il
commento «in modalità non interattiva, esci senza attendere». Il `try/catch` non
protegge nulla: con stdin rediretto `ReadKey` non solleva un'eccezione, **si
blocca**. Due esecuzioni dello script sono rimaste appese oltre un'ora prima che
il problema venisse notato. Sostituito con un controllo che distingue davvero i
due casi (`[Environment]::UserInteractive` e `[Console]::IsInputRedirected`), e
verificato: lo script ora esce da solo con exit 0 in 19 secondi.

Vale la pena notarlo perché è il caso più istruttivo dei quattro. Il commento
descriveva l'intenzione corretta, il codice sembrava implementarla, e il difetto
si è manifestato solo osservando che due processi non erano mai terminati.

## Finding

### 1. La build Docker era rotta per chiunque clonasse il repository — *corretto*

`Dockerfile` conteneva `COPY data/ ./data/`, ma `data/` **non è tracciata**: contiene
solo il database SQLite di runtime. La build funzionava in locale, dove la cartella
esiste, e falliva per chiunque partisse da un clone pulito — cioè esattamente
l'azienda o la persona che valuta il progetto.

Corretto rimuovendo il `COPY` (la cartella è già creata vuota a runtime dal `RUN mkdir`
successivo). Stessa famiglia del bug `COPY modules/` corretto il 19 agosto.

### 2. `COPY *.py ./` spediva in produzione tutta la root — *corretto*

La glob copiava nell'immagine ogni file `.py` presente in root, inclusi moduli morti
e file vuoti. Sostituita da un `COPY config.py ./` esplicito.

### 3. `api.py` in root era codice irraggiungibile — *rimosso*

In CPython un package vince sempre su un modulo omonimo: `import api` risolveva
**sempre** a `api/__init__.py`, quindi il contenuto di `api.py` non poteva mai
eseguirsi (verificato con `import api; api.__file__`). Il file si presentava come
"wrapper di retrocompatibilità" e il suo docstring elencava endpoint WinSarp
(`api/formule.py`, `api/graph.py`) come se fossero il prodotto attuale.

Una revisione precedente lo aveva classificato come shim legittimo: quella
valutazione era sbagliata ed è stata corretta in `docs/ROADMAP_V2.md`.

### 4. Il contratto OpenAPI versionato era falso — *rimosso*

`openapi.json` (104 KB, in root) documentava **44 endpoint inesistenti** — inclusi
`/api/winsarp/catalog` e `/api/graph` — e **ne ometteva 38 realmente presenti**.
Un artefatto generato una volta e mai rigenerato: peggio che assente, perché chi
tenta un'integrazione ci si basa. Il contratto reale resta disponibile e sempre
aggiornato su `/openapi.json`.

### 5. 1.389 righe di codice morto in `core/`, con 25 test a coprirlo — *rimosse*

Sei moduli non raggiungibili dal prodotto: `core/utils.py`, `core/error_handler.py`,
`core/response_cache.py`, `core/ai/response_cache.py`, `core/ai/semantic_cache.py`,
`core/ai/memory.py` (i primi due `response_cache` erano quasi-duplicati fra loro).

Tre di questi erano usati **solo dai test**. Il risultato è che 25 test su 173 (14%)
verificavano codice che il prodotto non esegue mai: una parte del segnale "tutta la
suite è verde" era falsa sicurezza. La suite è ora 148 test, tutti su codice vivo.

### 6. Due gate di CI che non potevano fallire — *corretto*

`.github/workflows/ci.yml` eseguiva `mypy ... || true` e `bandit ... || true`.
Il `|| true` forza l'exit code a zero: un controllo di sicurezza che fallisce
riportava successo senza lasciare alcun segnale — la stessa forma dei bug del
launcher, applicata alla pipeline.

Sostituiti con `continue-on-error: true` a livello di step: il comportamento
(non bloccare la build) è invariato, ma è **dichiarato** e la run risulta
visibilmente gialla invece che verde. Corretta anche l'esclusione `-x
core/templates,core/evaluation`, che puntava a cartelle non più esistenti, e
rimosso `api.py` dal target della scansione.

### 7. La documentazione descriveva un altro prodotto — *corretto*

- `DEVELOPER.md` — la guida che un valutatore tecnico legge per prima — descriveva
  l'architettura WinSarp: elencava `rag_engine.py`, `formula_builder.py`,
  `knowledge_graph.py`, `core/winsarp/`, `modules/`, dichiarava "871 test" e
  indicava `.venv` invece di `.venv-ermes`. Riscritta sul grafo dei moduli verificato.
- Quattro documenti WinSarp (`DELIVERABLE_FINALE.md` e `MANUALE_UTENTE.md`, in due
  versioni diverse ciascuno fra root e `docs/`) spostati sotto `legacy_winsarp/docs/`.
  Chi apriva `docs/` concludeva che il prodotto fosse un motore di formule.

### 8. Gli script di collegamento sul Desktop erano rotti — *corretto*

`README.md` afferma che `scripts/CREA_COLLEGAMENTO_DESKTOP.ps1` crea un collegamento
al launcher ufficiale. In realtà lo script **non creava alcun collegamento**: scriveva
un altro script in un percorso hardcoded inesistente (`C:\ProgettoRAG_DEV\`, mentre il
progetto sta in `C:\Progetti\ProgettoRAG_DEV`) e nominava il collegamento
"WinSarp AI Hub". Riscritto perché faccia ciò che il README dichiara.

Rimossi inoltre due duplicati rotti: `crea_shortcut.ps1` (percorso assoluto errato,
target non tracciato) e `crea_shortcut_bat.ps1`, la cui catena
`AVVIA.vbs → AVVIA_DIRETTO.bat` puntava a un file spostato nel legacy.

### 9. Un lock file che pip non può leggere — *rimosso*

`requirements-lock.txt` era codificato in **UTF-16** (il default di `pip freeze >`
in PowerShell). `pip install -r` fallisce con `UnicodeDecodeError`: era un lock file
inutilizzabile, non referenziato da CI, Docker o documentazione.

### 10. Configurazione che pubblicizzava funzionalità inesistenti — *annotato*

`docker-compose.yml` espone `ERMES_SLACK_*`, `ERMES_TEAMS_*` e `ERMES_TELEGRAM_*`,
ma l'unica implementazione è in `legacy_winsarp/api/integrations.py` e nessuna route
viva le espone (verificato sulle 92 route dell'app). Le variabili sono state lasciate
— servono con `ENABLE_LEGACY_WINSARP=1` — ma commentate esplicitamente, per non
promettere integrazioni che il prodotto non ha.

## Revisione della struttura

Una seconda passata, sulla forma anziché sulla logica: dove vivono i file, come
sono nominati, e cosa comunica l'organizzazione a chi apre il repository.

### 11. Il percorso di installazione non portava al percorso di avvio — *corretto*

Il finding strutturale più grave. I tre installer (`SETUP_INSTALL.bat`,
`SETUP_RAPIDO.bat`, `SETUP_INIZIALE.ps1`) creavano tutti un ambiente virtuale
chiamato `.venv`. Ma `scripts/avvia_ermes.ps1` cerca `.venv-ermes` ed esce con
errore se non lo trova. **Chi seguiva gli script di installazione otteneva
un'installazione "riuscita" che poi non si avviava.** Gli stessi installer
rimandavano inoltre a `AVVIA.bat`, che era stato spostato in `scripts/archive/`.

Consolidato su un solo installer allineato al launcher; i duplicati sono in
`legacy_winsarp/scripts/`. Corretti anche `smoke_test.bat`, `test_all.bat` e
`VERIFICA_SISTEMA.bat`, che puntavano al venv sbagliato.

### 12. Contenuto legacy dentro le cartelle del prodotto — *spostato*

- `tests/verify_final.py` era un test WinSarp (chiama `/api/formula/generate`)
  che viveva nella suite del prodotto e **non veniva mai eseguito**, perché il
  nome non corrisponde al pattern `test_*.py` di pytest.
- `docs/` conteneva `winsarp_grammar.txt`, più due file grafici orfani con zero
  riferimenti — uno dei quali, `literature_review_reading_read_icon_179858.ico`,
  con il nome di download da un sito di icone stock. `docs/` ora contiene
  soltanto documentazione.
- `scripts/STOP.ps1` era intitolato "WinSarp AI Hub" e fermava **Streamlit**,
  cioè la UI legacy — non il frontend del prodotto. Riscritto come vera
  controparte del launcher, e verificato dal vivo: ferma backend e frontend e
  controlla che le porte siano davvero libere.

### 13. Un verificatore che approvava sempre — *corretto*

`VERIFICA_SISTEMA.bat` stampava «TUTTI I PREREQUISITI SONO SODDISFATTI»
incondizionatamente, anche se ogni singolo controllo aveva stampato un errore.
Fra le dipendenze "principali" che verificava c'era `streamlit`, che non è
nemmeno in `requirements.txt`: quel controllo falliva sempre, senza conseguenze.
Riscritto con un conteggio reale dei fallimenti, e verificato su entrambi i
percorsi — quello di successo e quello di errore, che è poi quello che era rotto.

### 14. Organizzazione e naming — *documentati*

Metà del repository (173 file tracciati su 339) è `legacy_winsarp/`: è una scelta
esplicita, ma vale la pena saperlo prima di giudicare le proporzioni del
progetto. I nomi degli script mescolano maiuscole e minuscole, italiano e
inglese. Invece di rinominarli in massa — churn e rischio di rotture per un
guadagno cosmetico — la convenzione è stata resa esplicita in `scripts/README.md`,
che documenta anche a cosa serve ciascuno script.

## Verificato sano

Non tutto era da correggere. Questi punti sono stati controllati e sono risultati solidi:

- **Autorizzazione**: ogni endpoint amministrativo dipende da `_require_role("admin")`.
  `tests/test_api_auth_coverage.py` percorre le route dell'app e fa fallire la CI se
  un endpoint viene aggiunto senza protezione, con allowlist esplicita dei percorsi
  pubblici. Un import di autenticazione inutilizzato in `api/users.py` è risultato
  un semplice residuo, non un buco.
- **Accesso al legacy dal codice vivo**: l'unico caso in codice raggiungibile
  (`api/models.py:75-80`) è **fatto correttamente** — gated dietro il flag e con
  l'eccezione loggata, non ingoiata. Le altre fughe verso `legacy_winsarp` erano
  tutte in moduli morti, ora rimossi.
- **Frontend**: `tsc --noEmit` pulito, zero errori di tipo; build di produzione
  riuscita (1484 moduli, 230 KB JS).
- **Suite**: 146 test passati e 2 skipped, stabile su esecuzioni ripetute (~8,2 s).
- **Import inutilizzati**: 4 reali su tutto il codice di prodotto, ora rimossi.

## La CI era rossa da sempre, e nessuno se n'era accorto

La revisione si era chiusa dichiarando `ruff`, `mypy`, `bandit` e la build Docker
come **non verificati**, perché `pip install` falliva con
`CERTIFICATE_VERIFY_FAILED` dietro la TLS inspection aziendale. Guardando la CI
per delegarle quei controlli, è emerso che **falliva a ogni push, in 0 secondi**,
da settimane: nessun test e nessun controllo di sicurezza era mai realmente girato.

### 15. Un errore di workflow annullava l'intera pipeline — *corretto*

Il job di deploy usava `if: ${{ secrets.SLACK_WEBHOOK_URL != '' }}`. Il contesto
`secrets` non è utilizzabile in una condizione `if`: è un errore di validazione
che GitHub rileva prima di eseguire qualunque job, quindi l'intera run falliva
istantaneamente. Spostato il segreto in un `env` di job.

### 16. `npm ci` era irriproducibile — *corretto*

`package.json` dichiarava `vite ^5.1.4` e `vitest ^4.1.10`, ma vitest 4 richiede
vite `^6 || ^7 || ^8`. Una violazione di peer dependency che npm tollerava in
locale, dove `node_modules` esisteva già, ma che rendeva impossibile un lockfile
riproducibile: npm 11 risolveva esbuild 0.21.5, npm 10 pretendeva 0.28.2.
Rigenerare il lock non bastava — il conflitto era nelle dipendenze dichiarate.

### 17. Quattro test verdi che non verificavano nulla — *corretti*

Il finding più serio emerso dalla CI. `test_e2e_no_api_key_rejected` e
`test_e2e_invalid_api_key_rejected` interrogavano `/modules`, un endpoint WinSarp
rimosso. La catch-all della SPA risponde `200` con l'index HTML a qualunque
percorso sconosciuto, e i test asserivano soltanto `status_code == 200`: passavano
servendo una pagina HTML, senza toccare un endpoint API. **Due test il cui nome
promette di verificare il rifiuto dell'autenticazione non verificavano alcuna
autenticazione.** In CI, dove `frontend/dist/` non viene costruito, la catch-all
non è montata e i 404 hanno reso visibile l'inganno.

Riscritti su endpoint reali, con il content-type fra le asserzioni, così un `200`
servito dalla SPA non può più far passare un test per sbaglio. Verificati
riproducendo la condizione della CI in locale, cioè rimuovendo `frontend/dist/`.

### 18. Il gate ruff era inutilizzabile — *corretto*

Prima esecuzione reale: 616 violazioni, di cui **551 in `legacy_winsarp/`**, che
seppellivano le 65 del prodotto. Il legacy è ora escluso dal lint — è codice
congelato — e le 65 reali sono state corrette.

L'ostacolo di partenza è stato risolto senza aggirare la sicurezza: il trust
store di Windows contiene già la CA aziendale, quindi è stato esportato e passato
a `pip --cert`. Verifica reale del certificato, non disabilitata.

## Stato dei controlli

Tutti e sei i job della pipeline sono verdi, per la prima volta: `lint`, `test`,
`frontend`, `pre-deploy-backup`, `docker`, `deploy`. Il job `docker` costruisce
e pubblica l'immagine, il che verifica anche la correzione del finding 1 — la
build che in locale non era eseguibile.

Resta un solo disallineamento noto: il venv locale non ha `pytest-timeout`, che
la CI usa (`pytest --timeout=30`), quindi in locale la suite gira senza timeout
per test. Si risolve con `pip install -r requirements.txt` una volta configurato
il certificato aziendale.

## Effetto complessivo

| | Prima | Dopo |
|---|---|---|
| File tracciati in root | 37 | 18 |
| Righe Python di prodotto | 10.809 | 9.228 |
| Test | 173 (25 su codice morto) | 148 (tutti su codice vivo) |
| Moduli `core/` non raggiungibili | 6 | 0 |
| Endpoint falsi nel contratto OpenAPI | 44 | contratto generato a runtime |

Nessuna funzionalità rimossa. Le uniche modifiche a `api/` sono state due import
inutilizzati: le 92 route dell'app sono rimaste invariate, e la suite è verde a ogni
passo della pulizia.
