"""Deterministic unit tests for index_engine Phase 4 (overall index).

These tests validate:
- Laspeyres (weighted arithmetic mean of relatives) scaled to base=100
- Weighted Jevons (weighted geometric mean of relatives) scaled to base=100
- Deterministic validation behavior for empty/invalid inputs

They do *not* re-test Phase 2 aggregation or Phase 3 weights logic.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from index_engine.aggregation import ItemPriceRelatives
from index_engine.api_index import compute_overall_airfare_index
from models.fare import CabinClass, TripType
from models.index import IndexResult

ItemKey = tuple[str, str, CabinClass, TripType]


def _item(
    origin: str,
    destination: str,
    cabin_class: CabinClass,
    trip_type: TripType,
) -> ItemKey:
    return (origin, destination, cabin_class, trip_type)


def _make_result(relatives: dict[ItemKey, float]) -> ItemPriceRelatives:
    return ItemPriceRelatives(
        base_period=date(2026, 8, 27),
        current_period=date(2026, 8, 28),
        item_price_relatives=relatives,
    )


def _assert_finite_overall(result: IndexResult) -> None:
    assert math.isfinite(result.overall_laspeyres_index)
    assert math.isfinite(result.overall_jevons_index)
    assert result.overall_laspeyres_index > 0.0
    assert result.overall_jevons_index > 0.0


def test_base_period_unchanged_prices_returns_100() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.0, b: 1.0}
    weights = {a: 0.5, b: 0.5}

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    assert result.overall_laspeyres_index == pytest.approx(100.0)
    assert result.overall_jevons_index == pytest.approx(100.0)
    _assert_finite_overall(result)


def test_uniform_10_percent_increase_returns_110() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1, b: 1.1}
    weights = {a: 0.5, b: 0.5}

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    assert result.overall_laspeyres_index == pytest.approx(110.0)
    assert result.overall_jevons_index == pytest.approx(110.0)


def test_uniform_10_percent_decrease_returns_90() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 0.9, b: 0.9}
    weights = {a: 0.5, b: 0.5}

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    assert result.overall_laspeyres_index == pytest.approx(90.0)
    assert result.overall_jevons_index == pytest.approx(90.0)


def test_two_item_weighted_arithmetic_example_laspeyres_exact() -> None:
    # w1=1/4, w2=3/4; r1=5/4, r2=3/4
    # L = 100 * (w1*r1 + w2*r2)
    #   = 100 * (5/16 + 9/16) = 100 * (14/16) = 87.5
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.25, b: 0.75}
    weights = {a: 0.25, b: 0.75}

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    assert result.overall_laspeyres_index == 87.5


def test_two_item_weighted_geometric_example_jevons_exact_formula() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.25, b: 0.75}
    weights = {a: 0.25, b: 0.75}

    expected = 100.0 * math.exp(
        weights[a] * math.log(relatives[a]) + weights[b] * math.log(relatives[b])
    )

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    assert result.overall_jevons_index == pytest.approx(expected)


def test_different_item_relatives_laspeyres_and_jevons_differ() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.2, b: 0.9}
    weights = {a: 0.5, b: 0.5}

    result = compute_overall_airfare_index(_make_result(relatives), weights)

    expected_l = 100.0 * (0.5 * 1.2 + 0.5 * 0.9)
    expected_j = 100.0 * math.sqrt(1.2 * 0.9)

    assert result.overall_laspeyres_index == pytest.approx(expected_l)
    assert result.overall_jevons_index == pytest.approx(expected_j)
    assert result.overall_laspeyres_index != result.overall_jevons_index


def test_weights_sum_to_1_is_required() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1, b: 0.9}
    bad_weights = {a: 0.6, b: 0.6}  # sums to 1.2

    with pytest.raises(ValueError, match=r"weights must sum to 1\.0"):
        compute_overall_airfare_index(_make_result(relatives), bad_weights)


def test_deterministic_repeated_execution() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.05, b: 0.95}
    weights = {a: 0.5, b: 0.5}

    r1 = compute_overall_airfare_index(_make_result(relatives), weights)
    r2 = compute_overall_airfare_index(_make_result(relatives), weights)

    assert r1 == r2


def test_relatives_item_missing_in_weights_is_rejected() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1, b: 0.9}
    weights = {a: 1.0}  # missing b

    with pytest.raises(ValueError, match="keys must match"):
        compute_overall_airfare_index(_make_result(relatives), weights)


def test_weights_item_missing_in_relatives_is_rejected() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1}
    weights = {a: 0.5, b: 0.5}  # b not in relatives

    with pytest.raises(ValueError, match="keys must match"):
        compute_overall_airfare_index(_make_result(relatives), weights)


def test_empty_eligible_basket_returns_100_indices() -> None:
    result = compute_overall_airfare_index(
        _make_result({}),
        {},
    )

    assert result.overall_laspeyres_index == pytest.approx(100.0)
    assert result.overall_jevons_index == pytest.approx(100.0)
    assert result.item_indices == []


def test_empty_weights_mapping_raises_when_relatives_non_empty() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    with pytest.raises(ValueError, match="weights must be non-empty"):
        compute_overall_airfare_index(_make_result({a: 1.1}), {})


def test_zero_total_weight_raises() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1}
    bad_weights = {a: 0.0}

    with pytest.raises(ValueError, match="sum of weights must be > 0"):
        compute_overall_airfare_index(_make_result(relatives), bad_weights)


def test_non_positive_relative_raises() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    with pytest.raises(ValueError, match="relative value must be > 0"):
        compute_overall_airfare_index(_make_result({a: 0.0}), {a: 1.0})

    with pytest.raises(ValueError, match="relative value must be > 0"):
        compute_overall_airfare_index(_make_result({a: -1.0}), {a: 1.0})


def test_non_finite_relative_raises() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    with pytest.raises(ValueError, match="relative value must be a finite float"):
        compute_overall_airfare_index(
            _make_result({a: float("nan")}),
            {a: 1.0},
        )

    with pytest.raises(ValueError, match="relative value must be a finite float"):
        compute_overall_airfare_index(
            _make_result({a: float("inf")}),
            {a: 1.0},
        )


def test_invalid_weights_negative_raises() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1}
    bad_weights = {a: -0.1}

    with pytest.raises(ValueError, match="weight value must be >= 0"):
        compute_overall_airfare_index(_make_result(relatives), bad_weights)


def test_invalid_weights_non_finite_raises() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.1}

    with pytest.raises(ValueError, match="weight value must be a finite float"):
        compute_overall_airfare_index(
            _make_result(relatives),
            {a: float("nan")},
        )

    with pytest.raises(ValueError, match="weight value must be a finite float"):
        compute_overall_airfare_index(
            _make_result(relatives),
            {a: float("inf")},
        )


def test_no_nan_or_infinity_reaches_result() -> None:
    a = _item("DEL", "BOM", CabinClass.ECONOMY, TripType.ONE_WAY)
    b = _item("DEL", "HYD", CabinClass.ECONOMY, TripType.ONE_WAY)

    relatives = {a: 1.03, b: 0.97}
    weights = {a: 0.5, b: 0.5}

    result = compute_overall_airfare_index(_make_result(relatives), weights)
    _assert_finite_overall(result)
