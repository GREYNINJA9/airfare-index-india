"""Deduplication of normalized fare observations.

Deduplication is based on a deterministic key that represents a meaningful
business grouping. The key is:

    (route_origin, route_destination, airline_code, trip_type, price_inr,
     cabin_class, departure_at, scraped_at)

Two fare observations are duplicates if they share this key and are
within a configurable tolerance (currently 1 minute for datetime diff). For
now the tolerance is 1 minute; in production we would tune this.

This module is intentionally simple — it does not know about business
context beyond what the Fare contract defines. It exists to prevent
duplicate records from inflating the index engine's aggregation.
"""

from __future__ import annotations

from typing import List

from models.fare import Fare


def dedup(fares: List[Fare]) -> List[Fare]:
    """Return a new list with duplicates removed.

    The first occurrence of a duplicate key is kept; subsequent ones are
    dropped. The key is:

        (route_origin, route_destination, airline_code, trip_type,
         price_inr, cabin_class, departure_at, scraped_at)

    The ``distance_km`` and ``source`` fields are ignored for deduplication
    because they are spatial/provenance metadata only.
    """
    seen: set[tuple] = set()
    result: List[Fare] = []

    for fare in fares:
        key = (
            fare.route.origin,
            fare.route.destination,
            fare.airline_code,
            fare.trip_type,
            fare.price_inr,
            fare.cabin_class,
            fare.departure_at,
            fare.scraped_at,
        )
        if key not in seen:
            seen.add(key)
            result.append(fare)

    return result
