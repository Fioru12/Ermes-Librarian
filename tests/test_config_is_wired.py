"""Ogni impostazione dichiarata deve essere letta da qualcuno.

`tests/test_env_example_matches_config.py` copre il primo salto: una variabile
documentata in `.env.example` deve arrivare a un campo di `config/`. Non copre
il secondo, che e' quello dove i difetti si sono nascosti: che quel campo sia
poi letto da qualcosa. Un campo mai letto e' un'impostazione che si puo'
configurare con cura e che non fa niente, e nulla lo segnala — chi la imposta
crede di avere configurato qualcosa.

Difetti trovati da questo controllo:

* `ERMES_BACKUP_DIR` — `core/backup_manager.py` teneva la cartella in una
  costante di modulo con lo stesso nome, `BACKUP_DIR`, calcolata all'import da
  `cfg.BASE_DIR`. Chi la impostava per mandare i backup su un disco separato
  li otteneva accanto ai dati che dovevano proteggere. La collisione di nome e'
  anche il motivo per cui una ricerca testuale del nome non basta: questo
  controllo cerca `cfg.CAMPO`, non il nome da solo.
* `ERMES_BACKUP_RETENTION_COUNT` — conservazione fissa a 10.
* `ERMES_HYDE_ENABLED` — HyDE partiva sempre, e metterla a 0 non evitava la
  chiamata al modello.
* `ERMES_WEBHOOK_RATE_LIMIT_PER_MIN` — le rotte pensate per n8n, Zapier e i
  webhook di chat non avevano nessun limite, e l'impostazione che serviva a
  dargliene uno non aveva effetto.

Quello che resta e' nella lista sotto, ognuno con la sua ragione. La lista e'
un cricchetto: si accorcia, non si allunga.
"""

import dataclasses
import re
from pathlib import Path

import config

RADICE = Path(__file__).resolve().parents[1]

# Cartelle e file che DEFINISCONO la configurazione: cercare li' un campo
# troverebbe solo la sua dichiarazione.
_DEFINIZIONI = {"config_legacy.py"}
_ESCLUSE = {".venv-ermes", "__pycache__", "legacy_winsarp", "node_modules", "tests"}

# Campi dichiarati e non letti, con la ragione. Ogni voce e' un'impostazione
# che oggi non fa niente: la voce dice perche' non e' stata semplicemente
# collegata.
_NON_COLLEGATI_NOTI = {
    # Le manopole del recupero. Collegarle senza misurare cambierebbe in
    # silenzio i numeri pubblicati in docs/RETRIEVAL_EVALUATION.md, che sono
    # stati misurati con i valori attuali fissi nel codice. Vanno collegate
    # una alla volta, ognuna con la sua misura — non prima.
    "TOP_K_INITIAL": "il recupero usa il proprio limite; collegarla richiede rimisurare la valutazione",
    "TOP_K_FINAL": "come TOP_K_INITIAL",
    "SCORE_THRESHOLD_HIGH": "una soglia di punteggio e' stata misurata e respinta (RETRIEVAL_EVALUATION.md)",
    "EMBEDDING_DIMENSION": "la dimensione la decide il modello di embedding, non la configurazione",
    "EMBEDDING_BATCH_SIZE": "l'indicizzazione non lavora a lotti: il campo anticipa un lavoro non fatto",
    # Resti del prodotto precedente.
    "ENABLE_FORMULA_GENERATION": "riguarda il motore WinSarp, dietro ENABLE_LEGACY_WINSARP",
    "DLP_AUDIT_ENABLED": "il filtro PII si attiva con PII_FILTER_ENABLED; questa non ha mai avuto un consumatore",
    # Autenticazione.
    "OIDC_CLIENT_SECRET": "l'app verifica i token via JWKS e non scambia mai un codice: nessun client secret serve",
    # Percorso dei provider.
    "PROVIDERS_CONFIG_PATH": "core/ai/providers/registry.py apre providers.json per percorso fisso",
}


def _campi_dichiarati() -> dict[str, str]:
    campi: dict[str, str] = {}
    for nome_sub in config.Config._SOTTOCONFIG:
        for campo in dataclasses.fields(getattr(config.cfg, nome_sub)):
            campi[campo.name] = nome_sub
    return campi


def _sorgenti() -> str:
    pezzi = []
    for percorso in RADICE.rglob("*.py"):
        if any(parte in _ESCLUSE for parte in percorso.parts):
            continue
        if percorso.name in _DEFINIZIONI:
            continue
        # config/validation.py legge i campi per validarli: e' un consumatore
        # legittimo. Gli altri file di config/ li dichiarano.
        if percorso.parent.name == "config" and percorso.name != "validation.py":
            continue
        pezzi.append(percorso.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(pezzi)


def _letto(campo: str, testo: str) -> bool:
    """Cerca una lettura reale — `cfg.CAMPO`, `config.cfg.CAMPO`,
    `getattr(cfg, "CAMPO")` — non la semplice comparsa del nome."""
    # Deliberatamente NON si accetta la sola comparsa del nome, ne'
    # un'assegnazione `CAMPO = ...`: era esattamente cosi' che BACKUP_DIR
    # sembrava usata, mentre quel nome era una costante di modulo omonima e
    # l'impostazione non arrivava a nessuno.
    return bool(
        re.search(rf"(?:cfg|settings|_cfg)\s*\.\s*{campo}\b", testo)
        or re.search(rf"getattr\(\s*[\w.]*cfg\s*,\s*[\"']{campo}[\"']", testo)
    )


def test_every_declared_setting_is_read_by_something():
    testo = _sorgenti()
    campi = _campi_dichiarati()

    inerti = sorted(c for c in campi if c not in _NON_COLLEGATI_NOTI and not _letto(c, testo))

    assert inerti == [], (
        "Impostazioni dichiarate e mai lette: "
        + ", ".join(f"{c} ({campi[c]})" for c in inerti)
        + ". Chi le configura non ottiene alcun effetto e nulla glielo segnala. "
        "Collegale, oppure aggiungile a _NON_COLLEGATI_NOTI con la ragione."
    )


def test_the_known_list_only_names_settings_that_exist():
    """Un campo rinominato o rimosso deve uscire dalla lista, altrimenti la
    lista smette di descrivere il codice."""
    campi = _campi_dichiarati()

    fantasmi = sorted(c for c in _NON_COLLEGATI_NOTI if c not in campi)

    assert fantasmi == [], f"la lista nomina campi che non esistono piu': {', '.join(fantasmi)}"


def test_the_known_list_does_not_grow_silently():
    """Il cricchetto. Se qualcuno collega una di queste, la voce va togliuta:
    lasciarla dentro nasconderebbe la prossima regressione dello stesso tipo.
    """
    testo = _sorgenti()

    ormai_collegati = sorted(c for c in _NON_COLLEGATI_NOTI if _letto(c, testo))

    assert ormai_collegati == [], (
        "queste impostazioni sono ora lette dal codice: togli la voce da _NON_COLLEGATI_NOTI: "
        + ", ".join(ormai_collegati)
    )


def test_the_settings_this_check_found_are_wired():
    """Le quattro trovate da questo controllo, verificate per nome: se una
    tornasse inerte, il test sopra la segnalerebbe, ma con un messaggio
    generico. Qui il fallimento dice quale funzione la ha perduta."""
    testo = _sorgenti()

    for campo in ("BACKUP_DIR", "BACKUP_RETENTION_COUNT", "HYDE_ENABLED", "WEBHOOK_RATE_LIMIT_PER_MIN"):
        assert _letto(campo, testo), f"{campo} e' tornata inerte"
