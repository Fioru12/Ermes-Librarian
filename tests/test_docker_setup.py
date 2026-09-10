"""Verifica statica di Dockerfile e docker-compose contro il repository.

Perche' esiste
--------------
Lo stack Compose non e' mai stato avviato end-to-end su questa macchina: il
servizio Docker richiede privilegi di amministratore che questa sessione non
ha. Non potendo eseguire `docker compose up`, si verifica staticamente cio'
che si puo': che i file che il Dockerfile copia esistano, che il modulo
lanciato dal CMD esista, e che le variabili d'ambiente impostate dal compose
siano quelle che il codice legge davvero.

Non sostituisce un avvio reale — non dice niente su rete, permessi dei volumi
o disponibilita' dei modelli. Intercetta la classe di errori che fa fallire il
primo avvio prima ancora che il container parta.

Il difetto che ha motivato questo file: il compose impostava `ERMES_MODEL` ed
`ERMES_EMBED_MODEL`, cioe' le due impostazioni piu' importanti, e il codice
legge `ERMES_DEFAULT_MODEL_ID` ed `ERMES_EMBED_MODEL_ID`. Il container girava
sempre con i modelli predefiniti, qualunque cosa scrivesse chi lo installava,
e nulla lo segnalava.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RADICE = Path(__file__).resolve().parents[1]


def _variabili_lette() -> set[str]:
    lette: set[str] = set()
    for percorso in (RADICE / "config").glob("*.py"):
        lette |= set(re.findall(r'"(ERMES_[A-Z0-9_]+)"', percorso.read_text(encoding="utf-8")))
    return lette


def _compose() -> dict:
    return yaml.safe_load((RADICE / "docker-compose.yml").read_text(encoding="utf-8"))


# ============================================================
# Il compose non deve impostare variabili inerti
# ============================================================


def test_compose_only_sets_variables_the_code_reads():
    lette = _variabili_lette()
    inerti = []
    for nome, servizio in (_compose().get("services") or {}).items():
        for voce in servizio.get("environment") or []:
            if not isinstance(voce, str) or not voce.startswith("ERMES_"):
                continue
            chiave = voce.split("=", 1)[0]
            if chiave not in lette:
                inerti.append(f"{nome}: {chiave}")

    assert inerti == [], (
        "docker-compose.yml imposta variabili che config/ non legge: "
        + ", ".join(inerti)
        + ". Nel container non hanno alcun effetto e nulla lo segnala."
    )


@pytest.mark.parametrize(
    "rinominata,attuale",
    [
        ("ERMES_MODEL", "ERMES_DEFAULT_MODEL_ID"),
        ("ERMES_EMBED_MODEL", "ERMES_EMBED_MODEL_ID"),
        ("ERMES_LIBRARY_ASSISTANT_TIMEOUT", "ERMES_ASSISTANT_TIMEOUT_SEC"),
    ],
)
def test_the_old_variable_names_do_not_come_back_in_compose(rinominata, attuale):
    testo = (RADICE / "docker-compose.yml").read_text(encoding="utf-8")

    assert f"- {rinominata}=" not in testo, f"{rinominata} non e' letta da nessuno: usa {attuale}"


# ============================================================
# Il Dockerfile deve copiare file che esistono
# ============================================================


def test_every_copied_path_exists_in_the_repository():
    """Esclude le copie fra stadi (`COPY --from=...`), che vengono da un'immagine
    intermedia e non dal repository."""
    testo = (RADICE / "Dockerfile").read_text(encoding="utf-8")
    mancanti = []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga.startswith("COPY ") or "--from=" in riga:
            continue
        parti = riga[len("COPY ") :].split()
        for sorgente in parti[:-1]:
            if sorgente.startswith("--") or "*" in sorgente:
                continue
            if not (RADICE / sorgente).exists():
                mancanti.append(sorgente)

    assert mancanti == [], f"Dockerfile copia percorsi inesistenti: {', '.join(mancanti)}"


def test_the_launched_module_exists():
    testo = (RADICE / "Dockerfile").read_text(encoding="utf-8")

    trovati = re.findall(r"uvicorn\s+([\w\.]+):(\w+)", testo)

    assert trovati, "il Dockerfile non lancia uvicorn: se e' cambiato, aggiornare questo test"
    for modulo, _attributo in trovati:
        percorso = RADICE / modulo.replace(".", "/")
        assert percorso.is_dir() or percorso.with_suffix(".py").exists(), (
            f"il CMD lancia uvicorn {modulo}, che non esiste nel repository"
        )


# ============================================================
# Ogni percorso montato deve esistere dentro l'immagine
# ============================================================


def test_every_directory_mounted_into_the_app_is_created_in_the_image():
    """Le directory montate sono per la maggior parte in .gitignore — dati e
    segreti — quindi su un clone pulito NON esistono e le crea Docker.

    Un primo tentativo di test verificava che esistessero nel repository:
    passava solo perche' sulla macchina di sviluppo le aveva create
    l'applicazione, e su un clone pulito avrebbe segnalato cinque problemi
    inesistenti. Il container gira come root e il Dockerfile crea quelle
    directory nell'immagine, quindi i permessi non sono un problema.

    La proprieta' verificabile dal repository e' un'altra: ogni cartella
    montata nel servizio `app` deve essere fra quelle che il Dockerfile crea.
    Il controllo riguarda solo `app`, perche' e' l'unico servizio costruito da
    quel Dockerfile — applicarlo a caddy o postgres, che usano immagini
    ufficiali, era l'errore della prima versione di questo test.
    """
    dockerfile = (RADICE / "Dockerfile").read_text(encoding="utf-8")
    create = set()
    for riga in re.findall(r"^RUN\s+mkdir\s+-p\s+(.+?)(?:\s*&&|$)", dockerfile, re.M):
        create |= {voce.strip().split("/")[0] for voce in riga.split() if voce.strip()}

    app = (_compose().get("services") or {}).get("app") or {}
    non_create = []
    for volume in app.get("volumes") or []:
        if not isinstance(volume, str) or not volume.startswith("./"):
            continue
        cartella = volume.split(":", 1)[0][2:].split("/")[0]
        if cartella not in create:
            non_create.append(f"./{cartella}")

    assert non_create == [], "il compose monta nel servizio app percorsi che il Dockerfile non crea: " + ", ".join(
        non_create
    )


def test_config_files_mounted_from_the_repository_are_tracked():
    """I servizi che usano immagini ufficiali montano la propria configurazione
    dal repository: se quel file non e' versionato, su un clone pulito Docker
    crea una DIRECTORY vuota al suo posto e il servizio parte senza
    configurazione. E' il caso di scripts/Caddyfile per il reverse proxy.
    """
    import subprocess

    tracciati = set(
        subprocess.run(["git", "ls-files"], cwd=RADICE, capture_output=True, text=True, check=False).stdout.split()
    )

    mancanti = []
    for nome, servizio in (_compose().get("services") or {}).items():
        if nome == "app":
            continue
        for volume in servizio.get("volumes") or []:
            if not isinstance(volume, str) or not volume.startswith("./"):
                continue
            sorgente = volume.split(":", 1)[0][2:]
            if sorgente not in tracciati:
                mancanti.append(f"{nome}: ./{sorgente}")

    assert mancanti == [], (
        "il compose monta file di configurazione non versionati: "
        + ", ".join(mancanti)
        + ". Su un clone pulito Docker creerebbe una directory vuota al loro posto."
    )
