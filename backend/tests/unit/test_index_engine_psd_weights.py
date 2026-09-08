"""Unit tests for PSD (DGCA Passenger Traffic Data) route weighting."""

from __future__ import annotations

import pytest

from backend.index_engine.weights import (
    DEFAULT_PSD_ROUTE_WEIGHTS,
    compute_psd_base_basket_weights,
)
from backend.models.fare import CabinClass, TripType

ItemKey = tuple[str, str, CabinClass, TripType]


def _item(origin: str, destination: str) -> ItemKey:
    return (origin, destination, CabinClass.ECONOMY, TripType.ONE_WAY)


def test_empty_psd_returns_empty():
    assert compute_psd_base_basket_weights({}) == {}


def test_single_item_psd_weight_is_one():
    item = _item("DEL", "BOM")
    weights = compute_psd_base_basket_weights({item: 1.05})
    assert weights == {item: 1.0}


def test_psd_weights_reflect_traffic_shares():
    item_del_bom = _item("DEL", "BOM")  # 0.12 in DEFAULT_PSD
    item_blr_hyd = _item("BLR", "HYD")  # 0.045 in DEFAULT_PSD

    relatives = {item_del_bom: 1.02, item_blr_hyd: 1.10}
    weights = compute_psd_base_basket_weights(relatives)

    assert sum(weights.values()) == pytest.approx(1.0)
    # DEL-BOM should have higher weight than BLR-HYD
    assert weights[item_del_bom] > weights[item_blr_hyd]
    # Ratio should match traffic share ratio 0.12 / 0.045
    ratio = weights[item_del_bom] / weights[item_blr_hyd]
    assert ratio == pytest.approx(0.12 / 0.045, rel=1e-3)


def test_custom_route_weights_override():
    item_a = _item("DEL", "BOM")
    item_b = _item("DEL", "BLR")

    custom_weights = {("DEL", "BOM"): 0.8, ("DEL", "BLR"): 0.2}
    weights = compute_psd_base_basket_weights(
        {item_a: 1.0, item_b: 1.0},
        route_weights=custom_weights,
    )

    assert weights[item_a] == pytest.approx(0.8)
    assert weights[item_b] == pytest.approx(0.2)
    assert sum(weights.values()) == pytest.approx(1.0)
