"""Normalization: the single chokepoint that produces Fare.

This module converts raw fare observations (as written by scrapers or test
fixtures) into validated `models.fare.Fare` instances. It is the ONLY place
in the codebase that calls `Fare.model_validate` — every consumer goes
through here, so the raw-to-normalized mapping has exactly one
implementation.

If a record cannot be normalized (e.g., required field missing, currency
not INR, datetime not timezone-aware), a `FareNormalizationError` is
raised with a precise reason.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ValidationError

from models.fare import (
    INDIAN_CURRENCY,
    CabinClass,
    Fare,
    RawFareSource,
    TripType,
)
from models.route import Route


class FareNormalizationError(ValueError):
    """Raised when a raw record cannot be normalized to a Fare."""


def normalize(raw_record: dict[str, Any]) -> Fare:
    """Convert a raw fare dict into a validated `Fare`.

    Validates the raw provenance via `RawFareSource` first, then assembles
    the normalized business fields and validates the full `Fare`. A
    normalization failure (currency not INR, naive datetime, etc.) raises
    `FareNormalizationError` with a precise reason.
    """
    if not isinstance(raw_record, dict):
        raise FareNormalizationError(
            f"raw record must be a dict, got {type(raw_record).__name__}"
        )

    try:
        source = RawFareSource.model_validate(raw_record.get("source", {}))
    except ValidationError as e:
        raise FareNormalizationError(f"invalid raw source: {e}") from e

    if source.raw_currency != INDIAN_CURRENCY:
        raise FareNormalizationError(
            f"non-INR raw currency: {source.raw_currency!r} "
            f"(Day-3 prototype supports INR only)"
        )

    try:
        cabin = _parse_enum(raw_record.get("cabin_class"), CabinClass, "cabin_class")
        trip = _parse_enum(raw_record.get("trip_type"), TripType, "trip_type")
        route = Route.model_validate(raw_record.get("route", {}))
        airline_code = str(raw_record.get("airline_code", "")).strip().upper()
        price_inr = raw_record.get("price_inr")
        departure_at = raw_record.get("departure_at")
        scraped_at = raw_record.get("scraped_at")
    except ValidationError as e:
        raise FareNormalizationError(f"invalid normalized field: {e}") from e

    if not isinstance(price_inr, (int, float)) or isinstance(price_inr, bool):
        raise FareNormalizationError(
            f"price_inr must be numeric, got {type(price_inr).__name__}"
        )

    departure_at = _coerce_datetime(departure_at, "departure_at")
    scraped_at = _coerce_datetime(scraped_at, "scraped_at")

    try:
        return Fare(
            route=route,
            airline_code=airline_code,
            price_inr=float(price_inr),
            cabin_class=cabin,
            departure_at=departure_at,
            scraped_at=scraped_at,
            trip_type=trip,
            source=source,
        )
    except ValidationError as e:
        raise FareNormalizationError(f"Fare validation failed: {e}") from e


def _parse_enum(value: Any, enum_cls: type, field_name: str):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, KeyError) as e:
        raise FareNormalizationError(
            f"invalid {field_name}: {value!r} is not a {enum_cls.__name__}"
        ) from e


def _coerce_datetime(value: Any, field_name: str) -> datetime:
    """Parse a datetime, accepting datetime instances or ISO-8601 strings.

    The model rejects naive datetimes; naive ISO strings are converted to
    UTC-aware datetimes here so the normalizer is the single chokepoint
    for time handling.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as e:
            raise FareNormalizationError(
                f"invalid {field_name}: {value!r} is not ISO-8601"
            ) from e
        if parsed.tzinfo is None:
            # Treat naive ISO strings as UTC to avoid ambiguous interpretation
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    raise FareNormalizationError(
        f"{field_name} must be a datetime or ISO-8601 string, "
        f"got {type(value).__name__}"
    )
