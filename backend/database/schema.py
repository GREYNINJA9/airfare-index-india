"""Database schema initialization and maintenance.

This module contains the DDL that creates the ``fares`` and ``index_results``
tables for the PostgreSQL backend. ``init_sqlite_schema`` is retained solely
for the one-time SQLite → PostgreSQL data migration path.
"""

from __future__ import annotations

import sqlite3


def init_sqlite_schema(conn: sqlite3.Connection) -> None:
    """Create the SQLite tables and indexes (used by the migration script)."""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS fares (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        route_origin        TEXT    NOT NULL,
        route_destination   TEXT    NOT NULL,
        route_distance_km   REAL    NOT NULL,
        airline_code        TEXT    NOT NULL,
        price_inr           REAL    NOT NULL,
        cabin_class         TEXT    NOT NULL,
        departure_at        TEXT    NOT NULL,
        scraped_at          TEXT    NOT NULL,
        trip_type           TEXT    NOT NULL,
        source_name         TEXT,
        source_type         TEXT,
        raw_price           REAL,
        raw_currency        TEXT,
        raw_cabin_label     TEXT,
        source_url          TEXT,
        raw_offer_id        TEXT UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_fares_route_origin ON fares(route_origin);
    CREATE INDEX IF NOT EXISTS idx_fares_route_destination ON fares(route_destination);
    CREATE INDEX IF NOT EXISTS idx_fares_scraped_at ON fares(scraped_at);

    CREATE TABLE IF NOT EXISTS index_results (
        id                        INTEGER PRIMARY KEY AUTOINCREMENT,
        base_period               TEXT    NOT NULL,
        current_period            TEXT    NOT NULL,
        overall_laspeyres_index   REAL    NOT NULL,
        overall_jevons_index      REAL    NOT NULL,
        methodology_json          TEXT    NOT NULL,
        item_indices_json         TEXT    NOT NULL,
        UNIQUE(base_period, current_period)
    );
    CREATE INDEX IF NOT EXISTS idx_index_results_base_current
        ON index_results(base_period, current_period);
"""
    conn.executescript(schema_sql)


def init_postgres_schema(conn) -> None:
    """Create the PostgreSQL tables and indexes if they do not exist."""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS fares (
        id                  SERIAL PRIMARY KEY,
        route_origin        TEXT    NOT NULL,
        route_destination   TEXT    NOT NULL,
        route_distance_km   DOUBLE PRECISION NOT NULL,
        airline_code        TEXT    NOT NULL,
        price_inr           DOUBLE PRECISION NOT NULL,
        cabin_class         TEXT    NOT NULL,
        departure_at        TEXT    NOT NULL,
        scraped_at          TEXT    NOT NULL,
        trip_type           TEXT    NOT NULL,
        source_name         TEXT,
        source_type         TEXT,
        raw_price           DOUBLE PRECISION,
        raw_currency        TEXT,
        raw_cabin_label     TEXT,
        source_url          TEXT,
        raw_offer_id        TEXT UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_fares_route_origin ON fares(route_origin);
    CREATE INDEX IF NOT EXISTS idx_fares_route_destination ON fares(route_destination);
    CREATE INDEX IF NOT EXISTS idx_fares_scraped_at ON fares(scraped_at);

    CREATE TABLE IF NOT EXISTS index_results (
        id                        SERIAL PRIMARY KEY,
        base_period               TEXT    NOT NULL,
        current_period            TEXT    NOT NULL,
        overall_laspeyres_index   DOUBLE PRECISION NOT NULL,
        overall_jevons_index      DOUBLE PRECISION NOT NULL,
        methodology_json          TEXT    NOT NULL,
        item_indices_json         TEXT    NOT NULL,
        UNIQUE(base_period, current_period)
    );
    CREATE INDEX IF NOT EXISTS idx_index_results_base_current
        ON index_results(base_period, current_period);
"""
    # Check if this is our wrapper or raw connection
    actual_conn = getattr(conn, "pg_conn", conn)
    cur = actual_conn.cursor()
    cur.execute(schema_sql)
    actual_conn.commit()


def truncate_tables(conn) -> None:
    """Safely truncate all data tables, resetting primary key sequences.

    Used for test isolation.
    """
    actual_conn = getattr(conn, "pg_conn", conn)
    cur = actual_conn.cursor()
    cur.execute("TRUNCATE TABLE fares, index_results RESTART IDENTITY CASCADE;")
    actual_conn.commit()


def init_schema(conn) -> None:
    """Initialize PostgreSQL schema."""
    init_postgres_schema(conn)
