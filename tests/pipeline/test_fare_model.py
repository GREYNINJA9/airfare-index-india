"""Deterministic unit tests for the canonical Fare domain contract.

No network access, no wall-clock dependence. All timestamps are fixed UTC
values so the suite is fully deterministic.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from models.fare import (
    INDIAN_CURRENCY,
    CabinClass,
    Fare,
    RawFareSource,
    SourceType,
    TripType,
)
from models.route import Route

# Fixed timestamps (deterministic; no wall clock).
_DEPART = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
_SCRAPE = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
_HISTORICAL_DEPART = datetime(2026, 1, 12, 18, 0, tzinfo=timezone.utc)


def _valid_source(**overrides: object) -> RawFareSource:
    """A valid raw provenance record, optionally overridden for tests."""
    base: dict[str, object] = {
        "source_name": "MakeMyTrip",
        "source_type": SourceType.OTA,
        "raw_price": 5249.0,
        "raw_currency": "INR",
        "raw_cabin_label": "Economy Saver",
        "source_url": "https://www.makemytrip.com/flights/DEL-BOM",
        "raw_offer_id": "MMT-DEL-BOM-20260915",
    }
    base.update(overrides)
    return RawFareSource.model_validate(base)


def _valid_fare(**overrides: object) -> Fare:
    """A valid fare observation, optionally overridden for tests."""
    base: dict[str, object] = {
        "route": Route(origin="DEL", destination="BOM", distance_km=1138.0),
        "airline_code": "6E",
        "price_inr": 5249.0,
        "cabin_class": CabinClass.ECONOMY,
        "departure_at": _DEPART,
        "scraped_at": _SCRAPE,
        "trip_type": TripType.ONE_WAY,
        "source": _valid_source(),
    }
    base.update(overrides)
    return Fare.model_validate(base)


# --- valid creation ------------------------------------------------------


def test_valid_fare_creation() -> None:
    """A well-formed fare is accepted and exposes its normalized fields."""
    fare = _valid_fare()
    assert fare.route.origin == "DEL"
    assert fare.route.destination == "BOM"
    assert fare.airline_code == "6E"
    assert fare.price_inr == 5249.0
    assert fare.cabin_class is CabinClass.ECONOMY
    assert fare.trip_type is TripType.ONE_WAY
    assert fare.departure_at == _DEPART
    assert fare.scraped_at == _SCRAPE
    assert INDIAN_CURRENCY == "INR"


def test_forward_looking_fare_is_valid() -> None:
    """Scraping before departure (advance booking) is a valid observation."""
    fare = _valid_fare()  # scrape Aug 27 < departure Sep 15
    assert fare.scraped_at < fare.departure_at


def test_historical_fare_is_valid() -> None:
    """Scraping after departure (historical capture) is also valid."""
    fare = _valid_fare(
        departure_at=_HISTORICAL_DEPART,
        scraped_at=_SCRAPE,  # scrape after depart
    )
    assert fare.scraped_at > fare.departure_at


def test_alphanumeric_airline_code_accepted() -> None:
    """IATA carrier codes may include digits (e.g. '6E', 'I5')."""
    fare = _valid_fare(airline_code="I5")
    assert fare.airline_code == "I5"


def test_airline_code_uppercased() -> None:
    """Lowercase carrier codes are normalized to uppercase."""
    fare = _valid_fare(airline_code="6e")
    assert fare.airline_code == "6E"


# --- invalid price / currency -------------------------------------------


@pytest.mark.parametrize("bad_price", [0.0, -1.0, -0.01])
def test_reject_nonpositive_price(bad_price: float) -> None:
    """price_inr must be strictly positive."""
    with pytest.raises(ValidationError):
        _valid_fare(price_inr=bad_price)


def test_reject_nonpositive_raw_price() -> None:
    """raw_price in provenance must also be strictly positive."""
    with pytest.raises(ValidationError):
        _valid_source(raw_price=0.0)


@pytest.mark.parametrize("bad_currency", ["IN", "INRR", "1NR", "in", ""])
def test_reject_malformed_raw_currency(bad_currency: str) -> None:
    """raw_currency must be a three-letter currency code."""
    with pytest.raises(ValidationError):
        _valid_source(raw_currency=bad_currency)


def test_raw_currency_uppercased() -> None:
    """A lowercase currency code is normalized to uppercase (valid)."""
    src = _valid_source(raw_currency="inr")
    assert src.raw_currency == "INR"


# --- invalid route ------------------------------------------------------


def test_reject_identical_origin_destination() -> None:
    """A fare with an identical origin/destination is invalid."""
    with pytest.raises(ValidationError):
        _valid_fare(route=Route(origin="DEL", destination="DEL"))


def test_reject_malformed_airline_code() -> None:
    """Carrier codes must be exactly two alphanumeric characters."""
    with pytest.raises(ValidationError):
        _valid_fare(airline_code="6E3")
    with pytest.raises(ValidationError):
        _valid_fare(airline_code="6")


# --- datetime validation ------------------------------------------------


def test_reject_naive_departure_at() -> None:
    """departure_at must be timezone-aware."""
    with pytest.raises(ValidationError):
        _valid_fare(departure_at=datetime(2026, 9, 15, 6, 0))  # naive


def test_reject_naive_scraped_at() -> None:
    """scraped_at must be timezone-aware."""
    with pytest.raises(ValidationError):
        _valid_fare(scraped_at=datetime(2026, 8, 27, 10, 0))  # naive


def test_tz_aware_datetimes_preserved() -> None:
    """Timezone-aware datetimes are preserved through the model."""
    fare = _valid_fare()
    assert fare.departure_at.tzinfo is not None
    assert fare.scraped_at.tzinfo is not None


# --- required vs optional fields ----------------------------------------


def test_required_fields_enforced() -> None:
    """Omitting a required field raises a validation error."""
    minimal = {
        "route": Route(origin="DEL", destination="BOM"),
        "airline_code": "6E",
    }
    with pytest.raises(ValidationError):
        Fare.model_validate(minimal)


def test_optional_source_fields() -> None:
    """source_url and raw_offer_id are optional in provenance."""
    src = RawFareSource.model_validate(
        {
            "source_name": "IndiGo",
            "source_type": SourceType.AIRLINE,
            "raw_price": 5249.0,
            "raw_currency": "INR",
            "raw_cabin_label": "Economy",
        }
    )
    assert src.source_url is None
    assert src.raw_offer_id is None


def test_reject_extra_fields() -> None:
    """Unknown fields are rejected on both Fare and RawFareSource."""
    fare = _valid_fare()
    with pytest.raises(ValidationError):
        Fare.model_validate({**fare.model_dump(), "unexpected": 1})
    with pytest.raises(ValidationError):
        _valid_source(unexpected=1)


# --- enum handling ------------------------------------------------------


def test_cabin_class_enum_values() -> None:
    """All canonical cabin classes are accepted and preserve their value."""
    for cabin in CabinClass:
        fare = _valid_fare(cabin_class=cabin)
        assert fare.cabin_class is cabin


def test_trip_type_enum_values() -> None:
    """Both trip types are accepted and preserve their value."""
    for trip in TripType:
        fare = _valid_fare(trip_type=trip)
        assert fare.trip_type is trip


def test_source_type_enum_values() -> None:
    """Both source types are accepted in provenance."""
    for st in SourceType:
        src = _valid_source(source_type=st)
        assert src.source_type is st


def test_reject_invalid_enum_string() -> None:
    """An unrecognized cabin class string is rejected."""
    with pytest.raises(ValidationError):
        _valid_fare(cabin_class="LUXURY")


# --- serialization / deserialization -------------------------------------


def test_json_roundtrip_preserves_fare() -> None:
    """A fare survives a JSON serialize/deserialize round-trip unchanged."""
    fare = _valid_fare()
    restored = Fare.model_validate_json(fare.model_dump_json())
    assert restored == fare


def test_dict_roundtrip_preserves_fare() -> None:
    """A fare survives a dict serialize/deserialize round-trip unchanged."""
    fare = _valid_fare()
    restored = Fare.model_validate(fare.model_dump())
    assert restored == fare


def test_raw_source_json_roundtrip() -> None:
    """Provenance survives a JSON round-trip unchanged."""
    src = _valid_source()
    restored = RawFareSource.model_validate_json(src.model_dump_json())
    assert restored == src


def test_serialization_separates_business_and_raw() -> None:
    """Serialized output keeps raw provenance nested under 'source'."""
    fare = _valid_fare()
    data = json.loads(fare.model_dump_json())
    assert "source" in data and isinstance(data["source"], dict)
    # Business fields live at top level; raw price/currency nested in source.
    assert data["price_inr"] == fare.price_inr
    assert data["source"]["raw_price"] == fare.source.raw_price
    assert data["source"]["raw_currency"] == fare.source.raw_currency


# --- synthetic dataset ---------------------------------------------------


SYNTHETIC_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "sample" / "synthetic_fares.json"
)


def test_synthetic_dataset_is_labeled_non_real() -> None:
    """The synthetic fixture must declare itself non-real."""
    payload = json.loads(SYNTHETIC_PATH.read_text())
    assert payload["_meta"]["is_real_data"] is False


def test_synthetic_dataset_validates_against_contract() -> None:
    """Every record in the synthetic fixture validates as a Fare."""
    payload = json.loads(SYNTHETIC_PATH.read_text())
    records = payload["fares"]
    assert payload["_meta"]["record_count"] == len(records)
    fares = [Fare.model_validate(r) for r in records]
    # Cover a representative subset of the contract dimensions.
    assert any(f.source.source_type is SourceType.AIRLINE for f in fares)
    assert any(f.source.source_type is SourceType.OTA for f in fares)
    assert any(f.trip_type is TripType.ROUND_TRIP for f in fares)
    assert any(f.cabin_class is CabinClass.BUSINESS for f in fares)
    # Includes both forward-looking and historical observations.
    assert any(f.scraped_at < f.departure_at for f in fares)
    assert any(f.scraped_at > f.departure_at for f in fares)
