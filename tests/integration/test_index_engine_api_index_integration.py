"""Integration test: Fare → aggregation → weights → Phase 4 overall index.

This validates the integration contract using synthetic data only.

Chain:
synthetic Fare objects
↓
index_engine/aggregation.aggregate_item_price_relatives
↓
index_engine/weights.compute_uniform_base_basket_weights
↓
index_engine/api_index.compute_overall_airfare_index
↓
models/index.IndexResult
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_uniform_base_basket_weights
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.index import IndexResult
from models.route import Route


def _source(*, name: str, price_inr: float) -> RawFareSource:
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
            "raw_offer_id": f"{name}-{price_inr}",
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
            "source": _source(name=source_name, price_inr=price_inr),
        }
    )


def test_fare_to_overall_index_integration_increase_gt_100() -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    # Two items in base basket (and observed in current period).
    # Relative price relatives:
    # item_a: r_a = 110 / 100 = 1.10
    # item_b: r_b = 90 / 80 = 1.125
    item_a = ("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = ("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    fares = [
        _fare(
            origin=item_a[0],
            destination=item_a[1],
            cabin_class=item_a[2],
            trip_type=item_a[3],
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
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
        ),
    ]

    price_relatives_result = aggregate_item_price_relatives(
        fares,
        current_period=d1.date(),
    )

    # Phase 3 weights are uniform over eligible items.
    weights = compute_uniform_base_basket_weights(
        price_relatives_result.item_price_relatives
    )

    result = compute_overall_airfare_index(
        price_relatives_result,
        weights,
    )

    assert isinstance(result, IndexResult)
    assert result.base_period == d0.date()
    assert result.current_period == d1.date()
    assert len(result.item_indices) == 2

    # At least one scenario where fares increase from base.
    assert result.overall_laspeyres_index > 100.0
    assert result.overall_jevons_index > 100.0
