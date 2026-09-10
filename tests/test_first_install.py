"""La prima installazione non deve arrivare preconfigurata con una password nota.

Trovato il 10 settembre 2026 clonando il repository da GitHub in una cartella
vuota e seguendo il "Quick start" del README alla lettera. Dimostrato su
quell'installazione, prima della correzione:

    POST /api/auth/login  {"username":"admin","password":"CHANGE_ME"}
    -> 200, sessione amministrativa valida

Tre pezzi che si coprono a vicenda, ognuno dei quali da solo lo avrebbe
impedito:

* `.env.example` conteneva `ERMES_ADMIN_PASSWORD=CHANGE_ME` NON commentata, e
  il README dice `Copy-Item .env.example .env` come primo passo. Quel valore
  diventa quindi la password reale dell'amministratore.
* `scripts/provision_local_demo_auth.py --write`, che esiste proprio per
  generare una credenziale casuale, guarda solo se la variabile e' *presente*:
  trovandola stampava `LOCAL_AUTH_ALREADY_CONFIGURED` e non faceva niente.
* `python -m config.validation`, il controllo che dovrebbe fermare una
  configurazione inutilizzabile, rispondeva "nessun problema". Controllava
  l'assenza della password, non il suo valore — e `_PLACEHOLDERS` in quel
  file conteneva gia' "change_me", usato per il segreto dell'audit e mai per
  la password dell'amministratore.

Vale piu' degli altri difetti di questa serie per un motivo semplice: e' cio'
che incontra chiunque provi il progetto per la prima volta, e nessuna delle
tre difese diceva niente.
"""

import re
import sys
from pathlib import Path

import pytest

import config
from config.validation import ConfigurationError, check_configuration, enforce

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from provision_local_demo_auth import provision  # noqa: E402

RADICE = Path(__file__).resolve().parents[1]
ESEMPIO = RADICE / ".env.example"


def _cfg(**overrides):
    base = {"API_KEY": "", "ADMIN_PASSWORD": "StrongPassword!123", "OIDC_ENABLED": False, "HOST": "127.0.0.1"}
    base.update(overrides)
    return config.cfg.replace(**base)


def _assegnazioni_attive() -> dict[str, str]:
    """Le variabili che `.env.example` imposta davvero, cioe' le righe non
    commentate: sono quelle che diventano configurazione al primo passo del
    README."""
    attive: dict[str, str] = {}
    for riga in ESEMPIO.read_text(encoding="utf-8").splitlines():
        pulita = riga.strip()
        if not pulita or pulita.startswith("#"):
            continue
        corrispondenza = re.match(r"^([A-Z0-9_]+)\s*=\s*(.*)$", pulita)
        if corrispondenza:
            attive[corrispondenza.group(1)] = corrispondenza.group(2).strip()
    return attive


# ============================================================
# Il file di esempio non deve configurare una credenziale
# ============================================================


def test_the_example_file_does_not_set_an_admin_password():
    """Copiato in `.env` come dice il README, questo file diventa la
    configurazione reale: qualunque valore qui e' una password vera."""
    attive = _assegnazioni_attive()

    assert "ERMES_ADMIN_PASSWORD" not in attive, (
        f"il primo passo del README installa la password {attive.get('ERMES_ADMIN_PASSWORD')!r}"
    )


def test_the_example_file_does_not_set_an_api_key_either():
    """Stesso ragionamento: l'API key e' l'altra credenziale che apre tutto."""
    attive = _assegnazioni_attive()

    assert "ERMES_API_KEY" not in attive, f"chiave API preimpostata: {attive.get('ERMES_API_KEY')!r}"


def test_the_example_file_assigns_each_variable_at_most_once():
    """Con la stessa variabile assegnata due volte vince l'ultima riga, e chi
    modifica la prima non ottiene niente senza capire perche'."""
    righe = [
        r.strip()
        for r in ESEMPIO.read_text(encoding="utf-8").splitlines()
        if r.strip() and not r.strip().startswith("#")
    ]
    nomi = [re.match(r"^([A-Z0-9_]+)\s*=", r).group(1) for r in righe if re.match(r"^([A-Z0-9_]+)\s*=", r)]

    duplicati = sorted({n for n in nomi if nomi.count(n) > 1})

    assert duplicati == [], f"assegnate due volte in .env.example: {', '.join(duplicati)}"


# ============================================================
# Il controllo di configurazione deve rifiutare un segnaposto
# ============================================================


@pytest.mark.parametrize("segnaposto", ["CHANGE_ME", "change_me", "changeme", "  CHANGE_ME  "])
def test_a_placeholder_admin_password_is_fatal(segnaposto):
    """Controllava l'assenza della password, non il suo valore."""
    problemi = check_configuration(_cfg(ADMIN_PASSWORD=segnaposto))

    interessati = [p for p in problemi if p.setting == "ERMES_ADMIN_PASSWORD"]
    assert interessati, f"{segnaposto!r} accettata come password dell'amministratore"
    assert interessati[0].severity == "fatal"


def test_the_application_refuses_to_start_with_a_placeholder_password():
    """E' la differenza fra un avviso che nessuno legge e un'installazione che
    non parte: `enforce` viene chiamata nel lifespan."""
    with pytest.raises(ConfigurationError, match="ADMIN_PASSWORD"):
        enforce(_cfg(ADMIN_PASSWORD="CHANGE_ME"))


def test_a_placeholder_api_key_is_also_refused():
    with pytest.raises(ConfigurationError):
        enforce(_cfg(ADMIN_PASSWORD="", API_KEY="CHANGE_ME"))


def test_a_short_password_is_flagged_but_does_not_block_startup():
    """Un avviso, non un blocco: una password corta e' una scelta discutibile
    di chi installa, un segnaposto e' una credenziale pubblica."""
    problemi = check_configuration(_cfg(ADMIN_PASSWORD="pippo"))

    interessati = [p for p in problemi if p.setting == "ERMES_ADMIN_PASSWORD"]
    assert interessati and interessati[0].severity == "warning"
    enforce(_cfg(ADMIN_PASSWORD="pippo"))  # non solleva


def test_a_real_password_passes():
    assert [p for p in check_configuration(_cfg()) if p.setting == "ERMES_ADMIN_PASSWORD"] == []


# ============================================================
# Il provisioning deve generare, non dichiarare tutto a posto
# ============================================================


def test_provisioning_generates_credentials_when_only_a_placeholder_is_present(tmp_path, capsys):
    """Guardava solo se la variabile era presente: trovando il segnaposto del
    file di esempio stampava LOCAL_AUTH_ALREADY_CONFIGURED e non faceva
    niente.

    Chiamata in processo su file temporanei. La prima versione di questo test
    lanciava lo script come sottoprocesso, ma i suoi percorsi erano fissati al
    repository: leggeva e avrebbe scritto il `.env` reale, e il test passava
    per il motivo sbagliato. Da qui la separazione fra `provision()` e
    `main()`.
    """
    env = tmp_path / ".env"
    env.write_text("ERMES_ADMIN_USERNAME=admin\nERMES_ADMIN_PASSWORD=CHANGE_ME\n", encoding="utf-8")

    provision(env, tmp_path / "LOCAL_LOGIN.txt")

    stampato = capsys.readouterr().out
    assert "LOCAL_AUTH_ALREADY_CONFIGURED" not in stampato, stampato
    contenuto = env.read_text(encoding="utf-8")
    assert "CHANGE_ME" not in contenuto, "il segnaposto e' rimasto nel file come password apparente"
    generata = re.search(r"^ERMES_ADMIN_PASSWORD=(.+)$", contenuto, re.M)
    assert generata and len(generata.group(1).strip()) >= 20, contenuto


def test_the_generated_password_passes_the_configuration_check(tmp_path, capsys):
    """Le due difese devono concordare: uno script che genera una credenziale
    poi rifiutata dal controllo d'avvio sarebbe peggio di nessuno dei due."""
    env = tmp_path / ".env"
    env.write_text("ERMES_ADMIN_PASSWORD=CHANGE_ME\n", encoding="utf-8")
    provision(env, tmp_path / "LOCAL_LOGIN.txt")
    generata = re.search(r"^ERMES_ADMIN_PASSWORD=(.+)$", env.read_text(encoding="utf-8"), re.M).group(1).strip()

    enforce(_cfg(ADMIN_PASSWORD=generata))  # non solleva

    assert [p for p in check_configuration(_cfg(ADMIN_PASSWORD=generata)) if p.setting == "ERMES_ADMIN_PASSWORD"] == []


def test_provisioning_leaves_a_real_password_alone(tmp_path, capsys):
    """Non deve sovrascrivere la credenziale di un'installazione esistente."""
    env = tmp_path / ".env"
    env.write_text("ERMES_ADMIN_PASSWORD=UnaPasswordVeraCheEsiste!42\n", encoding="utf-8")

    provision(env, tmp_path / "LOCAL_LOGIN.txt")

    assert "LOCAL_AUTH_ALREADY_CONFIGURED" in capsys.readouterr().out
    assert "UnaPasswordVeraCheEsiste!42" in env.read_text(encoding="utf-8")


def test_the_reminder_file_is_not_tracked_by_git():
    """Il promemoria contiene la password in chiaro."""
    import subprocess

    tracciati = subprocess.run(
        ["git", "ls-files"], cwd=RADICE, capture_output=True, text=True, check=False
    ).stdout.split()

    assert "LOCAL_LOGIN.txt" not in tracciati
