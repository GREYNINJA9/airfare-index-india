"""Repository: persistence and query helpers for fare observations.

The repository is the only layer that writes/reads ``Fare`` rows to/from
the database. It uses the connector from :mod:`database.connection` and
the schema from :mod:`database.schema`.

All functions are deterministic and operate on validated ``Fare`` objects.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from models.fare import Fare


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC string for storage."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(__import__("datetime").timezone.utc)
    return dt.isoformat()


def insert_fare(conn: sqlite3.Connection, fare: Fare) -> int:
    """Insert a single ``Fare`` and return its row id."""
    sql = """
    INSERT INTO fares (
        route_origin, route_destination, route_distance_km,
        airline_code, price_inr, cabin_class, departure_at, scraped_at,
        trip_type, source_name, source_type, raw_price, raw_currency,
        raw_cabin_label, source_url, raw_offer_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        fare.route.origin,
        fare.route.destination,
        fare.route.distance_km if fare.route.distance_km is not None else 0.0,
        fare.airline_code,
        fare.price_inr,
        fare.cabin_class.value,
        _iso(fare.departure_at),
        _iso(fare.scraped_at),
        fare.trip_type.value,
        fare.source.source_name,
        fare.source.source_type.value,
        fare.source.raw_price,
        fare.source.raw_currency,
        fare.source.raw_cabin_label,
        str(fare.source.source_url) if fare.source.source_url else None,
        fare.source.raw_offer_id,
    )
    cur = conn.execute(sql, params)
    conn.commit()
    return int(cur.lastrowid)


def insert_fares(conn: sqlite3.Connection, fares: List[Fare]) -> int:
    """Insert many ``Fare`` rows, returning the count inserted."""
    return sum(1 for fare in fares if insert_fare(conn, fare) > 0)


def get_fares_by_route(
    conn: sqlite3.Connection, origin: str, destination: str
) -> List[dict]:
    """Return all stored fares for a route as plain dicts."""
    cur = conn.execute(
        """
        SELECT * FROM fares
        WHERE route_origin = ? AND route_destination = ?
        ORDER BY scraped_at ASC
        """,
        (origin, destination),
    )
    return [dict(row) for row in cur.fetchall()]


def get_fare_by_offer_id(conn, raw_offer_id: str) -> Optional[dict]:
    """Return one fare row by its source offer id, or ``None``."""
    if not raw_offer_id:
        return None
    cur = conn.execute("SELECT * FROM fares WHERE raw_offer_id = ?", (raw_offer_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def count_fares(conn) -> int:
    """Return the total number of stored fares."""
    cur = conn.execute("SELECT COUNT(*) AS n FROM fares")
    return int(cur.fetchone()["n"])
