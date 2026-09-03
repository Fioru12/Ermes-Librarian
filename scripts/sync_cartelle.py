"""Sincronizzazione e monitoraggio delle cartelle registrate in Ermes Knowledge.

Utilizzo:
  # Scansione singola immediata di tutte le cartelle:
  python scripts/sync_cartelle.py

  # Monitoraggio continuo ogni N secondi (default 15):
  python scripts/sync_cartelle.py --watch --interval 10
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import cfg
from core.folder_watcher import sync_all_sources
from core.library_store import LibraryStore


def main():
    parser = argparse.ArgumentParser(description="Sincronizza le cartelle collegate in Ermes Knowledge.")
    parser.add_argument("--watch", action="store_true", help="Esegui in modalità monitoraggio continuo")
    parser.add_argument("--interval", type=int, default=15, help="Intervallo in secondi tra le scansioni (default: 15)")
    args = parser.parse_args()

    store = LibraryStore(cfg.LIBRARY_DB_PATH)
    print("=== Ermes Knowledge — Sincronizzazione Cartelle ===")
    print(f"Database: {cfg.LIBRARY_DB_PATH}")

    if not args.watch:
        print("Scansione di tutte le cartelle collegate...")
        summary = sync_all_sources(store, cfg.LIBRARY_STORAGE_DIR)
        print(f"Cartelle scansionate: {summary['scanned_sources']}")
        print(f"Nuovi documenti importati: {summary['total_imported']}")
        if summary["total_failed"]:
            print(f"Errori riscontrati: {summary['total_failed']}")
        print("Sincronizzazione completata.")
        return

    print(f"Avvio monitoraggio continuo (intervallo: {args.interval}s). Premi CTRL+C per terminare.")
    try:
        while True:
            summary = sync_all_sources(store, cfg.LIBRARY_STORAGE_DIR)
            if summary["total_imported"] > 0:
                print(f"[{time.strftime('%H:%M:%S')}] Rilevati e importati {summary['total_imported']} nuovi documenti.")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitoraggio terminato.")


if __name__ == "__main__":
    main()
