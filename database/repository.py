"""Repository: persistence and query helpers for fare observations.

The repository is the only layer that writes/reads ``Fare`` rows to/from
SQLite for the prototype.

This module is intentionally deterministic: all functions operate on
validated domain models and return fully reconstructed, validated models
(e.g. :class:`models.fare.Fare`, :class:`models.index.IndexResult`).

Existing dictionary-returning fare query helpers are preserved for
backwards compatibility.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import List, Optional

from models.fare import Fare
from models.index import IndexResult


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC string for storage."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(__import__("datetime").timezone.utc)
    return dt.isoformat()


def insert_fare(conn: sqlite3.Connection, fare: Fare) -> int:
    """Insert a single ``Fare`` and return its row id, or 0 on conflict."""
    sql = """
    INSERT OR IGNORE INTO fares (
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
    return int(cur.lastrowid) if cur.rowcount > 0 else 0


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


def get_fares(conn: sqlite3.Connection) -> List[Fare]:
    """Return all stored fares as validated :class:`models.fare.Fare`.

    Ordering is deterministic to support repeatable computations and tests:
    primarily by ``scraped_at`` ascending, then by autoincrement ``id``.
    """

    cur = conn.execute(
        """
        SELECT * FROM fares
        ORDER BY scraped_at ASC, id ASC
        """
    )

    fares: List[Fare] = []
    for row in cur.fetchall():
        source_name = row["source_name"]
        source_type = row["source_type"]
        raw_price = row["raw_price"]
        raw_currency = row["raw_currency"]
        raw_cabin_label = row["raw_cabin_label"]

        if (
            source_name is None
            or source_type is None
            or raw_price is None
            or raw_currency is None
            or raw_cabin_label is None
        ):
            continue

        route_distance_km = row["route_distance_km"]
        distance_km: float | None
        try:
            distance_km_f = (
                float(route_distance_km) if route_distance_km is not None else 0.0
            )
        except (TypeError, ValueError):
            distance_km_f = 0.0

        # Historical behaviour: insert_fare stores `None` distance as 0.0.
        distance_km = None if distance_km_f == 0.0 else distance_km_f

        departure_at = datetime.fromisoformat(row["departure_at"])
        scraped_at = datetime.fromisoformat(row["scraped_at"])

        fares.append(
            Fare.model_validate(
                {
                    "route": {
                        "origin": row["route_origin"],
                        "destination": row["route_destination"],
                        "distance_km": distance_km,
                    },
                    "airline_code": row["airline_code"],
                    "price_inr": float(row["price_inr"]),
                    "cabin_class": row["cabin_class"],
                    "departure_at": departure_at,
                    "scraped_at": scraped_at,
                    "trip_type": row["trip_type"],
                    "source": {
                        "source_name": source_name,
                        "source_type": source_type,
                        "raw_price": float(raw_price),
                        "raw_currency": raw_currency,
                        "raw_cabin_label": raw_cabin_label,
                        "source_url": row["source_url"],
                        "raw_offer_id": row["raw_offer_id"],
                    },
                }
            )
        )

    return fares


def insert_index_result(conn: sqlite3.Connection, result: IndexResult) -> int:
    """Persist a computed :class:`models.index.IndexResult`, or 0 on conflict."""

    sql = """
    INSERT OR IGNORE INTO index_results (
        base_period,
        current_period,
        overall_laspeyres_index,
        overall_jevons_index,
        methodology_json,
        item_indices_json
    ) VALUES (?, ?, ?, ?, ?, ?)
    """

    params = (
        result.base_period.isoformat(),
        result.current_period.isoformat(),
        float(result.overall_laspeyres_index),
        float(result.overall_jevons_index),
        result.methodology.model_dump_json(),
        json.dumps([ii.model_dump(mode="json") for ii in result.item_indices]),
    )

    cur = conn.execute(sql, params)
    conn.commit()
    return int(cur.lastrowid) if cur.rowcount > 0 else 0


def get_index_results(
    conn: sqlite3.Connection,
    *,
    base_period: date | None = None,
    current_period: date | None = None,
) -> List[IndexResult]:
    """Return persisted index results as validated :class:`models.index.IndexResult`."""

    where_clauses: List[str] = []
    params: List[str] = []

    if base_period is not None:
        where_clauses.append("base_period = ?")
        params.append(base_period.isoformat())

    if current_period is not None:
        where_clauses.append("current_period = ?")
        params.append(current_period.isoformat())

    sql = "SELECT * FROM index_results"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    # Deterministic: by insertion id.
    sql += " ORDER BY id ASC"

    cur = conn.execute(sql, tuple(params))

    out: List[IndexResult] = []
    for row in cur.fetchall():
        methodology_data = json.loads(row["methodology_json"])
        item_indices_data = json.loads(row["item_indices_json"])

        out.append(
            IndexResult.model_validate(
                {
                    "base_period": date.fromisoformat(row["base_period"]),
                    "current_period": date.fromisoformat(row["current_period"]),
                    "overall_laspeyres_index": float(row["overall_laspeyres_index"]),
                    "overall_jevons_index": float(row["overall_jevons_index"]),
                    "methodology": methodology_data,
                    "item_indices": item_indices_data,
                }
            )
        )

    return out


def get_index_result(
    conn: sqlite3.Connection, *, base_period: date, current_period: date
) -> Optional[IndexResult]:
    """Return the first persisted IndexResult for a period pair."""

    results = get_index_results(
        conn, base_period=base_period, current_period=current_period
    )
    return results[0] if results else None
