"""Canonical domain models package.

This package is the single source of truth for the project's domain data
contract. It is intentionally dependency-free beyond Pydantic — it imports no
scraper, pipeline, database, or API code — so every downstream layer can
import the contract without coupling.

Public contract:

* :class:`models.route.Route` — origin/destination IATA pair.
* :class:`models.fare.Fare` — a single normalized fare observation.
* :class:`models.fare.RawFareSource` — raw provenance attached to a Fare.
* Enums: :class:`CabinClass`, :class:`SourceType`, :class:`TripType`.
* :data:`INDIAN_CURRENCY` — the canonical business currency (``"INR"``).

Note: :mod:`models.index` is intentionally left empty for now; the index
calculation contract is a later phase.
"""

from models.fare import (
    INDIAN_CURRENCY,
    CabinClass,
    Fare,
    RawFareSource,
    SourceType,
    TripType,
)
from models.route import Route

__all__ = [
    "INDIAN_CURRENCY",
    "CabinClass",
    "Fare",
    "RawFareSource",
    "Route",
    "SourceType",
    "TripType",
]
