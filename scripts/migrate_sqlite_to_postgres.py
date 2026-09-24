#!/usr/bin/env python3
"""scripts/migrate_sqlite_to_postgres.py
Ermes Enterprise — Script di Migrazione Dati SQLite -> PostgreSQL (Fase 5).

Esegue la migrazione deterministica e a blocchi da un database SQLite esistente
(es. data/ermes_knowledge.sqlite3) a un database PostgreSQL live (ERMES_DATABASE_URL).
Include verifica finale di integrità e parità dei record migrati.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

# Aggiunge la root del progetto al sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ermes.migrate")

# Ordine topologico per rispettare i vincoli di Foreign Key
TABLES_ORDER = [
    "libraries",
    "documents",
    "library_members",
    "document_chunks",
    "document_versions",
    "document_acls",
    "ingestion_jobs",
    "import_sources",
    "chat_integrations",
]


def _get_sqlite_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [str(row[1]) for row in cursor.fetchall()]


def _get_pg_columns(pg_cur: Any, table_name: str) -> list[str]:
    pg_cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [str(row["column_name"]) for row in pg_cur.fetchall()]


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    table_name: str,
    batch_size: int = 500,
    clean_target: bool = False,
) -> tuple[int, int]:
    """Migra una singola tabella da SQLite a PostgreSQL a blocchi."""
    # table_name interpolato piu' sotto arriva sempre da TABLES_ORDER (lista
    # chiusa, mai da un argomento CLI o da un valore letto dai database): il
    # controllo qui non e' contro un attacco possibile in questo script, ma
    # impedisce che diventi possibile se in futuro qualcuno lo richiama con
    # un nome arbitrario. bandit non puo' saperlo dal solo tipo `str`.
    if table_name not in TABLES_ORDER:
        raise ValueError(f"Tabella non riconosciuta: {table_name!r}")
    sqlite_cur = sqlite_conn.cursor()

    # Verifica se la tabella esiste in SQLite
    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    if not sqlite_cur.fetchone():
        logger.warning("Tabella '%s' non presente nel database SQLite di origine. Saltata.", table_name)
        return 0, 0

    sqlite_cols = _get_sqlite_columns(sqlite_cur, table_name)
    with pg_conn.cursor() as pg_cur:
        pg_cols = _get_pg_columns(pg_cur, table_name)

    # Identifica colonne comuni
    common_cols = [col for col in sqlite_cols if col in pg_cols]
    if not common_cols:
        logger.warning("Nessuna colonna comune trovata per la tabella '%s'.", table_name)
        return 0, 0

    if clean_target:
        with pg_conn.cursor() as pg_cur:
            pg_cur.execute(f"TRUNCATE TABLE {table_name} CASCADE")  # nosec B608: table_name validato sopra
        pg_conn.commit()
        logger.info("Tabella target '%s' ripulita con TRUNCATE.", table_name)

    cols_str = ", ".join(common_cols)
    placeholders = ", ".join(["%s"] * len(common_cols))
    insert_sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"  # nosec B608: table_name validato sopra, cols_str da _get_sqlite_columns/_get_pg_columns

    sqlite_cur.execute(f"SELECT {cols_str} FROM {table_name}")  # nosec B608: table_name validato sopra

    total_migrated = 0
    total_skipped = 0

    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break

        processed_rows: list[tuple[Any, ...]] = []
        for r in rows:
            row_dict = dict(r)
            vals: list[Any] = []
            for col in common_cols:
                v = row_dict.get(col)
                # Normalizza embedding_json per PostgreSQL JSONB
                if col == "embedding_json":
                    if v is None or v == "":
                        v = json.dumps(None)
                    elif isinstance(v, str):
                        try:
                            json.loads(v)
                        except Exception:
                            v = json.dumps(None)
                    elif isinstance(v, (list, dict)):
                        v = json.dumps(v)
                vals.append(v)
            processed_rows.append(tuple(vals))

        with pg_conn.cursor() as pg_cur:
            pg_cur.executemany(insert_sql, processed_rows)
            total_migrated += pg_cur.rowcount
            total_skipped += len(processed_rows) - max(0, pg_cur.rowcount)
        pg_conn.commit()

    return total_migrated, total_skipped


def verify_migration(
    sqlite_conn: sqlite3.Connection, pg_conn: Any
) -> dict[str, dict[str, Any]]:
    """Verifica e confronta i record tra SQLite e PostgreSQL."""
    stats: dict[str, dict[str, Any]] = {}
    sqlite_cur = sqlite_conn.cursor()

    for table in TABLES_ORDER:
        sqlite_cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        if not sqlite_cur.fetchone():
            continue

        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608: table viene da TABLES_ORDER, lista chiusa
        sqlite_count = int(sqlite_cur.fetchone()[0])

        with pg_conn.cursor() as pg_cur:
            pg_cur.execute(f"SELECT COUNT(*) as count FROM {table}")  # nosec B608: table viene da TABLES_ORDER, lista chiusa
            pg_row = pg_cur.fetchone()
            pg_count = int(pg_row["count"])

        matched = sqlite_count == pg_count
        stats[table] = {
            "sqlite_count": sqlite_count,
            "postgres_count": pg_count,
            "matched": matched,
        }

    return stats


def run_migration(
    sqlite_path: str | Path,
    pg_url: str,
    batch_size: int = 500,
    clean_target: bool = False,
    verify_only: bool = False,
) -> bool:
    """Entry point principale per l'esecuzione della migrazione."""
    sqlite_file = Path(sqlite_path).resolve()
    if not sqlite_file.is_file():
        logger.error("File database SQLite non trovato: %s", sqlite_file)
        return False

    if not pg_url.startswith("postgresql://") and not pg_url.startswith("postgres://"):
        logger.error("URL PostgreSQL non valido: %s", pg_url)
        return False

    try:
        from core.postgres_backend import connect, ensure_schema
    except ImportError as e:
        logger.error("Dipendenze PostgreSQL mancanti (psycopg): %s", e)
        return False

    logger.info("Apertura connessione SQLite: %s", sqlite_file)
    sqlite_conn = sqlite3.connect(str(sqlite_file))
    sqlite_conn.row_factory = sqlite3.Row

    logger.info("Apertura connessione PostgreSQL: %s", pg_url.split("@")[-1] if "@" in pg_url else pg_url)
    try:
        pg_conn = connect(pg_url)
    except Exception as e:
        logger.error("Impossibile connettersi a PostgreSQL: %s", e)
        sqlite_conn.close()
        return False

    try:
        logger.info("Inizializzazione e verifica schema PostgreSQL...")
        ensure_schema(pg_conn)

        if not verify_only:
            start_time = time.perf_counter()
            logger.info("Inizio migrazione dati (batch_size=%d)...", batch_size)
            for table in TABLES_ORDER:
                migrated, skipped = migrate_table(
                    sqlite_conn=sqlite_conn,
                    pg_conn=pg_conn,
                    table_name=table,
                    batch_size=batch_size,
                    clean_target=clean_target,
                )
                logger.info(
                    "Tabella '%-20s' completata: %d inseriti, %d conflitti/ignorati.",
                    table,
                    migrated,
                    skipped,
                )

            elapsed = time.perf_counter() - start_time
            logger.info("Migrazione completata in %.2f secondi.", elapsed)

        # Verifica di parità
        logger.info("Verifica di parità SQLite <-> PostgreSQL...")
        stats = verify_migration(sqlite_conn, pg_conn)

        all_ok = True
        logger.info("-" * 65)
        logger.info("%-22s | %-12s | %-12s | %-8s", "Tabella", "SQLite", "PostgreSQL", "Esito")
        logger.info("-" * 65)
        for table, data in stats.items():
            esito = "OK" if data["matched"] else "DISALLINEATO"
            if not data["matched"]:
                all_ok = False
            logger.info(
                "%-22s | %-12d | %-12d | %-8s",
                table,
                data["sqlite_count"],
                data["postgres_count"],
                esito,
            )
        logger.info("-" * 65)

        return all_ok
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrazione dati Ermes da SQLite locale a PostgreSQL aziendale."
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.environ.get("ERMES_SQLITE_PATH", cfg.LIBRARY_DB_PATH),
        help="Percorso al database SQLite di origine (default: da configurazione)",
    )
    parser.add_argument(
        "--pg-url",
        default=os.environ.get("ERMES_DATABASE_URL", ""),
        help="URL di connessione PostgreSQL target (es. postgresql://user:pass@host:5432/ermes)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Dimensione batch per inserimenti a blocchi (default: 500)",
    )
    parser.add_argument(
        "--clean-target",
        action="store_true",
        help="Esegue TRUNCATE delle tabelle PostgreSQL prima della migrazione",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Esegue solo la verifica dei conteggi senza migrare dati",
    )

    args = parser.parse_args()

    if not args.pg_url:
        logger.error(
            "Specificare --pg-url oppure valorizzare la variabile d'ambiente ERMES_DATABASE_URL."
        )
        return 1

    success = run_migration(
        sqlite_path=args.sqlite_path,
        pg_url=args.pg_url,
        batch_size=args.batch_size,
        clean_target=args.clean_target,
        verify_only=args.verify_only,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
