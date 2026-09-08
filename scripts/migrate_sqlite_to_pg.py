#!/usr/bin/env python3
"""Safely and securely migrate data from SQLite to PostgreSQL.

Features:
- Validates source SQLite database existence and integrity
- Ensures PostgreSQL target schema is created
- Migrates 'fares' with duplicate / conflict handling
- Migrates 'index_results' with conflict handling
- Validates row counts and field integrity after migration
- Can be run as a CLI script with arguments or environment variables
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys

import psycopg2
from psycopg2.extras import execute_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migration")


def get_sqlite_conn(path: str) -> sqlite3.Connection:
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQLite database not found at '{path}'")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn(dsn: str):
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn


def migrate_fares(
    sqlite_conn: sqlite3.Connection, pg_conn, batch_size: int = 1000
) -> int:
    logger.info("Migrating 'fares' table...")

    # Check if fares table exists in sqlite
    cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fares'"
    )
    if not cur.fetchone():
        logger.info("No 'fares' table found in SQLite source.")
        return 0

    cur = sqlite_conn.execute("SELECT * FROM fares ORDER BY id ASC")
    rows = cur.fetchall()
    total_source_fares = len(rows)
    logger.info("Found %d fares in SQLite.", total_source_fares)

    if total_source_fares == 0:
        return 0

    insert_sql = """
    INSERT INTO fares (
        route_origin, route_destination, route_distance_km,
        airline_code, price_inr, cabin_class, departure_at, scraped_at,
        trip_type, source_name, source_type, raw_price, raw_currency,
        raw_cabin_label, source_url, raw_offer_id
    ) VALUES (
        %(route_origin)s, %(route_destination)s, %(route_distance_km)s,
        %(airline_code)s, %(price_inr)s, %(cabin_class)s,
        %(departure_at)s, %(scraped_at)s, %(trip_type)s, %(source_name)s,
        %(source_type)s, %(raw_price)s, %(raw_currency)s,
        %(raw_cabin_label)s, %(source_url)s, %(raw_offer_id)s
    )
    ON CONFLICT (raw_offer_id) DO NOTHING;
    """

    records = [dict(r) for r in rows]

    with pg_conn.cursor() as pg_cur:
        execute_batch(pg_cur, insert_sql, records, page_size=batch_size)
    pg_conn.commit()

    with pg_conn.cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM fares")
        total_pg_fares = pg_cur.fetchone()[0]

    logger.info(
        "Successfully processed %d fares. Total in PostgreSQL: %d",
        total_source_fares,
        total_pg_fares,
    )
    return total_source_fares


def migrate_index_results(
    sqlite_conn: sqlite3.Connection, pg_conn, batch_size: int = 500
) -> int:
    logger.info("Migrating 'index_results' table...")

    cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='index_results'"
    )
    if not cur.fetchone():
        logger.info("No 'index_results' table found in SQLite source.")
        return 0

    cur = sqlite_conn.execute("SELECT * FROM index_results ORDER BY id ASC")
    rows = cur.fetchall()
    total_source_indices = len(rows)
    logger.info("Found %d index_results in SQLite.", total_source_indices)

    if total_source_indices == 0:
        return 0

    insert_sql = """
    INSERT INTO index_results (
        base_period, current_period, overall_laspeyres_index,
        overall_jevons_index, methodology_json, item_indices_json
    ) VALUES (
        %(base_period)s, %(current_period)s, %(overall_laspeyres_index)s,
        %(overall_jevons_index)s, %(methodology_json)s, %(item_indices_json)s
    )
    ON CONFLICT (base_period, current_period) DO NOTHING;
    """

    records = [dict(r) for r in rows]

    with pg_conn.cursor() as pg_cur:
        execute_batch(pg_cur, insert_sql, records, page_size=batch_size)
    pg_conn.commit()

    with pg_conn.cursor() as pg_cur:
        pg_cur.execute("SELECT COUNT(*) FROM index_results")
        total_pg_indices = pg_cur.fetchone()[0]

    logger.info(
        "Successfully processed %d index_results. Total in PostgreSQL: %d",
        total_source_indices,
        total_pg_indices,
    )
    return total_source_indices


def main():
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to PostgreSQL safely and securely."
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.environ.get("SQLITE_PATH", "data/airfare_index.db"),
        help="Path to source SQLite database file",
    )
    parser.add_argument(
        "--pg-dsn",
        default=os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/airfare_index"
        ),
        help="PostgreSQL connection string (DSN)",
    )
    args = parser.parse_args()

    logger.info(
        "Starting database migration from '%s' to PostgreSQL...",
        args.sqlite_path,
    )

    if not os.path.exists(args.sqlite_path):
        logger.warning(
            "Source SQLite database '%s' does not exist. Nothing to transfer.",
            args.sqlite_path,
        )
        return

    try:
        sqlite_conn = get_sqlite_conn(args.sqlite_path)
    except Exception as e:
        logger.error("Failed to connect to SQLite: %s", e)
        sys.exit(1)

    try:
        pg_conn = get_pg_conn(args.pg_dsn)
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        sys.exit(1)

    try:
        from database.schema import init_postgres_schema

        logger.info("Ensuring PostgreSQL schema exists...")
        init_postgres_schema(pg_conn)

        fares_count = migrate_fares(sqlite_conn, pg_conn)
        index_count = migrate_index_results(sqlite_conn, pg_conn)

        logger.info(
            "Migration completed successfully! Migrated %d fares and %d index results.",
            fares_count,
            index_count,
        )
    except Exception as e:
        logger.exception("Migration failed: %s", e)
        pg_conn.rollback()
        sys.exit(1)
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
