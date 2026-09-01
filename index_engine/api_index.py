"""Index calculation (Phase 4: overall index).

This module intentionally contains only deterministic, pure calculation logic
that combines price relatives with eligible weights.

Locked MVP methodology (see models/index.py):
- Laspeyres: weighted arithmetic mean of price relatives, scaled to base=100
- Weighted Jevons: weighted geometric mean of price relatives, scaled to base=100

It deliberately does *not* implement elasticity, API endpoints, persistence, or
any scraper/database logic.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from typing import Dict, List

from index_engine.aggregation import ItemPriceRelatives
from index_engine.weights import ItemKey as Phase3ItemKey
from models.fare import CabinClass, TripType
from models.index import IndexMethodologyMetadata, IndexResult, ItemIndex, ItemKey


def _item_sort_key(item: Phase3ItemKey) -> tuple[str, str, str, str]:
    origin, destination, cabin_class, trip_type = item
    if not isinstance(cabin_class, CabinClass):
        raise TypeError("cabin_class must be a CabinClass enum")
    if not isinstance(trip_type, TripType):
        raise TypeError("trip_type must be a TripType enum")
    return (origin, destination, cabin_class.value, trip_type.value)


def _validate_weight_mapping(
    weights: Mapping[Phase3ItemKey, float],
) -> Dict[Phase3ItemKey, float]:
    if not isinstance(weights, Mapping):
        raise TypeError("weights must be a mapping[item_key, float]")

    out: Dict[Phase3ItemKey, float] = {}
    for k, v in weights.items():
        if not isinstance(k, tuple) or len(k) != 4:
            raise ValueError("item key must be a 4-tuple")
        origin, destination, cabin_class, trip_type = k
        if not isinstance(origin, str) or not isinstance(destination, str):
            raise ValueError("item key origin/destination must be strings")
        if not isinstance(cabin_class, CabinClass):
            raise ValueError("item key cabin_class must be a CabinClass enum")
        if not isinstance(trip_type, TripType):
            raise ValueError("item key trip_type must be a TripType enum")

        if not isinstance(v, (int, float)):
            raise ValueError("weight value must be a number")
        w = float(v)
        if not math.isfinite(w):
            raise ValueError("weight value must be a finite float")
        if w < 0.0:
            raise ValueError("weight value must be >= 0")

        out[k] = w

    return out


def _validate_relative_mapping(
    relatives: Mapping[Phase3ItemKey, float],
) -> Dict[Phase3ItemKey, float]:
    if not isinstance(relatives, Mapping):
        raise TypeError("item_price_relatives must be a mapping[item_key, float]")

    out: Dict[Phase3ItemKey, float] = {}
    for k, v in relatives.items():
        if not isinstance(k, tuple) or len(k) != 4:
            raise ValueError("item key must be a 4-tuple")
        origin, destination, cabin_class, trip_type = k
        if not isinstance(origin, str) or not isinstance(destination, str):
            raise ValueError("item key origin/destination must be strings")
        if not isinstance(cabin_class, CabinClass):
            raise ValueError("item key cabin_class must be a CabinClass enum")
        if not isinstance(trip_type, TripType):
            raise ValueError("item key trip_type must be a TripType enum")

        if not isinstance(v, (int, float)):
            raise ValueError("relative value must be a number")
        r = float(v)
        if not math.isfinite(r):
            raise ValueError("relative value must be a finite float")
        if r <= 0.0:
            raise ValueError("relative value must be > 0")

        out[k] = r

    return out


def compute_overall_airfare_index(
    item_price_relatives_result: ItemPriceRelatives,
    weights: Mapping[Phase3ItemKey, float],
) -> IndexResult:
    """Compute overall Laspeyres + weighted Jevons indices.

    Args:
        item_price_relatives_result: Phase 2 aggregation output including
            base_period, current_period, and r_i mapping.
        weights: Phase 3 output mapping ``{item_key: w_i}``.

    Returns:
        IndexResult compatible object.

    Validation / deterministic empty + mismatch behavior:
        - If both relatives and weights are empty, returns base indices 100.0.
        - If one is empty and the other is not: raises ValueError.
        - If keys differ between relatives and weights: raises ValueError.
        - Relative values must be finite and > 0.
        - Weight values must be finite and >= 0.
        - For non-empty eligible sets, weights must sum to 1.0 exactly (within
          a small absolute tolerance).
    """

    if not isinstance(item_price_relatives_result, ItemPriceRelatives):
        raise TypeError("item_price_relatives_result must be an ItemPriceRelatives")

    base_period: date = item_price_relatives_result.base_period
    current_period: date = item_price_relatives_result.current_period

    raw_relatives = item_price_relatives_result.item_price_relatives
    validated_relatives = _validate_relative_mapping(raw_relatives)
    validated_weights = _validate_weight_mapping(weights)

    if len(validated_relatives) == 0:
        if len(validated_weights) == 0:
            methodology = IndexMethodologyMetadata()
            return IndexResult(
                base_period=base_period,
                current_period=current_period,
                overall_laspeyres_index=100.0,
                overall_jevons_index=100.0,
                item_indices=[],
                methodology=methodology,
            )
        raise ValueError("weights must be empty when item_price_relatives is empty")

    if len(validated_weights) == 0:
        raise ValueError(
            "weights must be non-empty when item_price_relatives is non-empty"
        )

    rel_keys = set(validated_relatives.keys())
    weight_keys = set(validated_weights.keys())
    if rel_keys != weight_keys:
        missing_in_weights = rel_keys - weight_keys
        missing_in_relatives = weight_keys - rel_keys
        raise ValueError(
            "weights and item_price_relatives keys must match "
            f"(missing_in_weights={len(missing_in_weights)}, "
            f"missing_in_relatives={len(missing_in_relatives)})"
        )

    weights_total = sum(validated_weights.values())
    if weights_total == 0.0:
        raise ValueError("sum of weights must be > 0")
    if not math.isclose(weights_total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"weights must sum to 1.0 (got {weights_total!r})")

    items_sorted = sorted(validated_relatives.keys(), key=_item_sort_key)

    laspeyres_rel_sum = 0.0
    log_weighted_sum = 0.0
    for item in items_sorted:
        w = validated_weights[item]
        r = validated_relatives[item]

        # w is >= 0 and r > 0; rel_sum arithmetic is well-defined.
        laspeyres_rel_sum += w * r

        # Jevons weighted geometric mean: exp(sum w_i * ln(r_i))
        log_weighted_sum += w * math.log(r)

    overall_laspeyres_index = 100.0 * laspeyres_rel_sum
    try:
        overall_jevons_index = 100.0 * math.exp(log_weighted_sum)
    except OverflowError as e:
        raise ValueError("computed overall_jevons_index is not finite") from e

    if not math.isfinite(overall_laspeyres_index):
        raise ValueError("computed overall_laspeyres_index is not finite")
    if not math.isfinite(overall_jevons_index):
        raise ValueError("computed overall_jevons_index is not finite")
    if overall_laspeyres_index <= 0.0 or overall_jevons_index <= 0.0:
        raise ValueError("computed overall indices must be > 0")

    item_indices: List[ItemIndex] = []
    for item in items_sorted:
        origin, destination, cabin_class, trip_type = item
        item_model_key = ItemKey(
            origin=origin,
            destination=destination,
            cabin_class=cabin_class,
            trip_type=trip_type,
        )
        item_indices.append(
            ItemIndex(item=item_model_key, index_relative=validated_relatives[item])
        )

    methodology = IndexMethodologyMetadata()
    return IndexResult(
        base_period=base_period,
        current_period=current_period,
        overall_laspeyres_index=overall_laspeyres_index,
        overall_jevons_index=overall_jevons_index,
        item_indices=item_indices,
        methodology=methodology,
    )


__all__ = ["compute_overall_airfare_index"]
