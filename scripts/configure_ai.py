"""Scelta del modello di intelligenza artificiale, al momento dell'installazione.

Tre possibilita', da scegliere esplicitamente (nessuna e' preselezionata):

- ``estratti``: nessun modello. Ermes mostra i passaggi pertinenti con la
  fonte e non genera testo. Funziona su qualunque computer e nessun dato
  esce dalla macchina.
- ``locale``: un modello che gira sul computer con Ollama. Nessun dato esce,
  ma servono memoria e tempo di calcolo; lo script controlla la RAM e
  scarica il modello.
- ``cloud``: un modello raggiungibile via API pubblica (OpenRouter). Va bene
  anche su un computer modesto, ma i passaggi dei documenti pertinenti a ogni
  domanda vengono inviati al provider: serve il consenso esplicito.

La verifica dell'evidenza (il controllo che fa dire "non lo so" invece di
citare un passaggio sbagliato) resta una scelta separata e spenta di
default: su domande realistiche non e' ancora misurata
(docs/RETRIEVAL_EVALUATION.md, suite PMI).

Lo script scrive solo le variabili che riguardano la scelta, lasciando
intatto il resto del file .env. Usa solo la libreria standard: il setup lo
chiama anche prima che l'ambiente virtuale esista.

Uso
---
    python scripts/configure_ai.py                       # domande a console
    python scripts/configure_ai.py --modo estratti
    python scripts/configure_ai.py --modo locale --verifica
    set ERMES_SETUP_OPENROUTER_KEY=sk-or-...             # la chiave non va sulla riga di comando
    python scripts/configure_ai.py --modo cloud --modello <id> --consenso-cloud

L'ultima riga stampata e' un JSON con l'esito, letto dal setup grafico.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

# La chiave arriva da qui e non da un argomento: la riga di comando di un
# processo e' visibile agli altri utenti della macchina.
KEY_ENV_VAR = "ERMES_SETUP_OPENROUTER_KEY"

# Stessi modelli che il progetto documenta e ha misurato (.env.example,
# docs/RETRIEVAL_EVALUATION.md). Il piu' piccolo e' anche quello consigliato
# per la verifica: e' una domanda si/no ripetuta per ogni passaggio.
MODELLO_LOCALE_GRANDE = "qwen3.5:9b"
MODELLO_LOCALE_PICCOLO = "qwen3.5:4b"
MODELLO_VERIFICA_LOCALE = "qwen3.5:4b"

RAM_MINIMA_GB = 8
# 15 e non 16: un computer venduto con 16 GB ne riporta circa 15,7 (memoria
# riservata al sistema e alla grafica integrata).
RAM_PER_MODELLO_GRANDE_GB = 15

MODI = ("estratti", "locale", "cloud")


class SceltaNonValidaError(ValueError):
    """La scelta non si puo' applicare cosi' com'e' (manca consenso, chiave...)."""


def ram_totale_gb() -> float | None:
    """Memoria fisica in GB, None se non si riesce a leggerla."""
    try:
        if sys.platform == "win32":

            class _Stato(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stato = _Stato()
            stato.dwLength = ctypes.sizeof(_Stato)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato)):  # type: ignore[attr-defined]
                return round(stato.ullTotalPhys / 1024**3, 1)
            return None
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            match = re.search(r"MemTotal:\s+(\d+) kB", meminfo.read_text())
            if match:
                return round(int(match.group(1)) / 1024**2, 1)
        pagine, dimensione = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        return round(pagine * dimensione / 1024**3, 1)
    except (OSError, ValueError, AttributeError):
        return None


def ollama_installato() -> bool:
    return shutil.which("ollama") is not None


def piano(
    modo: str,
    *,
    verifica: bool = False,
    consenso_cloud: bool = False,
    chiave: str = "",
    modello: str = "",
    ram_gb: float | None = None,
    ollama: bool = False,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Variabili da scrivere, avvisi per l'utente, modelli Ollama da scaricare.

    Pura: non tocca disco ne' rete, cosi' le regole si possono provare.
    """
    if modo not in MODI:
        raise SceltaNonValidaError(f"modalita' sconosciuta: {modo!r} (attese: {', '.join(MODI)})")
    avvisi: list[str] = []
    da_scaricare: list[str] = []
    # Sempre scritte, in ogni modo: passare da cloud a locale deve spegnere il
    # consenso, non lasciarlo acceso da una scelta precedente.
    variabili = {
        "ERMES_LIBRARY_ASSISTANT_MODE": "evidence_only",
        "ERMES_LIBRARY_CLOUD_CONSENT": "0",
        "ERMES_EVIDENCE_VERIFIER": "0",
    }

    if modo == "estratti":
        if verifica:
            avvisi.append(
                "La verifica dell'evidenza richiede un modello: non e' stata attivata. "
                "Sceglila con la modalita' locale o cloud."
            )
        return variabili, avvisi, da_scaricare

    if modo == "locale":
        modello_scelto = modello or (
            MODELLO_LOCALE_PICCOLO
            if ram_gb is not None and ram_gb < RAM_PER_MODELLO_GRANDE_GB
            else MODELLO_LOCALE_GRANDE
        )
        variabili["ERMES_LIBRARY_ASSISTANT_MODE"] = "local_ollama"
        variabili["ERMES_DEFAULT_MODEL_ID"] = modello_scelto
        da_scaricare.append(modello_scelto)
        if ram_gb is None:
            avvisi.append(
                "Memoria del computer non rilevata: se le risposte sono molto lente, scegli la modalita' cloud."
            )
        elif ram_gb < RAM_MINIMA_GB:
            avvisi.append(
                f"Il computer ha {ram_gb:g} GB di RAM: un modello locale sara' molto lento o non partira'. "
                "Valuta la modalita' cloud o 'solo estratti'."
            )
        elif ram_gb < RAM_PER_MODELLO_GRANDE_GB and not modello:
            avvisi.append(f"{ram_gb:g} GB di RAM: scelto il modello piu' leggero ({MODELLO_LOCALE_PICCOLO}).")
        if not ollama:
            avvisi.append(
                "Ollama non e' installato: scaricalo da https://ollama.com e poi rilancia questo passaggio "
                "(scripts/configure_ai.py) per scaricare il modello. Fino ad allora Ermes mostra solo gli estratti."
            )
        if verifica:
            variabili["ERMES_EVIDENCE_VERIFIER"] = "1"
            variabili["ERMES_EVIDENCE_VERIFIER_MODEL"] = MODELLO_VERIFICA_LOCALE
            if MODELLO_VERIFICA_LOCALE not in da_scaricare:
                da_scaricare.append(MODELLO_VERIFICA_LOCALE)
        return variabili, avvisi, da_scaricare

    # cloud
    if not consenso_cloud:
        raise SceltaNonValidaError(
            "La modalita' cloud invia al provider i passaggi dei documenti pertinenti a ogni domanda: "
            "serve il consenso esplicito (--consenso-cloud)."
        )
    if not chiave.strip():
        raise SceltaNonValidaError(f"Manca la chiave OpenRouter (variabile {KEY_ENV_VAR}).")
    if not modello.strip():
        raise SceltaNonValidaError("Indica il modello OpenRouter (--modello), copiando l'ID dalla pagina del modello.")
    if re.search(r"\s", chiave.strip()) or re.search(r"\s", modello.strip()):
        raise SceltaNonValidaError("Chiave e modello non possono contenere spazi.")
    variabili.update(
        {
            "ERMES_LIBRARY_ASSISTANT_MODE": "approved_openrouter",
            "ERMES_LIBRARY_CLOUD_CONSENT": "1",
            # I nomi documentati in .env.example e passati da docker-compose.yml.
            "OPENROUTER_API_KEY": chiave.strip(),
            "OPENROUTER_MODEL": modello.strip(),
        }
    )
    if verifica:
        # Nessun modello di verifica a parte: con una biblioteca cloud verifica
        # lo stesso provider che genera (core/evidence_verifier.py).
        variabili["ERMES_EVIDENCE_VERIFIER"] = "1"
    return variabili, avvisi, da_scaricare


# Varianti con prefisso che config/integrations.py preferisce ai nomi scritti
# da questo script: una vecchia chiave rimasta qui vincerebbe sulla nuova.
OMBRE = {"OPENROUTER_API_KEY": "ERMES_OPENROUTER_API_KEY", "OPENROUTER_MODEL": "ERMES_OPENROUTER_MODEL"}


def aggiorna_env(percorso: Path, variabili: dict[str, str], modello: Path | None = None) -> None:
    """Imposta le variabili nel .env senza toccare le altre righe.

    Una variabile gia' presente (anche commentata, come in .env.example) viene
    sostituita al suo posto, cosi' resta vicina alla sua spiegazione; le altre
    si aggiungono in fondo. Se il .env non c'e', si parte dall'esempio. Le
    varianti in OMBRE ancora attive vengono commentate.
    """
    ombre = {OMBRE[nome] for nome in variabili if nome in OMBRE}
    if percorso.exists():
        righe = percorso.read_text(encoding="utf-8").splitlines()
    elif modello is not None and modello.exists():
        righe = modello.read_text(encoding="utf-8").splitlines()
    else:
        righe = []
    restanti = dict(variabili)
    for indice, riga in enumerate(righe):
        match = re.match(r"^\s*#?\s*([A-Z0-9_]+)\s*=", riga)
        if match and match.group(1) in restanti:
            nome = match.group(1)
            # Solo la prima occorrenza: una seconda riga attiva con lo stesso
            # nome ridefinirebbe il valore, quindi le successive si commentano.
            righe[indice] = f"{nome}={restanti.pop(nome)}"
        elif match and (match.group(1) in variabili or match.group(1) in ombre) and not riga.lstrip().startswith("#"):
            righe[indice] = f"# {riga.strip()}  (sostituita da configure_ai.py)"
    if restanti:
        righe += ["", "# Scelta del modello (scripts/configure_ai.py)"]
        righe += [f"{nome}={valore}" for nome, valore in restanti.items()]
    percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")


def scarica_modelli(modelli: list[str]) -> list[str]:
    """`ollama pull` per ogni modello; restituisce quelli non scaricati."""
    falliti = []
    for nome in modelli:
        print(f"Scarico il modello {nome} con Ollama (puo' richiedere qualche minuto)...", flush=True)
        try:
            esito = subprocess.run(["ollama", "pull", nome], check=False)
        except OSError:
            falliti.append(nome)
            continue
        if esito.returncode != 0:
            falliti.append(nome)
    return falliti


def _chiedi(domanda: str, ammesse: tuple[str, ...]) -> str:
    while True:
        risposta = input(domanda).strip().lower()
        if risposta in ammesse:
            return risposta
        print(f"Rispondi con: {' / '.join(ammesse)}")


def _interattivo() -> argparse.Namespace:
    print(__doc__.split("Lo script scrive")[0])
    scelta = _chiedi("Quale modalita'? [1] solo estratti  [2] modello locale  [3] API cloud: ", ("1", "2", "3"))
    modo = {"1": "estratti", "2": "locale", "3": "cloud"}[scelta]
    args = argparse.Namespace(modo=modo, verifica=False, consenso_cloud=False, modello="", senza_download=False)
    if modo == "cloud":
        print("\nI passaggi pertinenti di ogni domanda verranno inviati a OpenRouter.")
        args.consenso_cloud = _chiedi("Acconsenti? [s/n]: ", ("s", "n")) == "s"
        if args.consenso_cloud and not os.environ.get(KEY_ENV_VAR):
            import getpass

            os.environ[KEY_ENV_VAR] = getpass.getpass("Chiave OpenRouter (non viene mostrata): ")
        if args.consenso_cloud:
            args.modello = input("ID del modello OpenRouter: ").strip()
    if modo != "estratti":
        print(
            "\nVerifica dell'evidenza: un secondo controllo che scarta i passaggi che non rispondono "
            "davvero.\nCosta una chiamata al modello per passaggio e su domande realistiche non e' ancora misurata."
        )
        args.verifica = _chiedi("Attivarla? [s/n]: ", ("s", "n")) == "s"
    return args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sceglie il modello di intelligenza artificiale di Ermes.")
    parser.add_argument("--modo", choices=MODI, help="Senza, le domande vengono fatte a console.")
    parser.add_argument("--verifica", action="store_true", help="Attiva la verifica dell'evidenza.")
    parser.add_argument("--consenso-cloud", action="store_true", help="Consenso a inviare passaggi al provider cloud.")
    parser.add_argument("--modello", default="", help="Modello Ollama (locale) o ID OpenRouter (cloud).")
    parser.add_argument("--senza-download", action="store_true", help="Non scaricare i modelli locali (es. Docker).")
    parser.add_argument("--env", type=Path, default=ENV_FILE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.modo is None:
        interattivi = _interattivo()
        for nome in ("modo", "verifica", "consenso_cloud", "modello"):
            setattr(args, nome, getattr(interattivi, nome))

    ollama = ollama_installato()
    try:
        variabili, avvisi, da_scaricare = piano(
            args.modo,
            verifica=args.verifica,
            consenso_cloud=args.consenso_cloud,
            chiave=os.environ.get(KEY_ENV_VAR, ""),
            modello=args.modello,
            ram_gb=ram_totale_gb(),
            ollama=ollama,
        )
    except SceltaNonValidaError as errore:
        print(f"Configurazione non applicata: {errore}", file=sys.stderr)
        print(json.dumps({"ok": False, "errore": str(errore)}, ensure_ascii=False))
        return 2

    aggiorna_env(args.env, variabili, ENV_EXAMPLE)
    non_scaricati: list[str] = []
    if da_scaricare and ollama and not args.senza_download:
        non_scaricati = scarica_modelli(da_scaricare)
        if non_scaricati:
            avvisi.append(
                f"Download non riuscito per: {', '.join(non_scaricati)}. "
                f"Riprova con: ollama pull {' && ollama pull '.join(non_scaricati)}"
            )
    for avviso in avvisi:
        print(f"AVVISO: {avviso}")
    print(f"Modalita' '{args.modo}' salvata in {args.env.name}. Riavvia Ermes per applicarla.")
    print("Vale per le biblioteche nuove; quelle esistenti si cambiano dalla pagina della biblioteca.")
    esito = {
        "ok": True,
        "modo": args.modo,
        "verifica": variabili["ERMES_EVIDENCE_VERIFIER"] == "1",
        "avvisi": avvisi,
        "modelli_da_scaricare": [m for m in da_scaricare if args.senza_download or not ollama or m in non_scaricati],
    }
    print(json.dumps(esito, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
