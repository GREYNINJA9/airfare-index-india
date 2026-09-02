"""Database schema initialization.

This module contains the DDL that creates the ``fares`` table for the
prototype. It is deliberately minimal and matches the canonical ``Fare``
model fields. The schema is deliberately simple: a single table with
all fields needed for the index engine and API.

The schema is created via ``DatabaseConnector.init_schema()`` which
receives a live connection.
"""

from __future__ import annotations

import sqlite3


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the ``fares`` table if it does not exist.

    The schema matches the canonical ``Fare`` model:

        id               INTEGER PRIMARY KEY AUTOINCREMENT
        route_origin     TEXT    NOT NULL
        route_destination TEXT    NOT NULL
        distance_km      REAL    NOT NULL
        airline_code     TEXT    NOT NULL
        price_inr        REAL    NOT NULL
        cabin_class      TEXT    NOT NULL
        departure_at    TEXT    NOT NULL  -- ISO-8601 UTC string
        scraped_at      TEXT    NOT NULL  -- ISO-8601 UTC string
        trip_type        TEXT    NOT NULL
        source_name      TEXT
        source_type      TEXT
        raw_price        REAL
        raw_currency      TEXT
        raw_cabin_label  TEXT
        source_url       TEXT
        raw_offer_id     TEXT

    Indexes are added on ``route_origin``, ``route_destination``,
    and ``scraped_at`` for the index engine's time-series queries.

    This module also initializes the derived ``index_results`` table for
    persisted index computations.
    """

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
        raw_cabin_label   TEXT,
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
        item_indices_json        TEXT    NOT NULL,
        UNIQUE(base_period, current_period)
    );
    CREATE INDEX IF NOT EXISTS idx_index_results_base_current
        ON index_results(base_period, current_period);
"""

    conn.executescript(schema_sql)
