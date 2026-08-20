# scripts/

Script operativi di Ermes Knowledge. Gli script del motore formule storico
stanno sotto `legacy_winsarp/scripts/` e non sono usati dal prodotto.

## Convenzione di naming

I nomi mescolano maiuscole e minuscole di proposito, non per disordine:

- **`MAIUSCOLO.bat` / `MAIUSCOLO.ps1`** — punti d'ingresso pensati per l'utente
  finale, da lanciare con doppio click su Windows.
- **`minuscolo.py` / `minuscolo.ps1`** — strumenti per sviluppatori, da eseguire
  da terminale.

L'unica eccezione è `avvia_ermes.ps1`: è il launcher principale, quindi
sarebbe da maiuscolo per convenzione, ma è già referenziato da README,
documentazione, collegamento sul Desktop e installer, e rinominarlo
introdurrebbe più rischio di quanto valga la coerenza cosmetica.

## Avvio e arresto

| Script | Cosa fa |
|---|---|
| `avvia_ermes.ps1` | **Launcher ufficiale.** Avvia Ollama, backend (8502) e frontend (3000), poi verifica lo stato con un health check reale. |
| `STOP.ps1` | Ferma backend e frontend e verifica che le porte siano davvero libere. Lascia Ollama in esecuzione: è un servizio condiviso. |

## Installazione e verifica

| Script | Cosa fa |
|---|---|
| `SETUP_INSTALL.bat` | Installer per Windows: controlla Python e Ollama, crea `.venv-ermes`, installa le dipendenze, crea il collegamento sul Desktop. |
| `VERIFICA_SISTEMA.bat` | Controlla i prerequisiti (venv, Ollama, dipendenze) e riporta quante mancano. Non dichiara successo se qualcosa fallisce. |
| `CREA_COLLEGAMENTO_DESKTOP.ps1` | Crea il collegamento sul Desktop verso `avvia_ermes.ps1`. |

> L'ambiente virtuale **deve** chiamarsi `.venv-ermes`: è quello che
> `avvia_ermes.ps1` cerca, e senza il quale il launcher esce con errore.
> Un `.venv` semplice può inoltre provenire da un altro profilo Windows.

## Strumenti per sviluppatori

| Script | Cosa fa |
|---|---|
| `smoke_test.py` | Smoke test del sistema. `smoke_test.bat` è solo un wrapper per doppio click. |
| `test_all.bat` | Esegue la suite pytest escludendo i test di integrazione. |
| `run_demo_validation.py` | Valida il flusso demo completo, incluso il controllo di isolamento fra biblioteche. |
| `provision_local_demo_auth.py` | Genera le credenziali di primo avvio in `.env` e `LOCAL_LOGIN.txt` (entrambi non versionati). |
| `setup_openrouter.py` | Configura OpenRouter come provider cloud approvato. |
| `backup.py` | Backup di database, documenti e configurazione. |

## Infrastruttura

| File | Cosa fa |
|---|---|
| `Caddyfile` | Configurazione del reverse proxy con SSL automatico, montata da `docker-compose.yml` sotto il profilo `public`. Sostituisci il dominio prima di usarla. |
