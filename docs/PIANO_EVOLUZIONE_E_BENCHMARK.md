# 🚀 Ermes Knowledge — Benchmark Competitivo e Piano di Evoluzione (2026)

> **Documento:** Analisi di Posizionamento Tecnologico e Roadmap di Innovazione  
> **Versione Progetto:** 2.4.1  
> **Data:** Ottobre 2026 (priorita' riviste il 27 ottobre 2026, vedi sezione 4)  
> **Stato:** Strategico / Architettura  
> **Natura:** documento di lavoro. Le colonne "Gap" del confronto sono ipotesi non verificate; il confronto controllato con gli altri progetti e' nel README. Le date della roadmap sono indicative.  

---

## 1. Executive Assessment dello Stato Attuale (v2.4.1)

Ermes Knowledge e' un prodotto funzionante e ben testato, ma **non ancora provato in produzione da utenti esterni**. Cio' che e' verificato (test, CI, monitoraggio su Docker) e cio' che non lo e' (carico reale, consegna degli avvisi su Slack/Teams, prova con screen reader) e' elencato in [`CHANGELOG.md`](../CHANGELOG.md) e [`docs/BENCHMARKS.md`](BENCHMARKS.md). Punti di forza dell'architettura:

- **Evidence-First:** risposte che citano il documento da cui arrivano e rifiuto esplicito quando le fonti non bastano (`NON_EVIDENCE`), con un verificatore delle evidenze (`core/evidence_verifier.py`). Riduce le risposte inventate, non le elimina: la misura e' in [`docs/BENCHMARKS.md`](BENCHMARKS.md).
- **Data Sovereignty & Local-First:** Funzionamento 100% offline nativo con Ollama/vLLM; nessuna dipendenza o telemetria cloud forzata.
- **Sicurezza e governance:**
  - Isolamento delle biblioteche: il controllo di accesso avviene prima che il contesto arrivi al modello, ed e' coperto da test.
  - Quarantena deterministica preventiva per attacchi di Prompt Injection indiretta nei documenti (`core/injection_guard.py`).
  - Registro di audit a catena (SHA-256 / HMAC): rende evidente una manomissione, non la impedisce (`core/audit_chain.py`).
  - Gestione identità RBAC integrata con OIDC/SSO e mappatura automatica dei gruppi ai ruoli di biblioteca.
  - Strumenti per esportazione (Art. 15) e cancellazione (Art. 17) dei dati di un utente. Non e' una certificazione di conformita' GDPR.
- **Integrazioni e Canali Estesi:** Connettori cartelle NAS/SMB, Microsoft Graph (SharePoint/OneDrive), Confluence, S3, WebDAV, server nativo Model Context Protocol (MCP), webhook per n8n/Zapier e bot per Slack, Teams e Telegram.
- **Esperienza Desktop:** un lanciatore Windows in C# (`scripts/launcher/ErmesLauncher.cs`, si compila con `scripts/build_exe.ps1`; il binario non e' nel repository) con istanza unica, icona nell'area di notifica e apertura in finestra propria tramite Edge o Chrome in modalita' app.
- **Affidabilità e qualità del codice:** oltre 850 test backend, oltre 110 test frontend, suite E2E in CI, Tailwind 4 (0 avvisi npm) e backend dati SQLite o PostgreSQL + pgvector.

**Punti deboli misurati (27 ottobre 2026).** La suite PMI (`python evaluation/run_library_eval.py --suite pmi`: 10 documenti realistici, 172 domande) mostra che la configurazione predefinita non mantiene ancora la promessa principale. Dettagli in [`docs/RETRIEVAL_EVALUATION.md`](RETRIEVAL_EVALUATION.md):

| Configurazione predefinita (solo parole, nessun modello) | Valore |
|---|---|
| Domande dirette | 0.952 |
| Parafrasi | 0.569 (scende a 0.35-0.40 con ~25 documenti estranei per biblioteca) |
| Astensione | 0.178 (2 su 45 con documenti estranei) |
| Trappole (argomento presente, risposta assente) | 2 su 20 |

La verifica dell'evidenza e' l'unico rimedio misurato (16/16 astensioni sul gold set storico), ma sulla suite PMI non e' ancora misurata.

---

## 2. Benchmark con i Top Progetti Open-Source (2025/2026)

L'analisi dell'ecosistema globale di riferimento su GitHub evidenzia i benchmark di settore e i trend dominanti:

| Progetto / Framework | Punti di Forza Riconosciuti | Gap Rispetto a Ermes | Cosa Possiamo Mutuare per Ermes |
|---|---|---|---|
| **RAGFlow** (`infiniflow/ragflow`) | **Deep Document Understanding:** Parsing visuale avanzato di layout complessi, tabelle annidate e note a piè di pagina. | Architettura pesante, requisiti di risorse elevati; governance e permessi meno integrati. | **Table & Layout Parsing:** estrazione di tabelle complesse in formato Markdown strutturato preservando intestazioni di colonna. |
| **AnythingLLM** (`Mintplex-Labs/anythingllm`) | Installazione desktop "one-click", UI moderna, gestione intuitiva delle cartelle e dei modelli locali. | Controllo accessi e verifica anti-allucinazione meno rigorosi; audit log basilare. | **Visual Document Preview:** drawer laterale interattivo per sfogliare i documenti sorgente. |
| **Open WebUI** (`open-webui/open-webui`) | Interfaccia in stile ChatGPT, personalizzazione prompt, community enorme. | Orientato al modello generalista, debole su isolamento formale delle fonti aziendali e conformità GDPR. | Fluidità dell'interfaccia conversazionale e controlli di generazione dinamici. |
| **Anthropic Contextual Retrieval** | **Contextual Chunking:** arricchimento dei chunk di testo con un breve prefisso contestuale dell'intero documento prima dell'embedding. | Tecnica di ricerca (non un'applicazione completa). | **Eliminazione dell'amnesia dei chunk:** riduzione stimata del 35-49% dei fallimenti di retrieval per frasi che non contengono il soggetto esplicito. |
| **LightRAG / GraphRAG** | **Graph-Augmented Retrieval:** estrazione di entità e relazioni per collegare fatti distribuiti su file diversi. | Costoso computazionalmente per corpora ampi; latenza di indicizzazione elevata. | **Knowledge Graph opzionale:** utile per interrogazioni relazionali (es. mappa fornitori-normative-contratti). |
| **Google NotebookLM** | **Studio & Sintesi:** trasformazione rapida dei file in guide, FAQ, briefing e audio overview (podcast). | Piattaforma proprietaria cloud Google; non utilizzabile per dati riservati on-premise. | **Potenziamento del tab Studio:** generazione "one-click" di executive briefing e domande di onboarding da intere biblioteche. |

---

## 3. Matrice dei Differenziatori di Ermes (Il nostro "Moat")

Ermes Knowledge possiede caratteristiche uniche che i software concorrenti generalisti raramente implementano:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ERMES ENTERPRISE ADVANTAGES                          │
├────────────────────────────────┬────────────────────────────────────────────┤
│ 1. Isolamento delle            │ Il contesto passa dal filtro di accesso    │
│    Biblioteche                 │ della biblioteca prima di arrivare al      │
│                                │ modello (coperto da test).                 │
├────────────────────────────────┼────────────────────────────────────────────┤
│ 2. Evidenza Obbligatoria       │ Ogni risposta cita la fonte, oppure        │
│                                │ dichiara NON_EVIDENCE.                     │
├────────────────────────────────┼────────────────────────────────────────────┤
│ 3. Difesa Iniezione Documenti  │ Il testo nei file è trattato come input    │
│    (Untrusted Data Layer)      │ ostile e bonificato prima del modello.     │
├────────────────────────────────┼────────────────────────────────────────────┤
│ 4. Audit Trail a catena        │ Rilevamento di manomissioni sul registro   │
│    HMAC-SHA256                 │ delle operazioni (non impedimento).        │
├────────────────────────────────┼────────────────────────────────────────────┤
│ 5. Lanciatore Windows          │ Nessuna finestra di terminale in vista;    │
│                                │ avvio dei servizi in background.           │
└────────────────────────────────┴────────────────────────────────────────────┘
```

---

## 4. Priorita' riviste (27 ottobre 2026)

Target scelto: **PMI e professionisti con vincoli di riservatezza** (studi, uffici qualita', amministrazione), installazione locale. Le funzioni enterprise gia' presenti (Helm, worker distribuito, SCIM, PostgreSQL) restano nel codice ma non ricevono nuovo lavoro finche' un cliente reale non le chiede.

Criterio dell'ordine: prima cio' che impedisce a una PMI di usare Ermes o di fidarsi delle risposte, poi cio' che lo distingue dagli altri. Ogni voce indica come si misura il risultato.

### Gia' fatto (non riproporre)

| Voce | Dove |
|---|---|
| Pollice su/giu' con motivazione sulle risposte | `frontend/src/components/chat/ChatArea.tsx`, statistiche in Analytics |
| Visualizzatore PDF che apre la pagina citata | `ChatArea.tsx` (vista "PDF Pag. N") |
| Studio: briefing, FAQ, guida di studio, domande suggerite (ex Iniziativa 4) | `core/library_studio.py` |
| Report stampabile in PDF della conversazione (ex Iniziativa 6, in parte) | pulsante "Report PDF" |
| Verifica dell'evidenza con modello locale o con l'API cloud approvata per la biblioteca | `core/evidence_verifier.py` |
| Scelta esplicita del modello all'installazione: solo estratti, Ollama, API pubblica | `scripts/configure_ai.py`, `SETUP_WIZARD.bat` |
| Suite di valutazione PMI con trappole e domande colloquiali | `evaluation/pmi_corpus/`, `evaluation/pmi_gold_set.json` |

### Priorita' 1 — Bloccano l'uso o la fiducia

**1.1 Misurare la verifica dell'evidenza sulla suite PMI, poi decidere il default.**
- Comando: `run_library_eval.py --suite pmi --semantic --verify` (Ollama) oppure `--verify --verifier openrouter`.
- Se l'astensione sale a 0.9 o piu' senza perdere le dirette: ricerca a vettori + verifica diventano il default delle modalita' locale e cloud nel setup, e il numero va nel README.
- Se no: si lavora sul verificatore (prompt, modello) prima di qualsiasi altra voce.

**1.2 Installer senza prerequisiti.**
- Oggi servono Python 3.11 e Node.js installati a mano (`scripts/installer/ermes_setup.iss` lo dichiara: "non include Python").
- Obiettivo: un `.exe` che contiene Python embedded e il frontend gia' compilato. Chi installa non apre mai un terminale.
- Misura: installazione su un PC Windows pulito, senza Python ne' Node, in meno di 10 minuti.

**1.3 Aggiornamento in un clic.**
- Senza, ogni installazione resta ferma alla versione del giorno in cui e' stata fatta, comprese le correzioni di sicurezza.
- Obiettivo: controllo della versione all'avvio e aggiornamento con backup automatico prima e ritorno alla versione precedente se l'avvio fallisce.

**1.4 Email e PEC come documenti.**
- In una PMI italiana gran parte degli accordi sta nelle email (ordini, PEC, condizioni concordate con i fornitori).
- Obiettivo: lettura di `.eml` e `.msg` (mittente, data, oggetto come riferimento della citazione; allegati come documenti collegati), poi un connettore IMAP in sola lettura.
- Misura: domande sulle email aggiunte alla suite PMI.

**1.5 Dai giudizi negativi al gold set.**
- Il pollice giu' esiste, ma i giudizi restano nelle statistiche.
- Obiettivo: esportare le domande con giudizio negativo (testo della domanda, biblioteca, motivazione; mai il contenuto dei documenti) come candidati per il gold set, da rivedere a mano.
- Misura: il gold set cresce con domande vere degli utenti pilota.

### Priorita' 2 — Distinguono Ermes dagli altri

**2.1 Evidenziazione del passaggio nel PDF** (ex Iniziativa 1, completamento).
- Il PDF si apre gia' alla pagina giusta; manca il passaggio evidenziato. Serve conservare, in ingestione, la posizione del testo nella pagina.

**2.2 Confronto tra versioni di un documento.**
- Lo storico delle versioni esiste gia'. Rispondere a "cosa e' cambiato tra la revisione 3 e la 4 della procedura?" con le differenze citate per sezione e' raro negli altri prodotti ed e' molto richiesto da qualita', ISO e uffici legali.

**2.3 Scadenze e revisioni dei documenti.**
- Data di revisione o scadenza per documento (procedure ISO, DVR, certificati), avviso a chi ne e' responsabile, elenco dei documenti scaduti nella scheda Stato.

**2.4 Domande su piu' documenti** (ex Iniziativa 2).
- "Elenca tutte le scadenze nelle procedure" oggi fallisce: la ricerca restituisce tre passaggi. Serve scomporre la domanda in sotto-domande o raccogliere i dati in forma strutturata, con le stesse regole di citazione e astensione.

**2.5 Passaggi con il loro contesto** (ex Iniziativa 3).
- Prima, la versione gratuita: anteporre a ogni passaggio titolo del documento e della sezione prima dell'indicizzazione. Poi, solo se la misura lo giustifica, il prefisso generato dal modello.
- Misura: parafrasi e trappole sulla suite PMI, prima e dopo.

**2.6 Un reranker multilingue.**
- Quello provato peggiorava ogni configurazione, ma era addestrato quasi solo sull'inglese. Va provato un modello multilingue sulla suite PMI prima di scartare l'idea.

### Rimandato — Lo hanno altri, oggi non serve al target

| Voce | Perche' aspettare |
|---|---|
| Agenti che compiono azioni (compilare moduli, inviare email) | Aumenta i rischi e contraddice il principio "solo evidenze". |
| Voce: dettatura e lettura delle risposte (ex Iniziativa 5) | Gradevole, non decide l'adozione in una PMI. |
| Altri connettori (Notion, Jira, Salesforce...) | Le PMI usano soprattutto cartelle di rete, email, Google Drive e SharePoint: gli ultimi tre ci sono, l'email e' la 1.4. |
| Immagini e grafici nelle risposte (multimodale) | Costo alto, valore basso su regolamenti e procedure. |
| Knowledge graph (LightRAG / GraphRAG) | Costoso da indicizzare; da valutare solo se la 2.4 non basta. |
| Versione cloud gestita (SaaS) | Scelta di business, da fare dopo i primi utenti pilota. |

### Fuori dal codice, ma necessario

- **2-3 utenti pilota** (commercialista, piccola azienda, associazione) dopo la 1.1: due settimane d'uso osservato, le loro domande vere entrano nel gold set.
- **Guida per l'utente non tecnico**: installazione, prima biblioteca, cosa significa "non ho trovato evidenza".

## 5. Ordine di esecuzione

1. **1.1** Misura della verifica sulla suite PMI e scelta del default.
2. **1.2** e **1.3** Installer senza prerequisiti con aggiornamento.
3. Utenti pilota, con **1.5** attivo per raccogliere le loro domande.
4. **1.4** Email e PEC.
5. **2.1** e **2.2** Evidenziazione nel PDF e confronto tra versioni.
6. Il resto della priorita' 2, nell'ordine indicato dalle misure.

Le date non sono indicate: dipendono dall'esito della 1.1 e dal tempo disponibile. Il piano precedente (Iniziative 1-6 con diagramma di Gantt) resta nella cronologia Git.
