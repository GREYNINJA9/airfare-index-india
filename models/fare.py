"""Canonical Fare domain model.

This module defines the Fare contract — the central data contract that flows
through the whole system::

    scraper → validation → cleaning → normalization → deduplication
           → database → index engine → API

A :class:`Fare` represents a single **normalized** fare observation for an
Indian domestic flight. It deliberately keeps two concerns separate:

* **Normalized business fields** — the canonical, analysis-ready values used
  by the index engine and API (route, price in INR, cabin class, departure
  time, scrape time, trip type, carrier).
* **Raw provenance** — a :class:`RawFareSource` record describing *where and
  how* the observation was captured (airline vs OTA, the source's name, the
  price/currency/cabin label *as originally captured*, and the source URL).
  Provenance is attached via ``source`` and is **never** used as a business
  field downstream.

The model contains no scraping logic and is not coupled to any particular
airline or OTA. Datetimes are timezone-aware. Prices are strictly positive.
Currency codes are ISO-4217 (three uppercase letters); the business price is
expressed in INR after normalization, while the original price/currency are
preserved verbatim in the provenance record.

This module uses only Pydantic v2 and the Python standard library — no new
dependencies are introduced.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)

from models.route import Route

__all__ = [
    "CabinClass",
    "SourceType",
    "TripType",
    "INDIAN_CURRENCY",
    "RawFareSource",
    "Fare",
]

#: The canonical business currency for the airfare index. All normalized
#: fare prices are expressed in INR; original currencies are preserved in
#: :class:`RawFareSource`.
INDIAN_CURRENCY: str = "INR"

#: IATA carrier codes are two uppercase alphanumeric characters — they may
#: include digits (e.g. ``"6E"`` for IndiGo, ``"I5"`` for Air India Express,
#: ``"SG"`` for SpiceJet). The pattern is kept generic on purpose so it does
#: not hardcode any single carrier.
_AIRLINE_CODE_PATTERN = r"^[A-Z0-9]{2}$"
_CURRENCY_CODE_PATTERN = r"^[A-Z]{3}$"


class CabinClass(str, Enum):
    """Canonical cabin classes for a domestic fare observation."""

    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class SourceType(str, Enum):
    """Where a fare observation was captured: an airline site or an OTA."""

    AIRLINE = "AIRLINE"
    OTA = "OTA"


class TripType(str, Enum):
    """Directionality of the fare: one-way or round-trip."""

    ONE_WAY = "ONE_WAY"
    ROUND_TRIP = "ROUND_TRIP"


class RawFareSource(BaseModel):
    """Raw provenance for a fare observation, kept separate from business data.

    This records the fare *exactly as captured* from the source, before any
    normalization. None of these fields are used as business fields by the
    index engine; they exist for traceability, audit, and re-normalization.

    Attributes:
        source_name: Human-readable name of the source (e.g. ``"IndiGo"``,
            ``"MakeMyTrip"``). Free-form text.
        source_type: Whether the source is an airline or an OTA.
        raw_price: Price as originally captured, in ``raw_currency``.
            Must be strictly positive.
        raw_currency: ISO-4217 currency code as captured (e.g. ``"INR"``).
            Three uppercase letters.
        raw_cabin_label: The cabin/fare label exactly as shown by the source
            (e.g. ``"Economy Saver"``, ``"Business"``). Free-form text; the
            canonical mapping is stored separately as ``cabin_class`` on
            :class:`Fare`.
        source_url: Optional URL of the page where the fare was observed.
        raw_offer_id: Optional source-specific offer/booking identifier, as
            captured verbatim.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    source_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Human-readable name of the source, e.g. 'MakeMyTrip'.",
    )
    source_type: SourceType = Field(
        ...,
        description="Whether the source is an airline site or an OTA.",
    )
    raw_price: float = Field(
        ...,
        gt=0.0,
        description="Price as originally captured, in raw_currency. > 0.",
    )
    raw_currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        pattern=_CURRENCY_CODE_PATTERN,
        description="ISO-4217 currency code as captured, e.g. 'INR'.",
    )
    raw_cabin_label: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Cabin/fare label exactly as shown by the source.",
    )
    source_url: HttpUrl | None = Field(
        default=None,
        description="Optional URL of the page where the fare was observed.",
    )
    raw_offer_id: str | None = Field(
        default=None,
        max_length=200,
        description="Optional source-specific offer/booking identifier.",
    )

    @field_validator("raw_currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v: str) -> str:
        """Uppercase the currency code before pattern validation."""
        if not isinstance(v, str):
            return v
        return v.strip().upper()


class Fare(BaseModel):
    """A single normalized fare observation for an Indian domestic flight.

    Business fields (analysis-ready):

        route: Origin/destination pair of IATA airport codes.
        airline_code: IATA carrier code (two uppercase alphanumeric
            characters, e.g. ``"6E"``) of the carrier offering the fare.
        price_inr: Normalized fare price in INR, strictly positive.
        cabin_class: Canonical cabin class.
        departure_at: Scheduled departure time, timezone-aware.
        scraped_at: Time the observation was captured, timezone-aware.
        trip_type: One-way or round-trip.

    Provenance (separate from business data):

        source: :class:`RawFareSource` describing the raw capture. Kept
            separate so the index engine never reads raw-source fields as
            business fields.

    Validation:
        * ``price_inr`` must be strictly positive.
        * ``airline_code`` must match ``^[A-Z0-9]{2}$`` (IATA codes may include
          digits, e.g. ``"6E"``).
        * ``departure_at`` and ``scraped_at`` must be timezone-aware (naive
          datetimes are rejected to avoid ambiguous local-time interpretation).
        * No cross-field time ordering is enforced between ``scraped_at`` and
          ``departure_at`` — both orderings are legitimate (advance booking
          scraped before departure; historical capture scraped after). A
          "not in the future" rule is intentionally omitted because it would
          require a wall clock and break deterministic testing.

    Notes:
        The model is not coupled to any particular airline or OTA, and
        contains no scraping logic. See :mod:`models.route` for the spatial
        contract.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    # --- normalized business fields ---------------------------------------

    route: Route = Field(
        ...,
        description="Origin/destination IATA pair for the flight.",
    )
    airline_code: str = Field(
        ...,
        min_length=2,
        max_length=2,
        pattern=_AIRLINE_CODE_PATTERN,
        description="IATA carrier code, two uppercase alphanumeric chars, e.g. '6E'.",
    )
    price_inr: float = Field(
        ...,
        gt=0.0,
        description="Normalized fare price in INR. Strictly positive.",
    )
    cabin_class: CabinClass = Field(
        ...,
        description="Canonical cabin class.",
    )
    departure_at: datetime = Field(
        ...,
        description=(
            "Scheduled departure time. Must be timezone-aware (naive "
            "datetimes are rejected)."
        ),
    )
    scraped_at: datetime = Field(
        ...,
        description=(
            "Time the observation was captured. Must be timezone-aware "
            "(naive datetimes are rejected)."
        ),
    )
    trip_type: TripType = Field(
        ...,
        description="Directionality of the fare: one-way or round-trip.",
    )

    # --- raw provenance (kept separate from business fields) --------------

    source: RawFareSource = Field(
        ...,
        description=(
            "Raw provenance for the observation, exactly as captured from "
            "the source. Not used as a business field by the index engine."
        ),
    )

    @field_validator("airline_code", mode="before")
    @classmethod
    def _normalize_airline_code(cls, v: str) -> str:
        """Uppercase the carrier code before pattern validation."""
        if not isinstance(v, str):
            return v
        return v.strip().upper()

    @field_validator("departure_at", "scraped_at")
    @classmethod
    def _require_tzaware(cls, v: datetime) -> datetime:
        """Reject naive datetimes to avoid ambiguous local-time interpretation."""
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("datetime must be timezone-aware (got a naive datetime)")
        return v

    # NOTE: No cross-field ordering between `scraped_at` and `departure_at` is
    # enforced. Both orderings are legitimate: a forward-looking observation
    # is captured *before* the flight departs (scraped_at < departure_at),
    # while a historical observation is captured *after* departure. A
    # "scraped_at must not be in the future" rule is deliberately omitted
    # because it would require a wall clock and break deterministic testing.
