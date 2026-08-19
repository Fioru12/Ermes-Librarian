# Ermes Knowledge — demo in 5 minuti

Questa demo mostra il valore del prodotto senza usare documenti di clienti o
materiale del precedente progetto WinSarp. Il corpus `Northstar Works` e' interamente fittizio.

## Preparazione

1. Avvia Ermes e accedi come amministratore.
2. Apri **Biblioteche e documenti** e seleziona `Northstar Works Demo`.
3. Mantieni la policy **Solo evidenze locali**. In questo stato nessun contenuto viene inviato a un LLM.

Se la biblioteca non esiste, esegui dalla radice del progetto:

```powershell
.\.venv-ermes\Scripts\python.exe scripts\run_demo_validation.py
```

Il comando carica tre policy fittizie, controlla le risposte e non invia dati fuori da `localhost`.

## Sequenza consigliata

1. Mostra i tre file nella biblioteca: handbook del personale, nota spese e policy accessi IT.
2. Cerca `annual leave` e apri il risultato: il passaggio e il locator fanno capire dove l'informazione e' stata trovata.
3. Dall'assistente chiedi: **“How much notice is required for annual leave?”**.
   La risposta deve citare `employee-handbook.md`.
4. Chiedi: **“When is an expense report due?”**.
   La risposta deve citare `expense-policy.md`.
5. Chiedi: **“What is the warranty period for customer hardware?”**.
   Ermes deve dichiarare di non avere evidenza, senza inventare una risposta.
6. Passa alla seconda biblioteca `Meridian Precision Works Demo` ([examples/demo-corpus-quality](../examples/demo-corpus-quality)) e chiedi **“What is the annual learning budget per employee?”** — una domanda a cui risponde solo `employee-handbook.md`, nell'*altra* biblioteca. Ermes deve astenersi anche qui: è la prova dal vivo che la ricerca non attraversa mai il confine tra biblioteche, non solo un'affermazione nella documentazione.

## Cosa dimostra

- Biblioteca isolata: la ricerca usa solo i documenti della biblioteca selezionata — dimostrato al passo 6 con una domanda a cui un'altra biblioteca potrebbe rispondere, ma questa correttamente si astiene.
- Tracciabilita: una risposta e' accompagnata da file, versione, locator ed estratto.
- Affidabilita: senza evidenza, il prodotto si astiene.
- Controllo dati: la modalita' predefinita non invia contenuto a modelli esterni.

## Nota su come scegliere domande di isolamento/astensione

Con un corpus piccolo e ricerca a parole chiave, una domanda "fuori biblioteca" può accidentalmente condividere una parola comune con un chunk della biblioteca sbagliata (es. "report", "work", "approve" ricorrono naturalmente in testi aziendali generici) e ottenere una risposta falsamente positiva — non è una fuga tra biblioteche (la query resta vincolata al `library_id` corretto lato SQL), è un falso positivo del solo keyword matching su una parola generica. La domanda di isolamento in `scripts/run_demo_validation.py` è stata scelta empiricamente (verificata contro il server reale, non assunta) per non condividere alcuna parola con il corpus Meridian — usa lo stesso approccio se aggiungi altre domande di questo tipo.

## Dimostrazione opzionale con AI

Solo dopo la demo evidence-only, un amministratore puo' configurare OpenRouter o un provider compatibile nella sezione **Impostazioni**. Il proprietario della biblioteca seleziona quindi `OpenRouter (cloud)` oppure `Provider approvato (cloud)` e conferma l'avviso di trasferimento dati.

Per abilitarlo serve anche `ERMES_LIBRARY_CLOUD_CONSENT=1` nel file `.env` locale. Non esiste fallback automatico: Ermes invia soltanto gli estratti autorizzati al provider nominato per quella biblioteca.
