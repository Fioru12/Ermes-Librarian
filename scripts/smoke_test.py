"""Smoke test di un'istanza Ermes gia' avviata.

Controlla, contro il server vero (non un TestClient):

1. /health risponde, e con quale stato (healthy / degraded) e quali avvisi;
2. se ERMES_ADMIN_PASSWORD e' impostata: login, elenco biblioteche, logout.

Codici di uscita: 0 tutto a posto, 1 istanza raggiungibile ma degradata o
login fallito, 2 istanza non raggiungibile.

Prima questo script lanciava `tests/test_winsarp.py` e interrogava `/query`
con il modulo "WinSarp": entrambi resti del progetto precedente, rimossi da
tempo. Lo script stampava "Smoke test completed." e usciva 0 comunque.
"""

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_PORT = int(os.environ.get("ERMES_API_PORT", "8502"))
BASE_URL = os.environ.get("ERMES_SMOKE_URL", f"http://127.0.0.1:{API_PORT}").rstrip("/")


def _solo_http(url):
    """urlopen accetta anche file:// e schemi personalizzati: qui gli URL sono
    costruiti da una porta, quindi un vincolo esplicito non toglie niente e
    chiude la segnalazione bandit B310 invece di silenziarla."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Schema non ammesso: {url!r}")
    return url


_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _richiesta(metodo, percorso, payload=None, timeout=10):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        _solo_http(BASE_URL + percorso),
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=metodo,
    )
    try:
        # nosec B310: lo schema e' verificato da _solo_http sopra.
        with _opener.open(req, timeout=timeout) as resp:  # nosec B310
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


def controlla_health(attesa_secondi=30):
    print(f"Health: {BASE_URL}/health (attesa massima {attesa_secondi}s)")
    inizio = time.time()
    while time.time() - inizio < attesa_secondi:
        codice, corpo = _richiesta("GET", "/health", timeout=5)
        if codice == 200:
            try:
                return json.loads(corpo)
            except json.JSONDecodeError:
                print(f"  risposta non JSON: {corpo[:200]}")
                return None
        time.sleep(1)
    print("  nessuna risposta")
    return None


def controlla_accesso(username, password):
    codice, corpo = _richiesta("POST", "/api/auth/login", {"username": username, "password": password})
    if codice != 200:
        print(f"  FAIL login ({codice})")
        return False
    print("  OK   login")

    codice, corpo = _richiesta("GET", "/api/libraries")
    if codice != 200:
        print(f"  FAIL elenco biblioteche ({codice})")
        return False
    dati = json.loads(corpo)
    voci = dati.get("items", dati) if isinstance(dati, dict) else dati
    print(f"  OK   elenco biblioteche ({len(voci)} visibili)")

    codice, _ = _richiesta("POST", "/api/auth/logout")
    print(f"  {'OK  ' if codice == 200 else 'FAIL'} logout ({codice})")
    return codice == 200


def main():
    health = controlla_health()
    if health is None:
        print("Istanza non raggiungibile: smoke test interrotto.")
        return 2

    stato = health.get("status")
    print(f"  stato: {stato}")
    for chiave in ("ollama_message", "openrouter_message"):
        if health.get(chiave):
            print(f"  {chiave}: {health[chiave]}")
    for avviso in health.get("warnings", []):
        print(f"  AVVISO: {avviso}")

    esito = 0 if stato == "healthy" else 1

    password = os.environ.get("ERMES_ADMIN_PASSWORD")
    if password:
        print("Accesso:")
        if not controlla_accesso(os.environ.get("ERMES_ADMIN_USERNAME", "admin"), password):
            esito = 1
    else:
        print("ERMES_ADMIN_PASSWORD non impostata: controllo di accesso saltato.")

    print(f"\nSmoke test: {'OK' if esito == 0 else 'PROBLEMI RILEVATI'} (uscita {esito})")
    return esito


if __name__ == "__main__":
    sys.exit(main())
