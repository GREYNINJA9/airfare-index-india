"""Deterministic unit tests for the index_engine weight layer (Phase 3)."""

from __future__ import annotations

import math

import pytest

from index_engine.weights import compute_uniform_base_basket_weights
from models.fare import CabinClass, TripType

ItemKey = tuple[str, str, CabinClass, TripType]


def _item(
    origin: str,
    destination: str,
    cabin_class: CabinClass,
    trip_type: TripType,
) -> ItemKey:
    return (origin, destination, cabin_class, trip_type)


def _sorted_items(keys: list[ItemKey]) -> list[ItemKey]:
    # Must match index_engine.weights._item_sort_key ordering.
    return sorted(keys, key=lambda it: (it[0], it[1], it[2].value, it[3].value))


def _expected_uniform_weights(keys: list[ItemKey]) -> dict[ItemKey, float]:
    items_sorted = _sorted_items(keys)
    n = len(items_sorted)
    if n == 0:
        return {}

    equal = 1.0 / n
    weights: dict[ItemKey, float] = {}
    sum_prev = 0.0

    for i, item in enumerate(items_sorted):
        if i < n - 1:
            weights[item] = equal
            sum_prev += equal
        else:
            weights[item] = 1.0 - sum_prev

    return weights


def test_empty_input_returns_empty_dict() -> None:
    assert compute_uniform_base_basket_weights({}) == {}


def test_invalid_item_price_relatives_type_raises() -> None:
    with pytest.raises(TypeError):
        compute_uniform_base_basket_weights(None)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        compute_uniform_base_basket_weights([])  # type: ignore[arg-type]


def test_invalid_item_key_raises() -> None:
    bad_mapping = {
        # wrong shape (len != 4)
        ("DEL", "BOM"): 1.0,
    }
    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights(bad_mapping)  # type: ignore[arg-type]


def test_invalid_relative_value_raises() -> None:
    item = _item(
        "DEL",
        "BOM",
        CabinClass.ECONOMY,
        TripType.ONE_WAY,
    )

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: 0.0})

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: -1.0})

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: float("nan")})

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: float("inf")})


def test_single_item_basket_weight_is_one() -> None:
    item = _item(
        "DEL",
        "BOM",
        CabinClass.ECONOMY,
        TripType.ONE_WAY,
    )

    weights = compute_uniform_base_basket_weights({item: 1.0})
    assert weights == {item: 1.0}
    assert sum(weights.values()) == 1.0


def test_two_item_basket_uniform_weights() -> None:
    item_a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    weights = compute_uniform_base_basket_weights({item_a: 1.1, item_b: 0.9})
    assert weights == {item_a: 0.5, item_b: 0.5}

    total = sum(weights.values())
    assert total == 1.0


def test_multiple_items_normalize_to_exactly_one_point_zero() -> None:
    item_a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = _item("BOM", "DEL", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_c = _item("CCU", "BLR", CabinClass.BUSINESS, TripType.ROUND_TRIP)

    # Values do not affect uniform weighting; they just must be valid.
    mapping = {item_a: 2.0, item_b: 3.0, item_c: 4.0}

    weights = compute_uniform_base_basket_weights(mapping)

    assert set(weights.keys()) == {item_a, item_b, item_c}
    assert sum(weights.values()) == 1.0

    expected = _expected_uniform_weights([item_a, item_b, item_c])
    assert weights == expected


def test_items_outside_base_basket_excluded_by_input_eligibility() -> None:
    # Simulate aggregation output that includes only base-basket items that
    # were observed in the current period.
    base_basket_item_1 = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    base_basket_item_2 = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    # Only item 1 is present in item_price_relatives (item 2 missing => excluded).
    weights = compute_uniform_base_basket_weights({base_basket_item_1: 1.3})
    assert weights == {base_basket_item_1: 1.0}
    assert base_basket_item_2 not in weights


def test_missing_current_item_exclude_and_renormalize() -> None:
    item_a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    # Both items exist in base basket, but only item_a is observed in current.
    weights = compute_uniform_base_basket_weights({item_a: 1.0})
    assert weights == {item_a: 1.0}
    assert sum(weights.values()) == 1.0

    # If both are present, weights revert to uniform across eligible items.
    weights2 = compute_uniform_base_basket_weights({item_a: 1.0, item_b: 1.0})
    assert weights2 == {item_a: 0.5, item_b: 0.5}


def test_zero_total_weight_protection_empty_input() -> None:
    weights = compute_uniform_base_basket_weights({})
    assert weights == {}


def test_deterministic_repeated_execution_and_insertion_order_irrelevance() -> None:
    item_a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_b = _item("BOM", "DEL", CabinClass.ECONOMY, TripType.ONE_WAY)
    item_c = _item("CCU", "BLR", CabinClass.BUSINESS, TripType.ROUND_TRIP)

    mapping_1 = {item_a: 2.0, item_b: 3.0, item_c: 4.0}
    mapping_2 = {item_c: 4.0, item_a: 2.0, item_b: 3.0}

    w1 = compute_uniform_base_basket_weights(mapping_1)
    w2 = compute_uniform_base_basket_weights(mapping_1)
    w3 = compute_uniform_base_basket_weights(mapping_2)

    assert w1 == w2
    assert w1 == w3


def test_relative_value_must_be_finite_float() -> None:
    item = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: math.nan})

    with pytest.raises(ValueError):
        compute_uniform_base_basket_weights({item: math.inf})
