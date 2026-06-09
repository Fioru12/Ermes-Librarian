# Manuale Utente — WinSarp AI Hub

## Indice
1. [Introduzione](#1-introduzione)
2. [Requisiti di sistema](#2-requisiti-di-sistema)
3. [Primo avvio](#3-primo-avvio)
4. [Interfaccia principale](#4-interfaccia-principale)
5. [Come fare una domanda](#5-come-fare-una-domanda)
6. [Leggere le risposte](#6-leggere-le-risposte)
7. [Caricare documenti (admin)](#7-caricare-documenti-admin)
8. [Pannello amministrativo](#8-pannello-amministrativo)
9. [FAQ e risoluzione problemi](#9-faq-e-risoluzione-problemi)
10. [Integrazione con Teams/Slack](#10-integrazione-con-teamsslack)
11. [Sicurezza](#11-sicurezza)

---

## 1. Introduzione

**WinSarp AI Hub** è un sistema RAG (Retrieval-Augmented Generation) che permette di consultare documentazione aziendale in linguaggio naturale, ricevendo risposte precise basate esclusivamente sui documenti caricati.

### A cosa serve
- ✅ Cercare formule WinSarp nel catalogo ufficiale
- ✅ Consultare manuali, procedure e normative aziendali
- ✅ Ottenere risposte immediate senza cercare manualmente nei documenti
- ✅ Ridurre le richieste ripetitive ai referenti interni

### Caratteristiche principali
- **100% offline**: tutti i dati restano sulla macchina aziendale
- **Privacy garantita**: nessuna informazione esce dal perimetro interno
- **Basato sui fatti**: le risposte sono ancorate ai documenti caricati
- **Multi-modulo**: puoi organizzare la documentazione per reparti/argomenti

---

## 2. Requisiti di sistema

### Server (dove gira il programma)
- **Sistema operativo**: Windows 10/11 o Windows Server
- **Python**: 3.11 o superiore
- **RAM**: minimo 8 GB (16 GB consigliati)
- **Spazio disco**: 2 GB per i modelli AI + spazio per i documenti
- **Ollama**: installato e configurato (incluso nello script di avvio)

### Client (da dove ti colleghi)
- **Browser**: Chrome, Edge, Firefox (ultima versione)
- **Rete**: stessa LAN del server (es. http://192.168.1.100:8502)

---

## 3. Primo avvio

### Se hai lo script automatico (raccomandato)
1. Doppio click su **`AVVIA_FINALE.bat`**
2. Lo script controlla e installa automaticamente:
   - Ambiente virtuale Python
   - Dipendenze (se mancanti)
   - Avvia Ollama (se non in esecuzione)
   - Scarica i modelli AI (solo la prima volta)
   - Apre il browser su `http://127.0.0.1:8502`

### Se avvii manualmente
Apri un terminale nella cartella del progetto ed esegui:
```
ollama serve
python -m streamlit run app.py --server.port 8502
```
Poi apri il browser all'indirizzo `http://localhost:8502`.

---

## 4. Interfaccia principale

### Schermata iniziale
All'avvio vedrai una schermata di benvenuto con:
- **Card informative**: come usare l'app in 3 passi
- **Suggerimenti rapidi**: consigli per l'uso
- **Sidebar a sinistra**: menu di navigazione

### Sidebar (menu a sinistra)
La sidebar contiene:
1. **Selettore modulo**: scegli l'area di lavoro (es. WinSarp, HR, Produzione)
2. **Stato sistema**: verifica che Ollama e i modelli siano funzionanti
3. **Documenti**: lista dei file nel modulo corrente
4. **Pulsanti azione**: Aggiorna, Cancella DB, Nuova conversazione
5. **Admin documenti**: accesso riservato agli amministratori
6. **Aiuto e FAQ**: guida rapida

### Area principale
- **Header**: nome del modulo attivo e modello AI in uso
- **Chat**: storico delle domande e risposte
- **Input chat**: campo per scrivere le domande

---

## 5. Come fare una domanda

### Passo 1: Seleziona il modulo
Dalla sidebar, scegli l'area di lavoro corretta dal menu a tendina.

### Passo 2: Scrivi la domanda
Digita nel campo di input in basso. Sii specifico per ottenere risposte migliori.

#### Esempi per modulo WinSarp:
| Domanda | Cosa ottieni |
|---|---|
| "Dammi la formula per straordinario oltre 8 ore con causale ST" | Formula completa con codice |
| "Qual è la formula per la gestione del turno notturno?" | Formula e spiegazione |
| "Mostrami la formula per arrotondare entrata e uscita" | Codice e dettagli logica |

#### Esempi per altri moduli:
| Domanda | Cosa ottieni |
|---|---|
| "Qual è la procedura per richiedere ferie?" | Procedure dal documento HR |
| "Come si compila il report mensile?" | Istruzioni passo-passo |

### Suggerimenti per domande efficaci
- ✅ Usa un linguaggio chiaro e diretto
- ✅ Specifica il contesto se necessario
- ✅ Se non ottieni ciò che cerchi, riformula
- ❌ Evita domande troppo generiche ("dimmi tutto")

---

## 6. Leggere le risposte

Ogni risposta contiene:

### Intestazione
- **Numero risposta**: progressivo nella conversazione
- **Tempo di risposta**: quanto ha impiegato il modello

### Badge di confidenza
Indica quanto la risposta è supportata dai documenti:
- ✅ **Confidenza alta**: la risposta è ben supportata
- ⚠️ **Confidenza media**: supporto parziale, verifica
- 🔴 **Confidenza bassa**: pochi documenti pertinenti trovati

### Blocco formula (modulo WinSarp)
- **Codice formula**: il codice WinSarp in formato compresso
- **Pulsante "Copia formula"**: copia il codice negli appunti
- **Logica applicata**: spiegazione passo-passo della formula
- **Errori**: eventuali problemi sintattici rilevati

### Fonti
Clicca su "Fonti" per vedere da quali documenti è stata estratta la risposta:
- Nome del file di origine
- Score di similarità (più alto = più pertinente)
- Anteprima del chunk di testo utilizzato

### Feedback
Dopo ogni risposta puoi valutare:
- 👍 **Utile**: la risposta è stata corretta e pertinente
- 👎 **Non utile**: la risposta non soddisfaceva la richiesta

---

## 7. Caricare documenti (admin)

### Cosa puoi caricare
- **PDF** (.pdf)
- **Word** (.docx)
- **Testo** (.txt)

### Procedura
1. Vai su **Admin documenti** nella sidebar
2. Inserisci le credenziali admin
3. Scegli il modulo di destinazione (o creane uno nuovo)
4. Trascina o seleziona i file
5. Clicca **"Salva file nel modulo"**
6. Clicca **"Aggiorna"** per reindicizzare

### Limiti
- **Dimensione massima**: 50 MB per upload (configurabile)
- **Formati supportati**: solo .txt, .pdf, .docx
- **Numero file**: senza limite specifico (dipende dalla RAM)

### Dopo l'upload
- I file vengono salvati in `/documenti/[nome_modulo]/`
- I nuovi documenti saranno disponibili dopo l'indicizzazione
- Puoi verificare nella lista documenti della sidebar

---

## 8. Pannello amministrativo

### Accesso admin
Per accedere al pannello admin è necessaria la password configurata dall'amministratore di sistema.

### Funzioni disponibili

#### Gestione utenti
- **Creare nuovi utenti**: assegna ruolo (admin/viewer)
- **Modificare ruoli**: cambia i permessi di un utente
- **Disattivare utenti**: blocca l'accesso senza eliminare

#### Manutenzione
- **Rimuovi orfani**: pulisce collezioni ChromaDB non più utilizzate
- **Cancella DB**: rimuove l'indice vettoriale di un modulo
- **Reindicizza**: forza la reindicizzazione dopo modifiche ai documenti

#### Log e monitoraggio
- **Audit log**: tutte le operazioni admin sono tracciate in `logs/audit_admin.jsonl`
- **Sessioni**: ogni conversazione è salvata in `logs/session_[data].jsonl`
- **Rotazione log**: i log più vecchi di 30 giorni vengono eliminati automaticamente

### Modifica tema
Dalla sidebar puoi passare da **tema scuro** (default) a **tema chiaro** con un click.

---

## 9. FAQ e risoluzione problemi

### "Ollama non risponde"
1. Apri un terminale (cmd o PowerShell)
2. Esegui: `ollama serve`
3. Ricarica la pagina nel browser

### "Risposta non trovata / confidenza bassa"
- I documenti caricati potrebbero non contenere l'informazione richiesta
- Prova a riformulare la domanda con termini diversi
- Verifica che il modulo corretto sia selezionato
- Controlla che i documenti siano stati caricati correttamente

### "I documenti non vengono indicizzati"
- Verifica che i file siano in formato supportato (.txt, .pdf, .docx)
- Controlla che i file non siano vuoti o corrotti
- Clicca "Aggiorna" dopo aver caricato nuovi file

### "La risposta è troppo lunga/scorretta"
- I modelli AI open-source possono occasionalmente produrre risposte non perfette
- Usa il feedback 👍/👎 per segnalare la qualità
- Riformula la domanda in modo più preciso

### "La conversazione è piena"
- Lo storico messaggi ha un limite (configurabile)
- Clicca "Nuova conversazione" per ricominciare
- Puoi scaricare il log della conversazione prima di cancellarla

### "Come faccio backup?"
Il sistema non ha backup automatici. Si consiglia di:
- Copiare periodicamente la cartella `documenti/`
- Copiare `security/users.json`
- `chroma_db/` è ricostruibile dai documenti

### "Cosa è il rate limiting?"
Il sistema limita il numero di richieste per proteggere da abusi:
- **Richieste**: max 60 al minuto per sessione
- **Upload**: max 20 per ora, max 500MB totali
- Se superi i limiti, vedrai un messaggio di avviso

### "I log di audit sono sicuri?"
Sì, ogni entry di audit è firmata con HMAC-SHA256 per garantire l'integrità. Se qualcuno modifica un log, la firma non corrisponderà più.

---

## 10. Integrazione con Teams/Slack

### Panoramica
WinSarp AI Hub espone un'API REST che può essere utilizzata da:
- Bot Microsoft Teams
- App Slack
- Script automatici
- Applicazioni custom

### Endpoint API
| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/health` | Stato del sistema |
| `POST` | `/query` | Esegue una domanda RAG |
| `GET` | `/modules` | Lista moduli disponibili |

### Esempio di chiamata (PowerShell)
```powershell
$body = @{
    query = "Dammi la formula per straordinario"
    module = "WinSarp"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8503/query" `
    -Method POST `
    -Body $body `
    -ContentType "application/json" `
    -Headers @{Authorization = "Bearer token-di-sviluppo"}
```

### Per l'integrazione Teams
1. Crea un bot in Microsoft Teams (tramite Azure Bot Service)
2. Configura il bot per chiamare l'API REST di WinSarp
3. La risposta può essere formattata come card adattiva

### Per l'integrazione Slack
1. Crea una Slack App con lo slash command `/winsarp`
2. Configura il comando per chiamare l'API
3. La risposta viene mostrata direttamente in chat

> **Nota**: l'integrazione Teams/Slack richiede sviluppo aggiuntivo. Contatta l'amministratore di sistema per assistenza.

---

## 11. Sicurezza

### Funzionalità di sicurezza implementate

#### Autenticazione
- **Password hashing**: le password sono memorizzate con PBKDF2-HMAC-SHA256
- **Timing-safe comparison**: protezione contro timing attacks
- **Rate limiting**: massimo 60 richieste/minuto per sessione

#### Integrità dei dati
- **Audit trail crittografato**: ogni operazione admin è firmata con HMAC-SHA256
- **Atomic write**: le modifiche ai file sono atomiche per evitare corruzione
- **File lock**: operazioni concorrenti sono sincronizzate

#### Protezione
- **Input validation**: tutti gli input sono validati prima dell'uso
- **Path traversal protection**: prevenzione accesso a file fuori dalla directory
- **CORS configurabile**: controllo degli origini delle richieste API

### Variabili d'ambiente per sicurezza
```env
# Password admin (cambia prima della produzione)
ERMES_ADMIN_PASSWORD=LaTuaPasswordForte

# API key per REST API
ERMES_API_KEY=genera-con-python-secrets

# Secret per audit logs HMAC
ERMES_AUDIT_SECRET=genera-con-python-secrets
```

### Best practices
1. **Cambia la password admin** prima di mettere in produzione
2. **Genera API key forte** con: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
3. **Genera audit secret** con: `python -c "import secrets; print(secrets.token_hex(32))"`
4. **Non versionare** i file `.env` e `security/users.json`
5. **Usa HTTPS** se esponi il servizio in rete pubblica

---

**WinSarp AI Hub v1.1** — Documentazione aggiornata al 2026  
Per assistenza tecnica: contatta l'amministratore di sistema