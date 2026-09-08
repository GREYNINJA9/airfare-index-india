"""Deterministic unit tests for pipeline.normalizer.

The normalizer is the single chokepoint that produces Fare instances.
No network access; no wall-clock dependence.
"""

import pytest

from models.fare import CabinClass, SourceType, TripType
from pipeline.normalizer import (
    FareNormalizationError,
    normalize,
)

# --- helpers ------------------------------------------------------------


def _raw_fare(**overrides):
    """A valid raw fare record (ISO-8601 datetimes), optionally overridden."""
    base = {
        "route": {"origin": "DEL", "destination": "BOM", "distance_km": 1138.0},
        "airline_code": "6E",
        "price_inr": 5249.0,
        "cabin_class": "ECONOMY",
        "departure_at": "2026-09-15T06:00:00+00:00",
        "scraped_at": "2026-08-27T10:00:00+00:00",
        "trip_type": "ONE_WAY",
        "source": {
            "source_name": "IndiGo",
            "source_type": "AIRLINE",
            "raw_price": 5249.0,
            "raw_currency": "INR",
            "raw_cabin_label": "Economy Saver",
            "source_url": "https://www.goindigo.in/flights",
            "raw_offer_id": "IG-DEL-BOM",
        },
    }
    base.update(overrides)
    return base


# --- valid normalization ------------------------------------------------


def test_normalize_valid_record():
    fare = normalize(_raw_fare())
    assert fare.route.origin == "DEL"
    assert fare.route.destination == "BOM"
    assert fare.airline_code == "6E"
    assert fare.price_inr == 5249.0
    assert fare.cabin_class is CabinClass.ECONOMY
    assert fare.trip_type is TripType.ONE_WAY
    assert fare.source.source_type is SourceType.AIRLINE
    assert fare.source.raw_currency == "INR"


def test_normalize_accepts_datetime_objects():
    from datetime import datetime, timezone

    record = _raw_fare(
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
    )
    fare = normalize(record)
    assert fare.departure_at.tzinfo is not None
    assert fare.scraped_at.tzinfo is not None


def test_normalize_rejects_lowercase_enum_strings():
    """Enum values must be uppercase (cleaner uppercases them first)."""
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(cabin_class="business"))
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(trip_type="round_trip"))


def test_normalize_accepts_lowercase_airline_code():
    fare = normalize(_raw_fare(airline_code="6e"))
    assert fare.airline_code == "6E"


def test_normalize_accepts_alphanumeric_airline_codes():
    for code in ("6E", "I5", "SG", "AI"):
        fare = normalize(_raw_fare(airline_code=code))
        assert fare.airline_code == code


def test_normalize_produces_fare_instance():
    """Normalized fares are valid Fare instances with correct normalized fields."""
    fare = normalize(_raw_fare())
    from models.fare import Fare

    assert isinstance(fare, Fare)
    assert fare.airline_code == "6E"


# --- invalid normalization ----------------------------------------------


def test_normalize_rejects_non_dict():
    with pytest.raises(FareNormalizationError):
        normalize("not a record")  # type: ignore[arg-type]
    with pytest.raises(FareNormalizationError):
        normalize([1, 2, 3])  # type: ignore[arg-type]


def test_normalize_rejects_non_inr_currency():
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(source={**_raw_fare()["source"], "raw_currency": "USD"}))


def test_normalize_rejects_missing_required_fields():
    record = _raw_fare()
    record.pop("price_inr")
    with pytest.raises(FareNormalizationError):
        normalize(record)
    record = _raw_fare()
    record.pop("airline_code")
    with pytest.raises(FareNormalizationError):
        normalize(record)


def test_normalize_rejects_invalid_enum():
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(cabin_class="LUXURY"))
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(trip_type="ONE_AND_A_HALF"))


def test_normalize_rejects_invalid_airline_code():
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(airline_code="6E3"))
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(airline_code="6"))


def test_normalize_rejects_non_numeric_price():
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(price_inr="expensive"))
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(price_inr=None))


def test_normalize_rejects_bad_iso_string():
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(departure_at="not-a-date"))
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(scraped_at=12345))


def test_normalize_propagates_route_validation():
    """A route with identical origin/destination propagates as a normalization error."""
    with pytest.raises(FareNormalizationError):
        normalize(_raw_fare(route={"origin": "DEL", "destination": "DEL"}))


def test_normalize_propagates_raw_source_validation():
    """A raw source missing required fields propagates as a normalization error."""
    record = _raw_fare()
    record["source"].pop("source_name")
    with pytest.raises(FareNormalizationError):
        normalize(record)
