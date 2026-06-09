"""
backup.py
Script per backup automatizzato di Ermes - Enterprise Knowledge Hub.
Backup periodico di ChromaDB, documenti, configurazione e utenti.
"""
import json
import logging
import tarfile
from datetime import datetime
from pathlib import Path

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackupManager:
    """Gestore backup automatizzato."""

    def __init__(self, base_dir: str = ".", backup_dir: str = "backups"):
        """
        Inizializza gestore backup.

        Args:
            base_dir: Directory base del progetto
            backup_dir: Directory dove salvare i backup
        """
        self.base_dir = Path(base_dir).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Directory da backuppare
        self.dirs_to_backup = [
            "chroma_db",
            "documenti",
            "security",
            "logs"
        ]

        # File da backuppare
        self.files_to_backup = [
            ".env",
            "config.py"
        ]

    def create_backup_name(self) -> str:
        """
        Crea nome backup con timestamp.

        Returns:
            Nome del file backup
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"ermes_backup_{timestamp}.tar.gz"

    def create_backup(self) -> str:
        """
        Crea backup completo.

        Returns:
            Percorso del file backup creato
        """
        backup_name = self.create_backup_name()
        backup_path = self.backup_dir / backup_name

        logger.info(f"Inizio backup: {backup_name}")

        try:
            with tarfile.open(backup_path, "w:gz") as tar:
                # Backup directory
                for dir_name in self.dirs_to_backup:
                    dir_path = self.base_dir / dir_name
                    if dir_path.exists() and dir_path.is_dir():
                        logger.info(f"Backup directory: {dir_name}")
                        tar.add(dir_path, arcname=dir_name)
                    else:
                        logger.warning(f"Directory non trovata: {dir_name}")

                # Backup file
                for file_name in self.files_to_backup:
                    file_path = self.base_dir / file_name
                    if file_path.exists() and file_path.is_file():
                        logger.info(f"Backup file: {file_name}")
                        tar.add(file_path, arcname=file_name)
                    else:
                        logger.warning(f"File non trovato: {file_name}")

            # Crea manifest backup
            manifest = {
                "timestamp": datetime.now().isoformat(),
                "backup_file": backup_name,
                "backup_size": backup_path.stat().st_size,
                "directories_backed": [d for d in self.dirs_to_backup if (self.base_dir / d).exists()],
                "files_backed": [f for f in self.files_to_backup if (self.base_dir / f).exists()]
            }

            manifest_path = self.backup_dir / f"{backup_name}.manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            logger.info(f"Backup completato: {backup_path} ({backup_path.stat().st_size / (1024*1024):.2f} MB)")
            return str(backup_path)

        except Exception as e:
            logger.error(f"Errore durante backup: {e}")
            # Rimuovi file parziale se esiste
            if backup_path.exists():
                backup_path.unlink()
            raise

    def cleanup_old_backups(self, keep_count: int = 7) -> int:
        """
        Rimuove backup vecchi, mantenendo gli ultimi N.

        Args:
            keep_count: Numero di backup da mantenere

        Returns:
            Numero di backup rimossi
        """
        backups = sorted(self.backup_dir.glob("ermes_backup_*.tar.gz"), reverse=True)

        if len(backups) <= keep_count:
            logger.info(f"Nessun backup da rimuovere (totali: {len(backups)}, mantenere: {keep_count})")
            return 0

        to_remove = backups[keep_count:]
        removed_count = 0

        for backup in to_remove:
            try:
                # Rimuovi backup
                backup.unlink()
                # Rimuovi manifest se esiste
                manifest = self.backup_dir / f"{backup.name}.manifest.json"
                if manifest.exists():
                    manifest.unlink()
                logger.info(f"Rimosso backup vecchio: {backup.name}")
                removed_count += 1
            except Exception as e:
                logger.error(f"Errore rimozione backup {backup.name}: {e}")

        logger.info(f"Rimossi {removed_count} backup vecchi")
        return removed_count

    def restore_backup(self, backup_file: str) -> None:
        """
        Ripristina backup.

        Args:
            backup_file: Percorso del file backup da ripristinare
        """
        backup_path = Path(backup_file)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup non trovato: {backup_file}")

        logger.info(f"Inizio ripristino backup: {backup_file}")

        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                # Estrai tutto nella directory base
                tar.extractall(path=self.base_dir)

            logger.info(f"Ripristino completato: {backup_file}")

        except Exception as e:
            logger.error(f"Errore durante ripristino: {e}")
            raise

    def list_backups(self) -> list[dict]:
        """
        Lista tutti i backup disponibili.

        Returns:
            Lista di informazioni sui backup
        """
        backups = []

        for backup_file in sorted(self.backup_dir.glob("ermes_backup_*.tar.gz")):
            manifest_file = self.backup_dir / f"{backup_file.name}.manifest.json"

            backup_info = {
                "file": backup_file.name,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "created": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            }

            # Carica manifest se esiste
            if manifest_file.exists():
                try:
                    with open(manifest_file) as f:
                        manifest = json.load(f)
                        backup_info["manifest"] = manifest
                except Exception as e:
                    logger.warning(f"Errore lettura manifest {manifest_file}: {e}")

            backups.append(backup_info)

        return backups


def main():
    """Funzione principale per esecuzione da CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Gestione backup Ermes")
    parser.add_argument("action", choices=["create", "restore", "list", "cleanup"], help="Azione da eseguire")
    parser.add_argument("--backup-file", help="File backup per ripristino")
    parser.add_argument("--keep", type=int, default=7, help="Numero backup da mantenere")
    parser.add_argument("--base-dir", default=".", help="Directory base del progetto")
    parser.add_argument("--backup-dir", default="backups", help="Directory backup")

    args = parser.parse_args()

    manager = BackupManager(args.base_dir, args.backup_dir)

    if args.action == "create":
        backup_path = manager.create_backup()
        manager.cleanup_old_backups(args.keep)
        print(f"Backup creato: {backup_path}")

    elif args.action == "restore":
        if not args.backup_file:
            print("Errore: specificare --backup-file per ripristino")
            return
        manager.restore_backup(args.backup_file)
        print(f"Backup ripristinato: {args.backup_file}")

    elif args.action == "list":
        backups = manager.list_backups()
        print(f"\nBackup disponibili ({len(backups)}):")
        for backup in backups:
            size_mb = backup["size"] / (1024*1024)
            print(f"  - {backup['file']} ({size_mb:.2f} MB, {backup['created']})")

    elif args.action == "cleanup":
        removed = manager.cleanup_old_backups(args.keep)
        print(f"Rimossi {removed} backup vecchi")


if __name__ == "__main__":
    main()
