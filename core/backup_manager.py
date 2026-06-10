"""
backup_manager.py
Sistema di backup e recovery per Ermes.
Esegue backup incrementali di KG, ChromaDB, logs, e configurazioni.
"""
import json
import logging
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from config import cfg

_logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(cfg.BASE_DIR, "backups")
MAX_BACKUPS = 10  # Mantieni ultimi N backup


def _get_backup_path() -> str:
    """Crea directory backup se non esiste."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _cleanup_old_backups(keep: int = MAX_BACKUPS):
    """Mantieni solo gli ultimi N backup."""
    backups = sorted(Path(BACKUP_DIR).glob("ermes_backup_*.tar.gz"))
    if len(backups) > keep:
        for old in backups[: len(backups) - keep]:
            old.unlink()
            _logger.info("Backup rimosso: %s", old.name)


def create_backup(label: str = "") -> dict:
    """
    Crea un backup completo del sistema.
    
    Include:
    - Knowledge Graph (data/winsarp_graph.json)
    - ChromaDB (chroma_db/)
    - Logs (logs/)
    - Configurazioni (.env, config.py)
    - Gold set (evaluation/)
    
    Returns:
        dict con path, dimensione, timestamp.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"ermes_backup_{ts}{('_' + label) if label else ''}"
    backup_path = os.path.join(_get_backup_path(), f"{backup_name}.tar.gz")

    _logger.info("Creazione backup: %s", backup_name)

    items_backed_up = []

    with tarfile.open(backup_path, "w:gz") as tar:
        # 1. Knowledge Graph
        kg_path = os.path.join(cfg.BASE_DIR, "data", "winsarp_graph.json")
        if os.path.exists(kg_path):
            tar.add(kg_path, arcname="data/winsarp_graph.json")
            items_backed_up.append("knowledge_graph")

        # 2. ChromaDB
        chroma_path = cfg.CHROMA_DIR
        if os.path.exists(chroma_path):
            tar.add(chroma_path, arcname="chroma_db")
            items_backed_up.append("chroma_db")

        # 3. Logs (ultimi 100 file)
        logs_path = cfg.LOGS_DIR
        if os.path.exists(logs_path):
            log_files = sorted(
                Path(logs_path).glob("*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:100]
            for lf in log_files:
                tar.add(str(lf), arcname=f"logs/{lf.name}")
            items_backed_up.append(f"logs ({len(log_files)} files)")

        # 4. Configurazioni
        for cfg_file in [".env", "config.py", "requirements.txt"]:
            cfg_path = os.path.join(cfg.BASE_DIR, cfg_file)
            if os.path.exists(cfg_path):
                tar.add(cfg_path, arcname=cfg_file)
                items_backed_up.append(cfg_file)

        # 5. Evaluation gold set
        eval_path = os.path.join(cfg.BASE_DIR, "evaluation", "gold_set.json")
        if os.path.exists(eval_path):
            tar.add(eval_path, arcname="evaluation/gold_set.json")
            items_backed_up.append("gold_set")

        # 6. Metadata
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "items": items_backed_up,
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
    for f in sorted(Path(BACKUP_DIR).glob("ermes_backup_*.tar.gz"), reverse=True):
        size_mb = f.stat().st_size / (1024 * 1024)
        backups.append({
            "name": f.stem,
            "path": str(f),
            "size_mb": round(size_mb, 2),
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return backups


def restore_backup(backup_name: str, dry_run: bool = False) -> dict:
    """
    Ripristina un backup.
    
    Args:
        backup_name: Nome del backup (senza .tar.gz)
        dry_run: Se True, mostra solo cosa verrebbe ripristinato
    
    Returns:
        dict con items ripristinati.
    """
    backup_path = os.path.join(BACKUP_DIR, f"{backup_name}.tar.gz")
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup non trovato: {backup_name}")

    _logger.info("Restore backup: %s (dry_run=%s)", backup_name, dry_run)

    restored = []
    with tarfile.open(backup_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "backup_metadata.json":
                continue

            target = os.path.join(cfg.BASE_DIR, member.name)

            if dry_run:
                restored.append(member.name)
                continue

            if member.isdir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with tar.extractfile(member) as src:
                    with open(target, "wb") as dst:
                        dst.write(src.read())
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
        "backup_dir": BACKUP_DIR,
        "max_backups": MAX_BACKUPS,
    }
