"""
backup_manager.py
Sistema di backup e recovery per Ermes.
Esegue backup incrementali di KG, ChromaDB, logs, e configurazioni.
"""

import json
import logging
import os
import re
import tarfile
import threading
from datetime import datetime
from pathlib import Path

from config import cfg

_logger = logging.getLogger(__name__)

MAX_BACKUPS = 10  # ripiego, se la configurazione non dice altro

# Il nome arriva dal percorso di una rotta
# (`POST /backup/restore/{backup_name}`) e finiva in os.path.join senza
# alcuna validazione: su Windows la barra rovesciata e' un separatore, quindi
# un nome come "..\\..\\altrove\\archivio" portava fuori dalla cartella dei
# backup, cioe' lasciava ripristinare un archivio qualsiasi presente sul
# disco.
_NOME_BACKUP_AMMESSO = re.compile(r"^ermes_backup_[A-Za-z0-9_.\-]{1,120}$")

_backup_lock = threading.Lock()


def _get_backup_path() -> str:
    """La cartella dei backup, risolta dalla configurazione a ogni chiamata.

    Prima era una costante di modulo, `os.path.join(cfg.BASE_DIR, "backups")`,
    calcolata al momento dell'import — e `cfg.BACKUP_DIR` esisteva in
    config/storage.py senza che niente la leggesse. Chi impostava
    ERMES_BACKUP_DIR per mandare i backup su un disco separato, che e' il
    motivo per cui quella variabile esiste, li otteneva accanto ai dati che
    dovevano proteggere. Un backup sullo stesso disco dell'originale non e' un
    backup.

    Un valore relativo si risolve rispetto a BASE_DIR, cosi' il default
    ("backups") resta la cartella di prima.
    """
    configurata = str(getattr(cfg, "BACKUP_DIR", "") or "backups").strip()
    percorso = Path(configurata)
    if not percorso.is_absolute():
        percorso = Path(cfg.BASE_DIR) / percorso
    percorso.mkdir(parents=True, exist_ok=True)
    return str(percorso)


def _conservazione() -> int:
    """Quanti backup mantenere. `cfg.BACKUP_RETENTION_COUNT` era ugualmente
    inerte: la conservazione restava fissa a MAX_BACKUPS."""
    try:
        valore = int(getattr(cfg, "BACKUP_RETENTION_COUNT", MAX_BACKUPS))
    except (TypeError, ValueError):
        return MAX_BACKUPS
    return valore if valore > 0 else MAX_BACKUPS


def _cleanup_old_backups(keep: int | None = None):
    """Mantieni solo gli ultimi N backup."""
    if keep is None:
        keep = _conservazione()
    backups = sorted(Path(_get_backup_path()).glob("ermes_backup_*.tar.gz"))
    if len(backups) > keep:
        for old in backups[: len(backups) - keep]:
            old.unlink()
            _logger.info("Backup rimosso: %s", old.name)


def _percorso_archivio(backup_name: str) -> str:
    if not _NOME_BACKUP_AMMESSO.match(backup_name or ""):
        raise ValueError(f"Nome di backup non ammesso: {backup_name!r}")
    return os.path.join(_get_backup_path(), f"{backup_name}.tar.gz")


def _bersaglio_dentro_base(nome_membro: str) -> Path:
    """Dove scrivere un membro dell'archivio, rifiutando le uscite dalla base.

    `target = os.path.join(cfg.BASE_DIR, member.name)` scriveva dove diceva
    l'archivio: con un nome di membro assoluto os.path.join scarta del tutto
    la base, e con `../..` si esce dalla cartella. E' la vulnerabilita'
    classica degli archivi tar, e qui non passa da `extractall`, quindi il
    filtro di sicurezza di tarfile non si applica.

    Non serviva nemmeno un archivio ostile per incontrarla: i nomi dei membri
    li calcola `os.path.relpath(percorso, cfg.BASE_DIR)`, quindi se
    LIBRARY_DB_PATH o LIBRARY_STORAGE_DIR puntano fuori da BASE_DIR — una
    configurazione legittima, per esempio i documenti su una condivisione di
    rete — quei nomi cominciano per `../` e il ripristino scrive fuori.
    """
    base = Path(cfg.BASE_DIR).resolve()
    bersaglio = (base / nome_membro).resolve()
    if bersaglio != base and base not in bersaglio.parents:
        raise ValueError(f"Membro del backup fuori dalla cartella dell'applicazione: {nome_membro!r}")
    return bersaglio


def _arcname(percorso: str, esterni: list[str] | None = None) -> str:
    """Il nome con cui un percorso entra nell'archivio.

    `os.path.relpath(percorso, cfg.BASE_DIR)` produce nomi che cominciano per
    `../` quando l'elemento sta fuori da BASE_DIR — configurazione legittima:
    i documenti su una condivisione di rete, il database su un altro disco. Un
    nome cosi' e' proprio quello che il ripristino ora rifiuta, e lasciarlo
    entrare significherebbe un archivio che contiene qualcosa che non si puo'
    ripristinare, senza dirlo a nessuno.

    Un elemento esterno entra quindi sotto `external/`, e il ripristino lo
    scrive li' dentro invece che al percorso originale: i dati sono salvi, ma
    riportarli al loro posto e' un'operazione manuale. Il metadata e il log lo
    dichiarano.
    """
    relativo = os.path.relpath(percorso, cfg.BASE_DIR).replace("\\", "/")
    if relativo.startswith("../") or relativo == ".." or os.path.isabs(relativo):
        base = os.path.basename(percorso.rstrip("/").rstrip("\\")) or "senza_nome"
        esterno = "external/" + base
        if esterni is not None:
            esterni.append(percorso)
        _logger.warning(
            "Backup: %s e' fuori da BASE_DIR, archiviato come %s (il ripristino non lo rimette al percorso originale)",
            percorso,
            esterno,
        )
        return esterno
    return relativo


def create_backup(label: str = "") -> dict:
    """
    Crea un backup completo del sistema (thread-safe).

    Include:
    - Knowledge Graph (data/winsarp_graph.json)
    - ChromaDB (chroma_db/)
    - Logs (logs/)
    - Configurazioni (.env, config.py)
    - Gold set (evaluation/)

    Returns:
        dict con path, dimensione, timestamp.
    """
    with _backup_lock:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"ermes_backup_{ts}{('_' + label) if label else ''}"
        backup_path = os.path.join(_get_backup_path(), f"{backup_name}.tar.gz")

        _logger.info("Creazione backup: %s", backup_name)

        items_backed_up = []
        esterni: list[str] = []

        with tarfile.open(backup_path, "w:gz") as tar:
            lib_db_path = getattr(cfg, "LIBRARY_DB_PATH", os.path.join(cfg.BASE_DIR, "data", "ermes_knowledge.sqlite3"))
            if os.path.exists(lib_db_path):
                rel_path = _arcname(lib_db_path, esterni)
                tar.add(lib_db_path, arcname=rel_path)
                items_backed_up.append("library_db")

            lib_storage = getattr(cfg, "LIBRARY_STORAGE_DIR", os.path.join(cfg.BASE_DIR, "storage", "libraries"))
            if os.path.exists(lib_storage):
                rel_path = _arcname(lib_storage, esterni)
                tar.add(lib_storage, arcname=rel_path)
                items_backed_up.append("library_storage")

            sec_dir = getattr(cfg, "SECURITY_DIR", os.path.join(cfg.BASE_DIR, "security"))
            if os.path.exists(sec_dir):
                rel_path = _arcname(sec_dir, esterni)
                tar.add(sec_dir, arcname=rel_path)
                items_backed_up.append("security")

            kg_path = os.path.join(cfg.BASE_DIR, "data", "winsarp_graph.json")
            if os.path.exists(kg_path):
                tar.add(kg_path, arcname="data/winsarp_graph.json")
                items_backed_up.append("knowledge_graph")

            chroma_path = getattr(cfg, "CHROMA_DIR", os.path.join(cfg.BASE_DIR, "chroma_db"))
            if os.path.exists(chroma_path):
                tar.add(chroma_path, arcname="chroma_db")
                items_backed_up.append("chroma_db")

            logs_path = getattr(cfg, "LOGS_DIR", os.path.join(cfg.BASE_DIR, "logs"))
            if os.path.exists(logs_path):
                log_files = sorted(
                    Path(logs_path).glob("*.jsonl"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )[:100]
                for lf in log_files:
                    tar.add(str(lf), arcname=f"logs/{lf.name}")
                items_backed_up.append(f"logs ({len(log_files)} files)")

            for cfg_file in [".env", "config.py", "requirements.txt"]:
                cfg_path = os.path.join(cfg.BASE_DIR, cfg_file)
                if os.path.exists(cfg_path):
                    tar.add(cfg_path, arcname=cfg_file)
                    items_backed_up.append(cfg_file)

            eval_path = os.path.join(cfg.BASE_DIR, "evaluation", "gold_set.json")
            if os.path.exists(eval_path):
                tar.add(eval_path, arcname="evaluation/gold_set.json")
                items_backed_up.append("gold_set")

            metadata = {
                "timestamp": datetime.now().isoformat(),
                "label": label,
                "items": items_backed_up,
                "external": esterni,
                "version": "1.0.0",
            }
            meta_json = json.dumps(metadata, indent=2)
            import io

            meta_bytes = meta_json.encode("utf-8")
            info = tarfile.TarInfo(name="backup_metadata.json")
            info.size = len(meta_bytes)
            tar.addfile(info, io.BytesIO(meta_bytes))

        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        _cleanup_old_backups()

        result = {
            "path": backup_path,
            "name": backup_name,
            "size_mb": round(size_mb, 2),
            "items": items_backed_up,
            "timestamp": datetime.now().isoformat(),
        }
        _logger.info("Backup completato: %s (%.2f MB)", backup_name, size_mb)
        return result


def list_backups() -> list[dict]:
    """Elenca tutti i backup disponibili."""
    backups = []
    for f in sorted(Path(_get_backup_path()).glob("ermes_backup_*.tar.gz"), reverse=True):
        size_mb = f.stat().st_size / (1024 * 1024)
        backups.append(
            {
                # `f.stem` toglie un solo suffisso: da "ermes_backup_X.tar.gz"
                # dava "ermes_backup_X.tar", un nome che restore_backup non
                # accetta (ci aggiunge ".tar.gz"). Elenco e ripristino non
                # erano mai stati usati in sequenza: ripristinare il backup
                # che l'API stessa elencava rispondeva "backup non trovato".
                "name": f.name[: -len(".tar.gz")],
                "path": str(f),
                "size_mb": round(size_mb, 2),
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
        )
    return backups


def restore_backup(backup_name: str, dry_run: bool = False) -> dict:
    """
    Ripristina un backup (thread-safe, atomic writes).

    Args:
        backup_name: Nome del backup (senza .tar.gz)
        dry_run: Se True, mostra solo cosa verrebbe ripristinato

    Returns:
        dict con items ripristinati.
    """
    with _backup_lock:
        backup_path = _percorso_archivio(backup_name)
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup non trovato: {backup_name}")

        _logger.info("Restore backup: %s (dry_run=%s)", backup_name, dry_run)

        restored = []
        with tarfile.open(backup_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name == "backup_metadata.json":
                    continue

                # Validato prima del ramo dry_run: il dry run serve a
                # decidere se ripristinare, quindi non deve elencare membri
                # che il ripristino reale rifiuta.
                target = str(_bersaglio_dentro_base(member.name))

                if dry_run:
                    restored.append(member.name)
                    continue

                if member.isdir():
                    os.makedirs(target, exist_ok=True)
                elif member.isfile():
                    import tempfile

                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        # tarfile can return None for a regular-looking member
                        # in a corrupted or truncated archive; extractfile()'s
                        # own contract is best-effort even for isfile()==True.
                        _logger.warning("Restore: impossibile leggere %s dal backup, saltato", member.name)
                        continue
                    with extracted as src:
                        data = src.read()
                    tmp = tempfile.NamedTemporaryFile(dir=os.path.dirname(target), delete=False, suffix=".tmp")
                    try:
                        tmp.write(data)
                        tmp.close()
                        os.replace(tmp.name, target)
                    except Exception:
                        if os.path.exists(tmp.name):
                            os.unlink(tmp.name)
                        raise
                else:
                    # Ne' directory ne' file regolare (symlink, device, fifo):
                    # non atteso da un backup che questo stesso modulo crea,
                    # ma un archivio esterno o corrotto potrebbe contenerne uno.
                    # Restare fuori da entrambi i rami sopra non deve comunque
                    # far dichiarare "ripristinato" un membro mai scritto.
                    _logger.warning("Restore: membro %s non e' un file o una directory, saltato", member.name)
                    continue
                restored.append(member.name)

        _logger.info("Restore completato: %d items", len(restored))
        return {"restored": restored, "dry_run": dry_run, "backup": backup_name}


def get_backup_status() -> dict:
    """Stato corrente dei backup."""
    backups = list_backups()
    return {
        "total_backups": len(backups),
        "latest": backups[0] if backups else None,
        "total_size_mb": round(sum(b["size_mb"] for b in backups), 2),
        "backup_dir": _get_backup_path(),
        "max_backups": _conservazione(),
    }
