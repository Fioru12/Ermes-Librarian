# Prova con uno screen reader (NVDA)

Cosa e' gia' verificato in automatico, e cosa no.

**Automatico (CI, a ogni modifica):** `e2e/accessibility.spec.ts` esegue axe (WCAG 2.1 A/AA) su tutte le schede in tema chiaro e scuro, e controlla che ogni schermata abbia un solo titolo di primo livello e nessun campo senza nome. Il test e2e `keyboard.spec.ts` copre tastiera e focus delle finestre.

**Non verificabile da una macchina:** come suona davvero con uno screen reader. Una persona deve ascoltare l'app. Servono 20 minuti.

## Preparazione

1. Installa NVDA (gratuito, [nvaccess.org](https://www.nvaccess.org)) e avvialo.
2. Avvia Ermes (`AVVIA_ERMES`) e accedi. Lascia il mouse: usa solo la tastiera.
3. Tasti utili di NVDA: `Ctrl` ferma la lettura, `H` salta al titolo successivo, `D` alla regione successiva, `F` al campo modulo successivo, `Insert+F7` elenca titoli, regioni e link.

## Cosa provare

| Schermata | Cosa deve succedere |
|---|---|
| Accesso | Dire "Nome utente" e "Password" sui due campi; errore di accesso letto da solo. |
| Tutte | Un solo titolo di primo livello, uguale al nome della scheda (premi `1`). La barra laterale e' una "navigazione". Il primo `Tab` offre "Vai al contenuto". |
| Assistente | Il campo si chiama "La tua domanda sui documenti". Dopo l'invio la risposta viene letta, e ogni fonte e' un pulsante che dice "Fonte 1: nome del file". |
| Finestra di una fonte | Il focus entra nella finestra, `Esc` la chiude e il focus torna al pulsante di prima. |
| Biblioteche e documenti | Ogni campo ha un nome sensato ("Nome della nuova biblioteca", "Cerca nei documenti"). Lo stato di un documento ("Pronto") e' letto, non solo colorato. |
| Collegamenti esterni, Impostazioni, Accessi | Ogni campo dice a cosa serve prima di scrivere. Gli interruttori dicono se sono attivi. |
| Stato del sistema | "Cosa richiede attenzione" e' letto prima del resto; i colori non sono l'unica informazione. |

## Cosa annotare

Per ogni problema: schermata, cosa ha detto NVDA, cosa ti aspettavi. Aprilo come issue sul repository: va corretto e, se si puo', coperto da un test automatico.

Quando la prova e' stata fatta, annota data, versione di NVDA e esito in fondo a questo file.

## Esiti

_Nessuna prova ancora registrata._
