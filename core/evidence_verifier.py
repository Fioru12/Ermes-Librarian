"""Verifica che un passaggio recuperato risponda davvero alla domanda.

Il problema che risolve
-----------------------
La ricerca semantica porta le parafrasi da 0.500 a 0.875 e in cambio azzera
l'astensione: ogni domanda fuori tema trova un passaggio "abbastanza simile"
da superare la soglia. La domanda ovvia — esiste una soglia intermedia che
tenga entrambe? — ha risposta no, e non per tentativi: i punteggi delle due
popolazioni si sovrappongono.

Sono stati misurati quattro segnali candidati sul golden set, cercando quello
che separasse le parafrasi corrette dai falsi positivi dell'astensione:

    coseno      parafrasi [0.587 .. 0.761]   astensione [0.635 .. 0.656]
    margine 1-2 parafrasi [0.010 .. 0.130]   astensione [0.024 .. 0.030]
    rapporto    parafrasi [1.016 .. 1.206]   astensione [1.038 .. 1.050]
    z-score     parafrasi [1.154 .. 1.708]   astensione [1.108 .. 1.711]

Nessuno separa. Un quinto, la copertura lessicale della domanda nel passaggio,
sembrava promettente — nessun falso positivo ne aveva — ma le quattro parafrasi
che superava erano esattamente le quattro che la ricerca per parole gia'
risolveva: zero guadagno. Sulle altre quattro, quelle dove il semantico
servirebbe davvero, il segnale e' identico a quello delle domande fuori tema,
perche' "nessun aggancio lessicale" e' proprio cio' che le accomuna.

Il segnale che mancava non e' un punteggio: e' una domanda. Chiedere a un
modello se il passaggio contenga la risposta separa le due popolazioni dove
nessuna statistica riusciva.

Misurato sul golden set (27 query, verificatore qwen3.5:4b locale):

    | Configurazione            | recall@3 | dirette | parafrasi | astensione |
    | Lessicale (default)       |    0.852 |   1.000 |     0.500 |      1.000 |
    | Ibrida senza verifica     |    0.852 |   1.000 |     0.875 |      0.000 |
    | Ibrida + questa verifica  |    0.889 |   1.000 |     0.625 |      1.000 |

Perche' non e' attiva di default
---------------------------------
Costa una chiamata al modello per ogni passaggio candidato, quindi fino a tre
per domanda, e richiede un modello raggiungibile — che nella modalita'
predefinita `evidence_only` non c'e' per scelta. Si attiva con
`ERMES_EVIDENCE_VERIFIER=1` insieme alla ricerca semantica.

Cosa succede se il modello non risponde
----------------------------------------
La verifica viene saltata e i passaggi passano com'erano, cioe' il sistema
torna a comportarsi come la configurazione documentata senza verifica. Non e'
un fail-open su una garanzia: e' il ritorno al comportamento di base. Ma non
avviene in silenzio — viene registrato, e la risposta porta
`evidence_verified: false`, cosi' chi legge sa che quel controllo non e'
passato.
"""

import concurrent.futures
import logging
import threading

import httpx

import config

_logger = logging.getLogger(__name__)

_ISTRUZIONE = (
    "Sei un verificatore di evidenza. Ti do una DOMANDA e un PASSAGGIO di un documento aziendale.\n"
    "Rispondi UNA SOLA PAROLA: SI se il passaggio contiene l'informazione che risponde alla domanda, "
    "NO se parla di un argomento diverso o non contiene la risposta.\n"
    "Nel dubbio rispondi NO.\n\nDOMANDA: {domanda}\n\nPASSAGGIO: {passaggio}\n\nRisposta:"
)

_TIMEOUT_SECONDI = 60.0

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.Client(timeout=_TIMEOUT_SECONDI)
    return _client


def _modello() -> str:
    """Modello del verificatore, con ripiego su quello generale.

    Il ripiego era `cfg.MODEL`, che non esiste: la configurazione espone
    DEFAULT_MODEL_ID. Abilitare il verificatore senza indicare un modello
    faceva quindi fallire ogni domanda con AttributeError. Non l'hanno visto i
    test perche' simulavano `_passaggio_risponde`, cioe' proprio la funzione
    che chiama questa — l'errore che questo progetto ha gia' fatto altrove.
    """
    return getattr(config.cfg, "EVIDENCE_VERIFIER_MODEL", "") or config.cfg.DEFAULT_MODEL_ID


def _passaggio_risponde(domanda: str, passaggio: str) -> bool | None:
    """True/False secondo il modello, None se la verifica non e' eseguibile."""
    try:
        risposta = httpx.post(
            f"{config.cfg.OLLAMA_HOST.rstrip('/')}/api/generate",
            json={
                "model": _modello(),
                "prompt": _ISTRUZIONE.format(domanda=domanda, passaggio=passaggio),
                "stream": False,
                # temperature 0: la stessa coppia domanda/passaggio deve dare
                # sempre lo stesso verdetto, altrimenti l'astensione diventa
                # casuale fra una richiesta e l'altra.
                "options": {"temperature": 0, "num_predict": 8},
                "think": False,
            },
            timeout=_TIMEOUT_SECONDI,
        )
        risposta.raise_for_status()
        testo = str(risposta.json().get("response", "")).strip().upper()
    except Exception as errore:
        # Volutamente ampio. La verifica e' un miglioramento facoltativo: un
        # suo guasto deve degradare al comportamento senza verifica, mai far
        # fallire la domanda dell'utente. L'elenco ristretto di eccezioni
        # lasciava passare, fra le altre, l'AttributeError qui sopra.
        _logger.warning("Verifica dell'evidenza non eseguibile: %s", errore)
        return None
    return testo.startswith(("SI", "SÌ", "YES"))


def verify_citations(question: str, citations: list[dict]) -> tuple[list[dict], bool]:
    """Restituisce (citazioni superstiti, verifica_eseguita).

    Se la verifica non e' attiva o non e' eseguibile, restituisce le citazioni
    invariate e `False`: il chiamante deve dichiararlo nella risposta invece di
    lasciar credere che il controllo sia passato.
    """
    from core.injection_guard import inspect_passage
    from core.metrics import record_verifier_outcome
    from core.pii_filter import filter_pii

    if not getattr(config.cfg, "EVIDENCE_VERIFIER_ENABLED", False):
        record_verifier_outcome("disabled")
        return citations, False
    if not citations:
        # Niente da verificare non e' un degrado: non si conta.
        return citations, False

    clean_question = filter_pii(question, enabled=config.cfg.PII_FILTER_ENABLED)
    superstiti: list[dict] = []
    to_verify: list[tuple[int, dict, str]] = []  # (original_idx, citation, clean_text)
    almeno_una_verificata = False

    for idx, citazione in enumerate(citations):
        testo = str(citazione.get("excerpt") or citazione.get("text") or "").strip()
        if not testo:
            # Senza testo non c'e' niente da verificare: si conserva la
            # citazione invece di scartarla per un dato mancante.
            superstiti.append(citazione)
            continue
        # Un passaggio con istruzioni rivolte al modello non va al modello, e
        # non conta come evidenza verificata: chi verifica non deve leggere
        # cio' che cerca di dirgli cosa rispondere.
        if inspect_passage(testo).sospetto:
            almeno_una_verificata = True
            continue
        clean_text = filter_pii(testo, enabled=config.cfg.PII_FILTER_ENABLED)
        to_verify.append((idx, citazione, clean_text))

    if to_verify:
        almeno_una_verificata = True
        # Esegui in parallelo se ci sono più passaggi candidati
        if len(to_verify) == 1:
            _, cit, c_text = to_verify[0]
            esito = _passaggio_risponde(clean_question, c_text)
            if esito is None:
                _logger.warning("Verifica dell'evidenza interrotta: le citazioni non sono state controllate")
                record_verifier_outcome("unavailable")
                return citations, False
            if esito:
                superstiti.append(cit)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(to_verify))) as executor:
                verdicts = list(executor.map(lambda item: _passaggio_risponde(clean_question, item[2]), to_verify))

            for (orig_idx, cit, _), esito in zip(to_verify, verdicts):
                if esito is None:
                    _logger.warning("Verifica dell'evidenza interrotta: le citazioni non sono state controllate")
                    record_verifier_outcome("unavailable")
                    return citations, False
                if esito:
                    superstiti.append(cit)

    if not almeno_una_verificata:
        return citations, False

    # Ordina i superstiti per preservare l'ordine originale di pertinenza
    orig_order = {id(c): i for i, c in enumerate(citations)}
    superstiti.sort(key=lambda c: orig_order.get(id(c), 999))

    record_verifier_outcome("verified")
    return superstiti, True
