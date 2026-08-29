"""Deterministic unit tests for pipeline.deduplicator."""

from pipeline.deduplicator import dedup
from tests.unit.test_fare_model import _valid_fare


def test_dedup_keeps_unique_fares():
    fares = [_valid_fare(), _valid_fare(price_inr=6000.0)]
    result = dedup(fares)
    assert len(result) == 2


def test_dedup_removes_exact_duplicates():
    fare = _valid_fare()
    result = dedup([fare, fare, fare])
    assert len(result) == 1
    # The surviving fare is the first occurrence.
    assert result[0] is fare


def test_dedup_distinguishes_by_route():
    fare_a = _valid_fare(route=_valid_fare().route)
    from models.route import Route

    fare_b = _valid_fare()
    fare_b = fare_b.model_copy(update={"route": Route(origin="CCU", destination="BLR")})
    result = dedup([fare_a, fare_b])
    assert len(result) == 2


def test_dedup_distinguishes_by_airline_code():
    fare_a = _valid_fare(airline_code="6E")
    fare_b = _valid_fare(airline_code="SG")
    assert len(dedup([fare_a, fare_b])) == 2


def test_dedup_distinguishes_by_cabin_class():
    fare_a = _valid_fare(cabin_class=_valid_fare().cabin_class)
    from models.fare import CabinClass

    fare_b = _valid_fare(cabin_class=CabinClass.BUSINESS)
    assert len(dedup([fare_a, fare_b])) == 2


def test_dedup_distinguishes_by_trip_type():
    from models.fare import TripType

    fare_a = _valid_fare(trip_type=TripType.ONE_WAY)
    fare_b = _valid_fare(trip_type=TripType.ROUND_TRIP)
    assert len(dedup([fare_a, fare_b])) == 2


def test_dedup_distinguishes_by_departure_time():
    from datetime import datetime, timezone

    fare_a = _valid_fare(departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc))
    fare_b = _valid_fare(departure_at=datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc))
    assert len(dedup([fare_a, fare_b])) == 2


def test_dedup_ignores_provenance_differences():
    """Same business observation from two different sources is deduplicated."""
    from models.fare import RawFareSource, SourceType

    src_a = RawFareSource(
        source_name="IndiGo",
        source_type=SourceType.AIRLINE,
        raw_price=5000.0,
        raw_currency="INR",
        raw_cabin_label="Economy",
    )
    src_b = RawFareSource(
        source_name="MakeMyTrip",
        source_type=SourceType.OTA,
        raw_price=5500.0,
        raw_currency="INR",
        raw_cabin_label="Economy",
    )

    from datetime import datetime, timezone

    from models.fare import CabinClass, TripType
    from models.route import Route

    common = dict(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
    )
    from models.fare import Fare

    fare_a = Fare(source=src_a, **common)
    fare_b = Fare(source=src_b, **common)

    assert len(dedup([fare_a, fare_b])) == 1


def test_dedup_empty_input():
    assert dedup([]) == []
