"""
utils.py
Funzioni di supporto: hash documenti, validazione file,
log JSON/TXT, pulizia log vecchi, pulizia ChromaDB orfani.
Nessuna dipendenza da Streamlit o LlamaIndex.
"""
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timedelta

# ============================================================
# CONFIGURAZIONE
# ============================================================
LOG_RETENTION_DAYS = 30
_HASH_CHUNK_SIZE   = 65536  # 64 KB — lettura a blocchi, evita OOM su file grandi
_logger = logging.getLogger(__name__)


# ============================================================
# HASH DOCUMENTI
# ============================================================
def compute_dir_hash(folder: str) -> str:
    """
    Calcola un hash MD5 del contenuto di una cartella.
    Considera nome e contenuto di ogni file, in ordine alfabetico.
    Lettura a blocchi da 64KB — evita caricamento intero file in RAM.
    """
    h = hashlib.md5()
    try:
        for fname in sorted(os.listdir(folder)):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                h.update(fname.encode())
                with open(fpath, "rb") as f:
                    while chunk := f.read(_HASH_CHUNK_SIZE):
                        h.update(chunk)
    except Exception as ex:
        _logger.warning("compute_dir_hash: errore su %s: %s", folder, ex)
    return h.hexdigest()


def load_saved_hashes(hash_file: str) -> dict:
    """Carica gli hash salvati dal file JSON. Restituisce {} se non esiste."""
    if os.path.exists(hash_file):
        try:
            with open(hash_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as ex:
            _logger.warning("load_saved_hashes: errore lettura %s: %s", hash_file, ex)
            return {}
    return {}


def load_hash(hash_file: str, modulo: str) -> str | None:
    """
    Carica l'hash salvato per un singolo modulo.
    Ritorna None se il file non esiste o il modulo non e' mai stato indicizzato.
    """
    return load_saved_hashes(hash_file).get(modulo)


def save_hash(hash_file: str, modulo: str, hash_val: str):
    """Salva l'hash di un modulo nel file JSON."""
    hashes = load_saved_hashes(hash_file)
    hashes[modulo] = hash_val
    os.makedirs(os.path.dirname(hash_file), exist_ok=True)
    with open(hash_file, "w", encoding="utf-8") as f:
        json.dump(hashes, f)


def docs_changed(hash_file: str, modulo: str, folder: str,
                 cache: dict | None = None) -> bool:
    """
    Controlla se i documenti del modulo sono cambiati rispetto all'ultimo hash.
    cache: dizionario opzionale per evitare ricalcoli nello stesso rerun.
    """
    if cache is not None and modulo in cache:
        return cache[modulo]

    saved = load_saved_hashes(hash_file).get(modulo)
    if saved is None:
        try:
            result = any(
                os.path.isfile(os.path.join(folder, f))
                for f in os.listdir(folder)
            )
        except Exception:
            result = False
    else:
        result = compute_dir_hash(folder) != saved

    if cache is not None:
        cache[modulo] = result
    return result


# ============================================================
# VALIDAZIONE DOCUMENTI
# ============================================================
def validate_docs(folder: str) -> tuple[bool, str, list]:
    """
    Verifica che la cartella esista e contenga file leggibili.

    Ritorna:
        (ok, messaggio, lista_file_validi)
        - ok=False se non ci sono file utilizzabili
        - messaggio contiene eventuali warning su file ignorati
    """
    if not os.path.exists(folder):
        return False, f"Cartella non trovata: {folder}", []

    all_files = [
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
    ]
    if not all_files:
        return False, "La cartella e' vuota. Aggiungi almeno un documento.", []

    valid, invalid = [], []
    for fname in all_files:
        fpath = os.path.join(folder, fname)
        if os.path.getsize(fpath) == 0:
            invalid.append(f"{fname} (0 byte — file vuoto)")
            continue
        try:
            with open(fpath, "rb") as f:
                f.read(64)
            valid.append(fname)
        except Exception as e:
            invalid.append(f"{fname} (errore lettura: {e})")

    if not valid:
        return (
            False,
            "Tutti i file sono vuoti o corrotti:\n" + "\n".join(invalid),
            []
        )

    msg = ("File ignorati (vuoti/corrotti): " + ", ".join(invalid)) if invalid else ""
    return True, msg, valid


# ============================================================
# LOG JSON
# ============================================================
def init_session_log(logs_dir: str) -> str:
    """Crea un nuovo file di log JSONL per la sessione corrente."""
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(logs_dir, f"session_{ts}.jsonl")


def append_to_log(log_path: str, modulo: str, role: str, content: str,
                  errors: list | None = None, elapsed: float | None = None):
    """
    Aggiunge un messaggio al log JSON della sessione.
    Ora usa append-only JSONL per performance migliori (O(1) invece di O(N)).
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "modulo":    modulo,
        "role":      role,
        "content":   content,
    }
    if errors:
        entry["errors"] = errors
    if elapsed is not None:
        entry["elapsed_sec"] = round(elapsed, 2)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_log_txt(messages: list) -> str:
    """
    Genera il contenuto testuale scaricabile della conversazione.
    Include errori, logica applicata e tempi di risposta.
    """
    lines = [
        f"LOG ERMES — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 50,
        "",
    ]
    for m in messages:
        lines.append(f"[{m['role'].upper()}]: {m['content']}")
        if m.get("errors"):
            lines.append("  Errori rilevati:")
            for e in m["errors"]:
                lines.append(f"    !! {e}")
        if m.get("exp"):
            lines.append(f"  Logica: {m['exp']}")
        if m.get("elapsed") is not None:
            lines.append(f"  Tempo risposta: {m['elapsed']:.1f}s")
        lines.append("")
    return "\n".join(lines)


def cleanup_old_logs(logs_dir: str, retention_days: int = LOG_RETENTION_DAYS):
    """Elimina i file di log piu' vecchi di retention_days giorni."""
    if not os.path.exists(logs_dir):
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for fname in os.listdir(logs_dir):
        fpath = os.path.join(logs_dir, fname)
        if os.path.isfile(fpath):
            try:
                if datetime.fromtimestamp(os.path.getmtime(fpath)) < cutoff:
                    os.remove(fpath)
            except Exception:
                pass


# ============================================================
# PULIZIA CHROMADB ORFANI
# ============================================================
def cleanup_orphan_collections(base_chroma_path: str,
                                base_docs_dir: str) -> int:
    """
    Rimuove le cartelle ChromaDB che non corrispondono
    ad alcun modulo presente in base_docs_dir.
    Ritorna il numero di cartelle rimosse.
    """
    if not os.path.exists(base_chroma_path):
        return 0

    moduli_validi = set()
    if os.path.exists(base_docs_dir):
        for d in os.listdir(base_docs_dir):
            if os.path.isdir(os.path.join(base_docs_dir, d)):
                moduli_validi.add(d.lower())

    rimossi = 0
    for entry in os.listdir(base_chroma_path):
        full_path = os.path.join(base_chroma_path, entry)
        if os.path.isdir(full_path) and entry not in moduli_validi:
            shutil.rmtree(full_path, ignore_errors=True)
            rimossi += 1
    return rimossi
