"""Utility di manutenzione per la pulizia dei file orfani in storage/libraries.

I file orfani sono file fisici rimasti sul disco a cui non corrisponde alcuna
riga nella tabella `documents` del database (accumulati tipicamente durante
esecuzioni di test di sviluppo o eliminazioni manuali).

Uso:
    python scripts/cleanup_orphan_storage.py            # Solo simulazione (dry-run)
    python scripts/cleanup_orphan_storage.py --confirm  # Esegue la rimozione effettiva
"""

import argparse
import os
import sys
from pathlib import Path

# Assicura che la root del progetto sia nel sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import cfg
from core.library_store import LibraryStore


def main():
    parser = argparse.ArgumentParser(description="Pulisce i file orfani dallo storage delle biblioteche.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Conferma l'eliminazione dei file orfani (senza questo flag opera in sola lettura/dry-run).",
    )
    args = parser.parse_args()

    store = LibraryStore(cfg.LIBRARY_DB_PATH)
    report = store.verify_index_consistency(cfg.LIBRARY_STORAGE_DIR, cfg.EMBED_MODEL_ID)
    orphans = report.get("orphan_files", [])

    print(f"Documenti censiti nel database: {report.get('checked_documents', 0)}")
    print(f"File orfani rilevati: {len(orphans)}")

    if not orphans:
        print("Nessun file orfano presente. Lo storage e' perfettamente allineato.")
        return 0

    root = Path(cfg.LIBRARY_STORAGE_DIR).resolve()
    total_bytes = 0
    valid_paths: list[Path] = []

    for rel_path in orphans:
        full_path = (root / rel_path).resolve()
        # Verifica di sicurezza: il file deve trovarsi tassativamente sotto storage_root
        if not full_path.is_relative_to(root):
            print(f"ATTENZIONE: Percorso anomalo ignorato per sicurezza: {full_path}")
            continue
        if full_path.is_file():
            size = full_path.stat().st_size
            total_bytes += size
            valid_paths.append(full_path)

    mb = total_bytes / (1024 * 1024)
    print(f"Spazio totale occupato dai file orfani: {mb:.2f} MB ({len(valid_paths)} file)")

    if not args.confirm:
        print("\nMODALITA' DRY-RUN: Nessun file e' stato modificato o eliminato.")
        print("Per rimuovere definitivamente questi file orfani, rieseguire con:")
        print("    python scripts/cleanup_orphan_storage.py --confirm")
        return 0

    print("\nRimozione dei file orfani in corso...")
    removed_count = 0
    for path in valid_paths:
        try:
            path.unlink()
            removed_count += 1
        except OSError as e:
            print(f"Errore rimozione {path}: {e}")

    print(f"Pulizia completata: {removed_count} file rimossi con successo.")

    # Rimuove cartelle vuote residue
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=False):
        if dirpath != str(root):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
