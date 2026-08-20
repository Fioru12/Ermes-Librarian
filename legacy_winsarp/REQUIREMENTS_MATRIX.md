# Requirements Matrix (PDF 14 Apr 2026)

Riferimento: `Adobe Scan 14 apr 2026.pdf` (progetto RAG aziendale).  
Nota: la soluzione usa LLM open-source locale (`Ollama`) al posto di Claude, come richiesto.

## Copertura Requisiti

- **R1 - Q/A su documentazione interna, risposte ancorate ai documenti**
  - Stato: **Coperto**
  - Evidenza: pipeline RAG in `rag_engine.py` + retrieval con fonti in `app.py`.

- **R2 - Indicizzazione documenti (PDF/Word/Testo), embedding, vector DB locale**
  - Stato: **Coperto**
  - Evidenza: `SimpleDirectoryReader` con `.pdf/.docx/.txt`, embedding Ollama, ChromaDB locale in `rag_engine.py`.

- **R3 - Interfaccia web per utenti**
  - Stato: **Coperto**
  - Evidenza: applicazione Streamlit (`app.py` + `theme.py`).

- **R4 - Caricamento documenti da pannello amministrativo**
  - Stato: **Coperto**
  - Evidenza: sezione `Admin documenti` in sidebar, upload multiplo e salvataggio modulo in `app.py`.

- **R5 - Gestione utenti e permessi**
  - Stato: **Coperto (base)**
  - Evidenza: `governance.py` (admin/viewer, auth locale, gestione utenti); controlli ruolo admin in `app.py`.
  - Nota: implementazione locale file-based, sufficiente per fase interna; estendibile a directory aziendale/SSO.

- **R6 - Riservatezza dati / operatività locale**
  - Stato: **Coperto**
  - Evidenza: Ollama su host locale (`OLLAMA_HOST`), ChromaDB locale, documenti locali, nessuna API cloud obbligatoria.

- **R7 - Tracciabilità operazioni amministrative**
  - Stato: **Coperto**
  - Evidenza: audit append-only in `logs/audit_admin.jsonl` tramite `append_audit()`.

- **R8 - Documentazione tecnica e avvio**
  - Stato: **Coperto**
  - Evidenza: `README.md` con prerequisiti, avvio, configurazione e test.

- **R9 - Qualità e verificabilità**
  - Stato: **Coperto (base)**
  - Evidenza: test in `tests/test_winsarp.py`, `tests/test_utils.py`, `tests/test_governance.py`.

## Gap Residui (non bloccanti)

- Integrazione identity enterprise (AD/LDAP/SSO) non presente.
- Dashboard KPI/monitoring avanzato non presente (solo log/audit base).
- Workflow di deploy formalizzato (CI/CD) non ancora codificato nel repository.

## Decisione Architetturale Applicata

- Modello consigliato dal documento: API Claude + RAG custom.
- Adattamento richiesto: **LLM open-source locale**.
- Scelta implementata: **Ollama locale + LlamaIndex + ChromaDB**.
