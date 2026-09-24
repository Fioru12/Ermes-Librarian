# Ermes Knowledge — Guida Commerciale & Strategia di Vendita Enterprise

Questa guida definisce il posizionamento strategico, il listino prezzi, i profili d'offerta e le argomentazioni di vendita per la commercializzazione di **Ermes Knowledge** ad aziende e studi professionali.

---

## 1. Posizionamento di Mercato: L'Alternativa Sovrana

La maggior parte delle aziende desidera adottare l'Intelligenza Artificiale per valorizzare i propri archivi documentali, ma si scontra con tre barriere invalicabili:
1. **Rischio Legale & GDPR**: Divieto di inviare contratti, bilanci, brevetti o dati sanitari su server cloud pubblici esteri (OpenAI, Anthropic, Google).
2. **Paura delle Allucinazioni**: L'IA convenzionale inventa numeri, clausole e normative quando non conosce la risposta.
3. **Costi Imprevedibili**: I servizi a consumo fatturano milioni di token ogni mese, rendendo i costi ingestibili su larga scala.

**La Risposta di Ermes Knowledge**:
Ermes è una piattaforma documentale enterprise **Evidence-First e Sovrana**. Funziona on-premise o su cloud privato, risponde citando rigorosamente i passaggi dei documenti originali (`[1]`, `[2]`), si astiene con certezza matematica quando le evidenze mancano, e mantiene un registro crittografico immutabile conforme agli standard ISO 27001 e SOC 2.

---

## 2. Listino Prezzi Ufficiale (Modello a 3 Livelli)

```
┌─────────────────────────────────┐   ┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│           TIER SMALL            │   │           TIER MEDIUM           │   │         TIER ENTERPRISE         │
│         3.000€ - 5.000€         │   │        8.000€ - 15.000€         │   │        20.000€ - 35.000€        │
│             all'anno            │   │             all'anno            │   │             all'anno            │
├─────────────────────────────────┤   ├─────────────────────────────────┤   ├─────────────────────────────────┤
│ • 1 - 15 Utenti                 │   │ • 15 - 50 Utenti                │   │ • 50+ Utenti (Illimitati)       │
│ • Singolo Server / PC Locale    │   │ • Server Dedicato / VM Cloud    │   │ • Cluster Kubernetes (Helm)     │
│ • Database SQLite WAL           │   │ • Storage Cifrato AES-256-GCM   │   │ • PostgreSQL HA + SKIP LOCKED   │
│ • Auth Locale + Brute-force lock│   │ • Separazione Dipartimenti RBAC │   │ • SSO OIDC + Provisioning SCIM  │
│ • Monitor Cartelle di Rete      │   │ • Connettori Cloud (S3, Drive)  │   │ • Ingestion Workers Distribuiti │
│ • Citazioni e Zero Allucinazioni│   │ • Catena Audit SHA-256          │   │ • Metriche Prometheus & SIEM    │
└─────────────────────────────────┘   └─────────────────────────────────┘   └─────────────────────────────────┘
```

### Servizi Professionali Aggiuntivi (Una Tantum & Ricorrenti)

* **Setup & Installazione Iniziale**: **1.500€ – 5.000€** (una tantum)
  * Installazione su server cliente o configurazione cloud privato.
  * Bonifica e importazione dell'archivio documentale storico.
  * Sessione formativa di 1 ora per amministratori e personale.
* **Canone di Assistenza & Supporto SLA**: **300€ – 800€ / mese**
  * Aggiornamenti software continui e patch di sicurezza.
  * Monitoraggio proattivo della coerenza degli indici.
  * SLA di intervento entro 4–8 ore lavorative.

---

## 3. Matrice Tecnica delle Funzionalità per Tier

| Funzionalità | Small | Medium | Enterprise | Implementazione nel Repository |
| :--- | :---: | :---: | :---: | :--- |
| **Utenti Concorrenti** | Fino a 15 | Fino a 50 | Illimitati | Architettura stateless FastAPI |
| **Architettura Database** | SQLite (WAL) | SQLite o Postgres | PostgreSQL HA | `core/database_backend.py` |
| **Worker Concorrenti** | Integrato | Integrato | Dedicato (`SKIP LOCKED`) | `core/distributed_worker.py` |
| **Sicurezza Storage** | Locale | AES-256-GCM | AES-256-GCM / S3 MinIO | `core/storage_provider.py` |
| **Controllo Accessi** | Utenti Locali | RBAC Granulare | SSO OIDC + SCIM 2.0 | `api/auth.py`, `api/scim.py` |
| **Audit Trail** | Locale | Hash Chain SHA-256 | Syslog RFC 5424 + SIEM | `core/governance.py` |
| **Connettori** | Cartella LAN | LAN, S3, Web | Tutti (Graph, Confluence, ecc.) | `core/connectors/` |
| **Orchestrazione** | Script / Docker | Docker Compose | Kubernetes Helm Charts | `deploy/helm/` |
| **Streaming Risposte (SSE)** | ✅ Incluso | ✅ Incluso | ✅ Incluso | `api/libraries.py` (`/ask/stream`) |

---

## 4. Value Proposition per Settore di Mercato

### A. Studi Legali & Notarili
* **Problema**: Ricerca lenta tra migliaia di contratti, atti, sentenze e memorie difensive.
* **Proposta Ermes**: Citazione esatta dell'articolo e della clausola con visualizzazione del testo originale. Riservatezza assoluta senza connessione a server terzi.

### B. Manifattura & Aziende Certificate ISO 9001 / 14001
* **Problema**: Procedure complesse, schede tecniche di macchinari, gestione lotti e non conformità sparse in centinaia di raccoglitori o file PDF/Excel.
* **Proposta Ermes**: Parser strutturato per tabelle XLSX/HTML e OCR per schemi cartacei scansionati. I tecnici trovano i parametri operativi in 3 secondi.

### C. Commercialisti & Consulenti del Lavoro
* **Problema**: Continuo aggiornamento di circolari ministeriali, CCNL, note operative e regolamenti sulle spese.
* **Proposta Ermes**: Ricerca semantica e lessicale con date e versioning. Risposte immediate ai clienti con riferimento alla circolare esatta.

### D. Sanità, Cliniche & Ospedali
* **Problema**: Rigidi vincoli deontologici e legali sui dati sanitari (GDPR Art. 9).
* **Proposta Ermes**: Installazione su rete isolata (*air-gapped*), crittografia end-to-end e anonimizzazione PII automatica.

---

## 5. Battlecard: Ermes vs Soluzioni Concorrenti

| Criterio | ChatGPT Enterprise / Cloud API | Microsoft Copilot 365 | **Ermes Knowledge** |
| :--- | :--- | :--- | :--- |
| **Residenza del Dato** | Cloud proprietario USA | Cloud Microsoft Azure | **100% On-Premise o Tuo Cloud Privato** |
| **Rischio Allucinazioni** | Elevato (modello generativo) | Medio/Elevato | **Zero (Evidence-First + Astensione 100%)** |
| **Costo a Regime** | Per-utente + consumo token | ~30€/utente/mese + licenza base | **Costo fisso licenza (ROI immediato)** |
| **Tracciabilità Audit** | Log aggregati del fornitore | Log Microsoft Purview | **Catena crittografica immutabile SHA-256** |
| **Conformità Air-Gap** | Impossibile | Impossibile | **Supportata nativamente (Offline)** |
