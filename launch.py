"""
Ermes Launcher.
Avvia il backend (che serve anche il frontend precompilato).
Mostra l'IP locale per la condivisione in LAN.
"""
import os
import socket
import subprocess
import time
import urllib.request
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(BASE, ".venv-ermes", "Scripts", "python.exe")
LOG = os.path.join(BASE, "launch.log")
PORT = 8502


def _log(msg: str):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def _check(url: str, timeout: int = 3) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _add_firewall_rule():
    """Tenta di aggiungere regola firewall, senza bloccare se non admin."""
    if not _is_admin():
        _log("Firewall: non amministratore, skip.")
        return
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             "name=Ermes 8502", "dir=in", "action=allow",
             "protocol=TCP", f"localport={PORT}"],
            capture_output=True, check=True)
        _log("Firewall: regola aggiunta.")
    except Exception as e:
        _log(f"Firewall: {e}")


def _clean_pycache():
    """Rimuove tutti i __pycache__ per evitare problemi di bytecode stale."""
    import shutil
    for root, dirs, _ in os.walk(BASE):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)


def _start_backend():
    _clean_pycache()
    log_file = open(os.path.join(BASE, "backend.log"), "w", encoding="utf-8")
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", str(PORT), "--reload"],
        cwd=BASE, stdout=log_file, stderr=log_file,
        creationflags=0x08000000,
    )


def main():
    _log("=== Avvio Ermes ===")
    ip = _get_local_ip()

    # Firewall (se admin)
    _add_firewall_rule()

    # Backend
    if _check(f"http://127.0.0.1:{PORT}/health"):
        _log("Backend gia' attivo.")
    else:
        _start_backend()
        for _ in range(15):
            time.sleep(2)
            if _check(f"http://127.0.0.1:{PORT}/health"):
                _log("Backend avviato.")
                break
        else:
            _log("ERRORE: backend non avviato.")
            return

    local_url = f"http://localhost:{PORT}"
    lan_url = f"http://{ip}:{PORT}"
    webbrowser.open(local_url)
    _log(f"Browser aperto: {local_url}")
    _log(f"Accesso LAN:    {lan_url}")

    print("\n=== Ermes avviato ===")
    print(f"Locale: {local_url}")
    print(f"Rete:   {lan_url}")
    print("\nCondividi l'indirizzo di rete con i tuoi colleghi!")
    print("Se non riescono a connettersi, esegui firewall.bat come amministratore.\n")
    print("Premi Ctrl+C per arrestare...")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        _log("=== Arrestato ===")


if __name__ == "__main__":
    main()
