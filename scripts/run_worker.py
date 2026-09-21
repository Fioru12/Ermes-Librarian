"""CLI entrypoint for running standalone distributed ingestion workers.

Usage:
    python scripts/run_worker.py --concurrency 4 --poll-interval 1.0
    python scripts/run_worker.py --once
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import cfg
from core.distributed_worker import DistributedIngestionWorker
from core.library_store import LibraryStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Ermes Distributed Ingestion Worker Daemon")
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=int(getattr(cfg, "INGESTION_WORKERS", 2)),
        help="Number of concurrent worker threads (default: from config)",
    )
    parser.add_argument(
        "--poll-interval",
        "-p",
        type=float,
        default=1.0,
        help="Polling interval in seconds when queue is idle (default: 1.0)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending jobs in the queue once and exit (batch/cron mode)",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help="Custom identifier for this worker instance",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )

    store = LibraryStore(cfg.LIBRARY_DB_PATH)
    storage_root = Path(cfg.LIBRARY_STORAGE_DIR)

    worker = DistributedIngestionWorker(
        store=store,
        storage_root=storage_root,
        worker_id=args.worker_id,
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
    )

    if args.once:
        logging.info("Modalità batch: elaborazione job pendenti...")
        count = worker.run_once()
        logging.info("Batch completato: %d job elaborati.", count)
        return 0

    worker.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
