"""Integration: SQLite fares → repository → index engine → persist IndexResult.

This test validates the deterministic end-to-end chain without re-implementing
any index math:

Synthetic Fare objects
↓
SQLite (fares table)
↓
repository.get_fares (reconstruct validated Fare models)
↓
index_engine aggregation
↓
index_engine weights
↓
index_engine Phase-4 computation
↓
repository.insert_index_result
↓
repository.get_index_result
↓
value equality verification
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from database.connection import close_connection, reset_connection
from database.repository import (
    get_fare_by_offer_id,
    get_fares,
    get_index_result,
    insert_fare,
    insert_index_result,
)
from database.schema import init_schema
from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_uniform_base_basket_weights
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.index import IndexMethodologyMetadata, IndexResult
from models.route import Route


def _source(*, name: str, price_inr: float, raw_offer_id: str) -> RawFareSource:
    return RawFareSource.model_validate(
        {
            "source_name": name,
            "source_type": SourceType.OTA
            if name.endswith("OTA")
            else SourceType.AIRLINE,
            "raw_price": float(price_inr),
            "raw_currency": "INR",
            "raw_cabin_label": "Economy",
            "source_url": "https://example.com/fare",
            "raw_offer_id": raw_offer_id,
        }
    )


def _fare(
    *,
    origin: str,
    destination: str,
    cabin_class: CabinClass,
    trip_type: TripType,
    scraped_at: datetime,
    price_inr: float,
    airline_code: str,
    source_name: str,
    raw_offer_id: str,
) -> Fare:
    departure_at = scraped_at + timedelta(days=20)
    route = Route(origin=origin, destination=destination)

    return Fare.model_validate(
        {
            "route": route.model_dump(),
            "airline_code": airline_code,
            "price_inr": float(price_inr),
            "cabin_class": cabin_class,
            "departure_at": departure_at,
            "scraped_at": scraped_at,
            "trip_type": trip_type,
            "source": _source(
                name=source_name,
                price_inr=price_inr,
                raw_offer_id=raw_offer_id,
            ),
        }
    )


@pytest.fixture()
def db():
    conn = reset_connection(path=":memory:")
    init_schema(conn)
    try:
        yield conn
    finally:
        close_connection()


def test_sqlite_to_fare_reconstruction_empty_db_raises_on_aggregation(db) -> None:
    fares = get_fares(db)
    assert fares == []

    current_period = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc).date()

    with pytest.raises(ValueError, match="fares must be non-empty"):
        aggregate_item_price_relatives(fares, current_period=current_period)


def test_sqlite_to_fare_reconstruction_route_enum_datetime_ordering(db) -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fare_d1 = _fare(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
        scraped_at=d1,
        price_inr=110.0,
        airline_code="6E",
        source_name="S1",
        raw_offer_id="offer-d1",
    )

    # Insert in reverse order to validate deterministic scraped_at ordering.
    fare_d0 = _fare(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
        scraped_at=d0,
        price_inr=100.0,
        airline_code="6E",
        source_name="S0",
        raw_offer_id="offer-d0",
    )

    insert_fare(db, fare_d1)
    insert_fare(db, fare_d0)

    # Direct lookup by offer id still returns dicts (existing behavior).
    row = get_fare_by_offer_id(db, "offer-d0")
    assert row is not None
    assert row["price_inr"] == 100.0

    fares = get_fares(db)
    assert [f.price_inr for f in fares] == [100.0, 110.0]
    assert len(fares) == 2

    # Route reconstructed correctly.
    assert fares[0].route.origin == "DEL"
    assert fares[0].route.destination == "BOM"

    # Enums reconstructed correctly.
    assert fares[0].cabin_class == CabinClass.ECONOMY
    assert fares[0].trip_type == TripType.ONE_WAY

    # Timezone-aware datetimes reconstructed correctly.
    assert fares[0].scraped_at.tzinfo is not None
    assert fares[0].scraped_at.tzinfo.utcoffset(fares[0].scraped_at) is not None
    assert fares[0].departure_at.tzinfo is not None
    assert fares[0].departure_at.tzinfo.utcoffset(fares[0].departure_at) is not None

    # Exact datetime round-trip.
    assert fares[0].scraped_at == d0
    assert fares[0].departure_at == d0 + timedelta(days=20)
    assert fares[1].scraped_at == d1
    assert fares[1].departure_at == d1 + timedelta(days=20)


def test_end_to_end_index_db_integration_round_trip(db) -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    item_a = ("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = ("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    # One quote per item/day => median equals the quote itself.
    fares: list[Fare] = [
        _fare(
            origin=item_a[0],
            destination=item_a[1],
            cabin_class=item_a[2],
            trip_type=item_a[3],
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
            raw_offer_id="A-d0",
        ),
        _fare(
            origin=item_b[0],
            destination=item_b[1],
            cabin_class=item_b[2],
            trip_type=item_b[3],
            scraped_at=d0,
            price_inr=80.0,
            airline_code="6E",
            source_name="S2",
            raw_offer_id="B-d0",
        ),
        _fare(
            origin=item_a[0],
            destination=item_a[1],
            cabin_class=item_a[2],
            trip_type=item_a[3],
            scraped_at=d1,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
            raw_offer_id="A-d1",
        ),
        _fare(
            origin=item_b[0],
            destination=item_b[1],
            cabin_class=item_b[2],
            trip_type=item_b[3],
            scraped_at=d1,
            price_inr=90.0,
            airline_code="6E",
            source_name="S2",
            raw_offer_id="B-d1",
        ),
    ]

    # Insert them into SQLite.
    for fare in fares:
        assert insert_fare(db, fare) > 0

    # Retrieve them via repository.get_fares (validated Fare objects).
    retrieved = get_fares(db)
    assert len(retrieved) == len(fares)

    # Compute expected index result from the *original* Fare objects.
    expected_relatives = aggregate_item_price_relatives(
        fares,
        current_period=d1.date(),
    )
    expected_weights = compute_uniform_base_basket_weights(
        expected_relatives.item_price_relatives
    )
    expected_result = compute_overall_airfare_index(
        expected_relatives,
        expected_weights,
    )

    # Compute actual index result from DB-retrieved fares.
    actual_relatives = aggregate_item_price_relatives(
        retrieved,
        current_period=d1.date(),
    )
    actual_weights = compute_uniform_base_basket_weights(
        actual_relatives.item_price_relatives
    )
    actual_result = compute_overall_airfare_index(
        actual_relatives,
        actual_weights,
    )

    assert isinstance(actual_result, IndexResult)
    assert actual_result == expected_result

    # Persist IndexResult.
    inserted_id = insert_index_result(db, actual_result)
    assert inserted_id > 0

    # Retrieve persisted IndexResult.
    persisted = get_index_result(
        db,
        base_period=actual_result.base_period,
        current_period=actual_result.current_period,
    )
    assert persisted is not None
    assert persisted == actual_result

    # Explicit value preservation checks.
    assert persisted.base_period == d0.date()
    assert persisted.current_period == d1.date()
    assert math.isclose(
        persisted.overall_laspeyres_index,
        expected_result.overall_laspeyres_index,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        persisted.overall_jevons_index,
        expected_result.overall_jevons_index,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    # Methodology metadata preservation.
    assert persisted.methodology == IndexMethodologyMetadata()
    assert persisted.methodology.methodology_version == "mvp-locked-1"

    # Item-level indices preserved.
    assert persisted.item_indices == actual_result.item_indices
    assert len(persisted.item_indices) == 2

    # Repeated computation deterministic.
    repeated_relatives = aggregate_item_price_relatives(
        retrieved,
        current_period=d1.date(),
    )
    repeated_weights = compute_uniform_base_basket_weights(
        repeated_relatives.item_price_relatives
    )
    repeated_result = compute_overall_airfare_index(
        repeated_relatives,
        repeated_weights,
    )
    assert repeated_result == actual_result
