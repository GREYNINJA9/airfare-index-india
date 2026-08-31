"""Deterministic unit tests for the index result contracts.

These tests validate that the index engine output schema:
- rejects invalid fields
- enforces finite numeric values
- supports JSON round-trips

No index_engine math is executed here.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from models.fare import CabinClass, TripType
from models.index import IndexMethodologyMetadata, IndexResult, ItemIndex, ItemKey


def test_item_key_validation() -> None:
    item = ItemKey(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )
    assert item.origin == "DEL"
    assert item.destination == "BOM"


@pytest.mark.parametrize(
    "bad_origin",
    ["DE", "DELA", "123", "del", ""],
)
def test_item_key_rejects_bad_origin(bad_origin: str) -> None:
    with pytest.raises(ValidationError):
        ItemKey(
            origin=bad_origin,
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
        )


def test_index_relative_rejects_nan() -> None:
    item = ItemKey(
        origin="DEL",
        destination="BOM",
        cabin_class=CabinClass.ECONOMY,
        trip_type=TripType.ONE_WAY,
    )

    with pytest.raises(ValidationError):
        ItemIndex(
            item=item,
            index_relative=float("nan"),
        )

    with pytest.raises(ValidationError):
        ItemIndex(
            item=item,
            index_relative=float("inf"),
        )


def test_index_result_valid_and_json_roundtrip() -> None:
    methodology = IndexMethodologyMetadata()
    result = IndexResult(
        base_period=date(2026, 8, 27),
        current_period=date(2026, 8, 28),
        overall_laspeyres_index=1.025,
        overall_jevons_index=1.0223,
        item_indices=[
            ItemIndex(
                item=ItemKey(
                    origin="DEL",
                    destination="BOM",
                    cabin_class=CabinClass.ECONOMY,
                    trip_type=TripType.ONE_WAY,
                ),
                index_relative=1.1,
            )
        ],
        methodology=methodology,
    )

    dumped = result.model_dump_json()
    restored = IndexResult.model_validate_json(dumped)
    assert restored == result


def test_index_result_forbids_extra_fields() -> None:
    methodology = IndexMethodologyMetadata()
    with pytest.raises(ValidationError):
        IndexResult(
            base_period=date(2026, 8, 27),
            current_period=date(2026, 8, 28),
            overall_laspeyres_index=1.0,
            overall_jevons_index=1.0,
            item_indices=[],
            methodology=methodology,
            unexpected=123,
        )
