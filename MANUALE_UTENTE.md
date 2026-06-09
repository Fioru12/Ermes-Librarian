# Manuale Utente - Ermes Enterprise Knowledge Hub

## Prerequisiti

- **Ollama** in esecuzione con modelli:
  - `qwen2.5:7b` (LLM default)
  - `bge-m3` (embeddings)
- **Documenti** da indicizzare in `documenti/<modulo>/`

## Avvio rapido

```bash
# Windows - doppio click su scripts/AVVIA.bat
# Oppure manualmente:
.venv\Scripts\streamlit run app.py
```

Apri `http://127.0.0.1:8502` nel browser.

## Interfaccia

### Sidebar (sinistra)

| Controllo | Descrizione |
|-----------|-------------|
| Tema | Alterna tema scuro/chiaro |
| Modello LLM | Seleziona il modello Ollama per le risposte |
| Area di lavoro | Scegli il modulo documentale, ad esempio WinSarp |
| Stato sistema | Health check: Ollama, ChromaDB, documenti |
| Documenti | Elenco dei file indicizzati per il modulo attivo |
| Manutenzione | Re-indicizza, cancella indice, nuova conversazione |

### Area principale

- **Header**: modulo attivo, modello, modalita operativa
- **Modalita operativa**: `Recupero` per RAG classico o `Generazione` per formule WinSarp
- **Chat**: scrivi una domanda e premi Invio

## Funzionalita

- **Ricerca RAG**: interroga i documenti del modulo selezionato
- **Generazione formule WinSarp**: in modalita Generazione, produce codice WinSarp
- **Feedback**: thumbs up/down su ogni risposta
- **Sorgenti**: mostra i documenti usati per la risposta con confidenza
- **Esportazione**: copia formule con un click

## API REST

```bash
curl -X POST http://127.0.0.1:8502/query \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "domanda", "module": "WinSarp"}'
```

## Amministrazione

Accedi con le credenziali admin da `.env` per gestire utenti e audit log.

## Troubleshooting

| Problema | Soluzione |
|----------|-----------|
| "Ollama non raggiungibile" | Avvia Ollama e ricarica la pagina |
| "Modelli mancanti" | `ollama pull qwen2.5:7b && ollama pull bge-m3` |
| Nessun documento trovato | Metti file in `documenti/<modulo>/` e re-indicizza |
