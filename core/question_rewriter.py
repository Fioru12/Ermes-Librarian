"""Riscrittura della domanda di raffinamento in forma autonoma.

Ogni domanda a Ermes era isolata: `_answer_question` riceveva la domanda e
basta, e "E l'anno scorso?" non poteva funzionare. Questo modulo aggiunge la
memoria conversazionale nell'unico modo che non rompe la promessa del
prodotto: tocca la DOMANDA, mai l'evidenza.

Il modo sbagliato — mettere la conversazione nel prompt di risposta — farebbe
rispondere il modello dai turni precedenti invece che dai documenti, e
salterebbe l'astensione. Qui invece un modello piccolo riscrive la domanda in
forma autonoma usando gli ultimi scambi, e da li' in poi la pipeline e' quella
di sempre: recupero, verifica, citazioni, astensione lavorano sulla domanda
riscritta esattamente come su una domanda nuova.

La storia la manda il client a ogni richiesta: il server non la conserva.
Niente nuovo archivio di conversazioni da proteggere e da cancellare.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

import config
from core.pii_filter import filter_pii

_logger = logging.getLogger(__name__)

MAX_TURNI = 3
MAX_CARATTERI_DOMANDA = 2000

# Le regole e l'esempio vengono da una prova con il modello vero
# (qwen3.5:4b, corpus dimostrativo in inglese): senza, "And for remote
# work?" dopo una domanda sulle ferie veniva riscritta in ITALIANO — la lingua
# di queste istruzioni, non della conversazione — e FUSA con la domanda
# precedente ("durata del preavviso per le ferie annuali e requisiti per il
# lavoro da remoto"), quindi il recupero lessicale su documenti inglesi non
# trovava niente. Un modello piccolo segue un esempio molto meglio di una
# regola.
_ISTRUZIONE = (
    "Riscrivi l'ULTIMA DOMANDA in modo che sia comprensibile da sola, senza la conversazione, "
    'rendendo espliciti i riferimenti impliciti ("e l\'anno scorso?", "e per loro?") usando '
    "le domande precedenti.\n"
    "Regole:\n"
    "1. Scrivi la domanda riscritta NELLA STESSA LINGUA dell'ultima domanda, non in italiano se "
    "l'ultima domanda e' in un'altra lingua.\n"
    "2. La domanda riscritta chiede SOLO cio' che chiede l'ultima domanda: la conversazione serve "
    "a sciogliere i riferimenti, non va ripetuta ne' unita alla nuova domanda.\n"
    "3. Non aggiungere informazioni che non siano nella conversazione; non rispondere.\n"
    "4. Se l'ultima domanda e' gia' autonoma, ricopiala identica.\n"
    "5. Scrivi SOLO la domanda riscritta, una riga, senza spiegazioni.\n\n"
    "Esempio.\n"
    "DOMANDA PRECEDENTE: How much notice is required for annual leave?\n"
    "ULTIMA DOMANDA: And for remote work?\n"
    "Domanda riscritta: What are the rules for remote work?\n\n"
    "Ora tocca a te.\n"
    "{conversazione}\n"
    "ULTIMA DOMANDA: {domanda}\n\n"
    "Domanda riscritta:"
)

_TIMEOUT_SECONDI = 60.0


@dataclass(frozen=True)
class Riscrittura:
    question: str
    rewritten: bool
    reason: str  # "disabled" | "no_history" | "rewritten" | "unchanged" | "model_unavailable" | "rejected"


def _modello() -> str:
    """Lo stesso modello del verificatore d'evidenza, con lo stesso ripiego:
    e' un compito piccolo e ripetuto, e vuole un modello piccolo."""
    return getattr(config.cfg, "EVIDENCE_VERIFIER_MODEL", "") or config.cfg.DEFAULT_MODEL_ID


def _conversazione(history: list[dict]) -> str:
    """Solo le DOMANDE precedenti, mai le risposte.

    Due ragioni, e la seconda vale piu' della prima. Qualita': provando con
    il modello vero, la risposta precedente — un passaggio lungo sulle ferie —
    dominava l'attenzione del modello piccolo, che riscriveva "And for remote
    work?" come una domanda sulle ferie. Le domande precedenti bastano a
    sciogliere i riferimenti ("e per loro?" -> di chi si parlava), e sono
    corte.

    Principio: le risposte contengono testo dei documenti. Mandarle al modello
    di riscrittura significherebbe far uscire contenuto documentale verso un
    modello anche in modalita' evidence_only, che promette esattamente il
    contrario. Le domande sono testo dell'utente, e passano comunque dal
    filtro PII.
    """
    righe = []
    for turno in history[-MAX_TURNI:]:
        domanda = str(turno.get("question", "")).strip()[:MAX_CARATTERI_DOMANDA]
        if domanda:
            righe.append(f"DOMANDA PRECEDENTE: {domanda}")
    return "\n".join(righe)


def _chiedi_al_modello(prompt: str) -> str | None:
    try:
        risposta = httpx.post(
            f"{config.cfg.OLLAMA_HOST.rstrip('/')}/api/generate",
            json={
                "model": _modello(),
                "prompt": prompt,
                "stream": False,
                # temperature 0: la stessa conversazione deve produrre sempre
                # la stessa riscrittura, altrimenti la risposta cambia fra un
                # tentativo e l'altro senza che l'utente abbia cambiato niente.
                "options": {"temperature": 0, "num_predict": 200},
                "think": False,
            },
            timeout=_TIMEOUT_SECONDI,
        )
        risposta.raise_for_status()
        return str(risposta.json().get("response", "")).strip()
    except Exception as errore:
        # Ampio per la stessa ragione del verificatore: un guasto della
        # riscrittura degrada alla domanda originale, mai a un errore per
        # l'utente. Il chiamante lo dichiara nella risposta.
        _logger.warning("Riscrittura della domanda non eseguibile: %s", errore)
        return None


def rewrite_with_history(question: str, history: list[dict] | None) -> Riscrittura:
    """La domanda da usare per il recupero, e se e come e' stata riscritta."""
    if not getattr(config.cfg, "CONVERSATION_MEMORY_ENABLED", False):
        return Riscrittura(question, False, "disabled")
    if not history:
        return Riscrittura(question, False, "no_history")

    # Domanda e storia vanno a un modello: passano dal filtro PII come ogni
    # altro percorso che lo fa.
    abilitato = config.cfg.PII_FILTER_ENABLED
    conversazione = filter_pii(_conversazione(history), enabled=abilitato)
    if not conversazione.strip():
        return Riscrittura(question, False, "no_history")
    prompt = _ISTRUZIONE.format(conversazione=conversazione, domanda=filter_pii(question, enabled=abilitato))

    esito = _chiedi_al_modello(prompt)
    if esito is None:
        return Riscrittura(question, False, "model_unavailable")

    riscritta = esito.strip().strip('"').strip()
    # Il modello puo' ignorare le istruzioni: una riscrittura vuota, enorme,
    # o su piu' righe (cioe' una spiegazione o una risposta invece di una
    # domanda) non e' una domanda e non deve arrivare al recupero.
    if not (2 <= len(riscritta) <= MAX_CARATTERI_DOMANDA) or "\n" in riscritta:
        _logger.warning("Riscrittura rifiutata (%d caratteri, %d righe)", len(riscritta), riscritta.count("\n") + 1)
        return Riscrittura(question, False, "rejected")
    if riscritta.casefold() == question.strip().casefold():
        return Riscrittura(question, False, "unchanged")
    return Riscrittura(riscritta, True, "rewritten")
