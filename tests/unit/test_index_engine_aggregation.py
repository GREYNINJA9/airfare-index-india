"""Deterministic unit tests for the index_engine aggregation layer.

These tests cover only the aggregation responsibilities locked for Phase 2:
- UTC daily bucketing (from Fare.scraped_at)
- item identity: (origin, destination, cabin_class, trip_type)
- median effective item-day price
- base-day selection (complete days, else max coverage w/ earliest tie)
- relative price computation P_i(d)/P_i(d0)
- missing current items (exclude + no carry forward)
- new items (exclude until base rebasing; base basket depends on base day)

No network calls. No randomness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from index_engine.aggregation import aggregate_item_price_relatives
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
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
    # departure_at is supporting metadata; it is not part of the MVP item key.
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
            "source": RawFareSource.model_validate(
                {
                    "source_name": source_name,
                    "source_type": SourceType.OTA
                    if "OTA" in source_name
                    else SourceType.AIRLINE,
                    "raw_price": float(price_inr),
                    "raw_currency": "INR",
                    "raw_cabin_label": "Economy",
                    "source_url": "https://example.com/fare",
                    "raw_offer_id": f"{source_name}-{origin}-{destination}",
                }
            ),
        }
    )


def _item_key(
    *,
    origin: str,
    destination: str,
    cabin_class: CabinClass,
    trip_type: TripType,
):
    return (origin, destination, cabin_class, trip_type)


def test_empty_dataset_raises() -> None:
    with pytest.raises(ValueError):
        aggregate_item_price_relatives(
            [], current_period=datetime(2026, 8, 28, tzinfo=timezone.utc).date()
        )


def test_invalid_input_type_raises() -> None:
    with pytest.raises(TypeError):
        aggregate_item_price_relatives(
            None,
            current_period=datetime(2026, 8, 28, tzinfo=timezone.utc).date(),
        )  # type: ignore[arg-type]


def test_utc_daily_bucketing_uses_utc_date() -> None:
    # scraped_at = 2026-08-27 01:00 +12:00 => 2026-08-26 13:00 UTC
    tz_plus_12 = timezone(timedelta(hours=12))
    scraped_base = datetime(2026, 8, 27, 1, 0, tzinfo=tz_plus_12)
    scraped_current = datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=scraped_base,
            price_inr=100.0,
            airline_code="6E",
            source_name="Src1",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=scraped_current,
            price_inr=110.0,
            airline_code="6E",
            source_name="Src1",
        ),
    ]

    result = aggregate_item_price_relatives(
        fares,
        current_period=datetime(2026, 8, 27, tzinfo=timezone.utc).date(),
    )

    assert result.base_period == datetime(2026, 8, 26, tzinfo=timezone.utc).date()
    expected_relative = 110.0 / 100.0
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): expected_relative
    }


def test_item_identity_origin_destination_cabin_trip() -> None:
    scraped_day = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=scraped_day,
            price_inr=100.0,
            airline_code="6E",
            source_name="Src1",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.BUSINESS,
            trip_type=TripType.ONE_WAY,
            scraped_at=scraped_day,
            price_inr=200.0,
            airline_code="6E",
            source_name="Src1",
        ),
    ]

    result = aggregate_item_price_relatives(
        fares,
        current_period=datetime(2026, 8, 27, tzinfo=timezone.utc).date(),
    )

    # Base day is the first complete day; with this dataset, item universe has
    # 2 items and day is complete because both items are present.
    assert result.base_period == datetime(2026, 8, 27, tzinfo=timezone.utc).date()
    assert set(result.item_price_relatives.keys()) == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ),
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.BUSINESS,
            trip_type=TripType.ONE_WAY,
        ),
    }
    assert (
        result.item_price_relatives[
            _item_key(
                origin="DEL",
                destination="BOM",
                cabin_class=CabinClass.ECONOMY,
                trip_type=TripType.ONE_WAY,
            )
        ]
        == 1.0
    )


def test_median_odd_count() -> None:
    base_day = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    current_day = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day,
            price_inr=98.0,
            airline_code="6E",
            source_name="A",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(hours=1),
            price_inr=100.0,
            airline_code="6E",
            source_name="B",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(hours=2),
            price_inr=102.0,
            airline_code="6E",
            source_name="C",
        ),
        # current: median of [108,110,112] = 110
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day,
            price_inr=110.0,
            airline_code="6E",
            source_name="A",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(hours=1),
            price_inr=108.0,
            airline_code="6E",
            source_name="B",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(hours=2),
            price_inr=112.0,
            airline_code="6E",
            source_name="C",
        ),
    ]

    result = aggregate_item_price_relatives(
        fares,
        current_period=current_day.date(),
    )

    assert result.base_period == base_day.date()
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): 110.0 / 100.0
    }


def test_median_even_count() -> None:
    base_day = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    current_day = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        # base median of [100,102] = 101
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day,
            price_inr=100.0,
            airline_code="6E",
            source_name="Src1",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(hours=1),
            price_inr=102.0,
            airline_code="6E",
            source_name="Src2",
        ),
        # current median of [110,112] = 111
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day,
            price_inr=110.0,
            airline_code="6E",
            source_name="Src1",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(hours=1),
            price_inr=112.0,
            airline_code="6E",
            source_name="Src2",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=current_day.date())

    expected = 111.0 / 101.0
    assert result.base_period == base_day.date()
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): pytest.approx(expected)
    }


def test_multiple_quotes_multiple_sources_median_is_single_value() -> None:
    base_day = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    current_day = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        # base: 4 quotes => median average of two middle values.
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day,
            price_inr=100.0,
            airline_code="6E",
            source_name="A_OTA",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(minutes=10),
            price_inr=104.0,
            airline_code="6E",
            source_name="B_OTA",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(minutes=20),
            price_inr=108.0,
            airline_code="6E",
            source_name="C",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=base_day + timedelta(minutes=30),
            price_inr=96.0,
            airline_code="6E",
            source_name="D",
        ),
        # sorted [96,100,104,108] => median (100+104)/2=102
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day,
            price_inr=110.0,
            airline_code="6E",
            source_name="A_OTA",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(minutes=10),
            price_inr=114.0,
            airline_code="6E",
            source_name="B_OTA",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(minutes=20),
            price_inr=118.0,
            airline_code="6E",
            source_name="C",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=current_day + timedelta(minutes=30),
            price_inr=106.0,
            airline_code="6E",
            source_name="D",
        ),
        # sorted [106,110,114,118] => median (110+114)/2=112
    ]

    result = aggregate_item_price_relatives(fares, current_period=current_day.date())
    expected_relative = 112.0 / 102.0
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): pytest.approx(expected_relative)
    }


def test_earliest_complete_base_day_selection() -> None:
    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)

    item1 = ("DEL", "BOM")
    item2 = ("BOM", "DEL")

    fares = [
        # d1 only item1
        _fare(
            origin=item1[0],
            destination=item1[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        # d2 both items => complete day, earliest complete
        _fare(
            origin=item1[0],
            destination=item1[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin=item2[0],
            destination=item2[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d3 both items
        _fare(
            origin=item1[0],
            destination=item1[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=120.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin=item2[0],
            destination=item2[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=210.0,
            airline_code="6E",
            source_name="S2",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d3.date())

    assert result.base_period == d2.date()
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): 120.0 / 110.0,
        _item_key(
            origin="BOM",
            destination="DEL",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): 210.0 / 200.0,
    }


def test_max_coverage_fallback_base_day_and_tie_break_earliest() -> None:
    # Universe has 3 items; no day contains all 3.
    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)  # items {1,2}
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)  # items {1,3}
    d3 = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)  # items {2,3}

    fares = [
        # d1: item1
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        # d1: item2
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d2: item1
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
        ),
        # d2: item3
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=300.0,
            airline_code="6E",
            source_name="S3",
        ),
        # d3: item2
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=210.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d3: item3
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=310.0,
            airline_code="6E",
            source_name="S3",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d3.date())

    # Each day covers 2 of 3 items => tie -> earliest date d1.
    assert result.base_period == d1.date()

    # Base basket contains items observed on d1: item1 and item2.
    # Current day d3 observes item2 and item3; item1 missing => excluded.
    # item3 is a new item for base basket => excluded.
    assert result.item_price_relatives.keys() == {
        _item_key(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        )
    }

    assert (
        result.item_price_relatives[
            _item_key(
                origin="DEL",
                destination="HYD",
                cabin_class=CabinClass.ECONOMY,
                trip_type=TripType.ONE_WAY,
            )
        ]
        == 210.0 / 200.0
    )


def test_missing_current_item_excluded_no_carry_forward() -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        # base day d0: item1 and item2
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # current day d1: only item1
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=120.0,
            airline_code="6E",
            source_name="S1",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d1.date())

    assert result.base_period == d0.date()
    assert result.item_price_relatives == {
        _item_key(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        ): 1.2
    }


def test_new_items_excluded_until_rebased() -> None:
    # Universe has 3 items; base day chosen by coverage does not include item3.
    # Current day contains item2 and item3; item3 should not appear.
    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)  # base day => items {1,2}
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)  # items {1,3}
    d3 = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)  # current => items {2,3}

    fares = [
        # base day d1
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d2 adds item3 but base already chosen to exclude it
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=300.0,
            airline_code="6E",
            source_name="S3",
        ),
        # current day d3: item2 and item3
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=210.0,
            airline_code="6E",
            source_name="S2",
        ),
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=310.0,
            airline_code="6E",
            source_name="S3",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d3.date())

    assert result.base_period == d1.date()

    item2_key = _item_key(
        origin="DEL",
        destination="HYD",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item3_key = _item_key(
        origin="CCU",
        destination="BLR",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )

    # Hardening: verify the “new item” is actually part of global U and is
    # present in the current period, but absent from the selected base
    # basket.
    universe_items = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
    }
    base_day_items = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
        if fare.scraped_at.astimezone(timezone.utc).date() == d1.date()
    }
    current_day_items = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
        if fare.scraped_at.astimezone(timezone.utc).date() == d3.date()
    }

    assert item3_key in universe_items
    assert item3_key in current_day_items
    assert item3_key not in base_day_items
    assert item3_key not in result.item_price_relatives

    # Only item2 is both in base basket and observed in current.
    assert set(result.item_price_relatives.keys()) == {item2_key}


def test_global_item_universe_used_for_base_day_selection() -> None:
    """Hardening: base-day selection uses U from *all* days.

    Dataset construction:
    - Day d1 contains only item A.
    - Day d2 contains items B and D (max distinct coverage).
    - Day d3 contains items C and E.

    Global universe U therefore has 5 items, and no day is complete.

    If (incorrectly) U were constructed only from items seen on the earliest
    day (d1), then U would be {A} and day d1 would appear complete, making
    d1 an eligible complete day. We expect the locked algorithm to *not* do
    that, so the selected base day must be the max-coverage day (d2), not d1.
    """

    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)

    item_a = _item_key(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_b = _item_key(
        origin="BOM",
        destination="DEL",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_d = _item_key(
        origin="DEL",
        destination="HYD",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_c = _item_key(
        origin="CCU",
        destination="BLR",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_e = _item_key(
        origin="MAA",
        destination="HYD",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )

    fares = [
        # d1: only A
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        # d2: B and D (max distinct coverage)
        _fare(
            origin="BOM",
            destination="DEL",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=150.0,
            airline_code="6E",
            source_name="S3",
        ),
        # d3: C and E
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=300.0,
            airline_code="6E",
            source_name="S4",
        ),
        _fare(
            origin="MAA",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=250.0,
            airline_code="6E",
            source_name="S5",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d2.date())

    universe_items = {item_a, item_b, item_c, item_d, item_e}
    assert universe_items == {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
    }

    items_on_d1 = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
        if fare.scraped_at == d1
    }
    assert items_on_d1 == {item_a}
    assert not universe_items.issubset(items_on_d1)

    # Expected base day is the earliest max-coverage day (d2), not d1.
    assert result.base_period == d2.date()

    # Since current_period == base_period == d2, relatives should include
    # exactly items observed on d2: {B, D}.
    assert set(result.item_price_relatives.keys()) == {item_b, item_d}


def test_explicit_base_basket_membership_and_no_rebasing_effect() -> None:
    """Hardening: current-period item C must not enter without base coverage.

    We construct U={A,B,C} with no complete day:
    - base candidate day d1 contains items {A, B}
    - day d2 contains only item {C} (elsewhere in the dataset)
    - current day d3 contains items {A, C}

    Locked base-day selection chooses the earliest max-coverage day.
    Coverage counts are:
    - d1: 2 items
    - d2: 1 item
    - d3: 2 items

    So the selected base day must be d1.

    Since C is not present on the selected base day, C must be excluded
    from current-period relatives even though it appears on the current day.
    """

    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)

    item_a = _item_key(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_b = _item_key(
        origin="DEL",
        destination="HYD",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    item_c = _item_key(
        origin="CCU",
        destination="BLR",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )

    fares = [
        # d1: A and B
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d2: C only
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=300.0,
            airline_code="6E",
            source_name="S3",
        ),
        # d3 (current): A and C
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=110.0,
            airline_code="6E",
            source_name="S4",
        ),
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d3,
            price_inr=310.0,
            airline_code="6E",
            source_name="S5",
        ),
    ]

    result = aggregate_item_price_relatives(fares, current_period=d3.date())

    # Selected base day must be d1.
    assert result.base_period == d1.date()

    # Base basket is defined as items observed on the selected base day.
    base_day_items = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
        if fare.scraped_at.astimezone(timezone.utc).date() == d1.date()
    }
    current_day_items = {
        _item_key(
            origin=fare.route.origin,
            destination=fare.route.destination,
            cabin_class=fare.cabin_class,
            trip_type=fare.trip_type,
        )
        for fare in fares
        if fare.scraped_at.astimezone(timezone.utc).date() == d3.date()
    }

    assert base_day_items == {item_a, item_b}
    assert item_c not in base_day_items

    # C appears on current day but must be excluded from relatives.
    assert item_c in current_day_items
    assert item_c not in result.item_price_relatives

    # Current day lacks item B, so the only relative included should be A.
    assert set(result.item_price_relatives.keys()) == {item_a}


def test_adversarial_no_rebasing_base_period_independent_of_current_period() -> None:
    """Hardening: current_period input must not change base selection.

    We build U={A,B,C} where item C appears only on d2.
    With the locked algorithm, d2 is the earliest complete day for U.

    If base-day selection incorrectly filtered based on the requested
    current_period, then:
    - for current_period=d1, U would drop C and base would become d1
    - for current_period=d2, base would be d2

    The locked implementation must yield base_period=d2 regardless of
    current_period.
    """

    d1 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        # d1: A and B only
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
        ),
        # d2: A, B, C
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=110.0,
            airline_code="6E",
            source_name="S3",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=210.0,
            airline_code="6E",
            source_name="S4",
        ),
        _fare(
            origin="CCU",
            destination="BLR",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d2,
            price_inr=300.0,
            airline_code="6E",
            source_name="S5",
        ),
    ]

    r_earlier = aggregate_item_price_relatives(fares, current_period=d1.date())
    r_later = aggregate_item_price_relatives(fares, current_period=d2.date())

    assert r_earlier.base_period == d2.date()
    assert r_later.base_period == d2.date()

    # Also ensure C appears only when current_period reaches d2.
    item_c = _item_key(
        origin="CCU",
        destination="BLR",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    assert item_c not in r_earlier.item_price_relatives
    assert item_c in r_later.item_price_relatives


def test_no_observed_base_items_current_returns_empty_relatives() -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d_missing = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        )
    ]

    result = aggregate_item_price_relatives(fares, current_period=d_missing.date())

    assert result.base_period == d0.date()
    assert result.item_price_relatives == {}


def test_deterministic_repeated_execution() -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
        ),
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
        ),
    ]

    r1 = aggregate_item_price_relatives(fares, current_period=d1.date())
    r2 = aggregate_item_price_relatives(fares, current_period=d1.date())

    assert r1 == r2
