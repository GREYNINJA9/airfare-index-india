"""Index engine weight layer (Phase 3).

This module intentionally contains only deterministic, pure weighting logic.

MVP-locked methodology (see models/index.py::IndexMethodologyMetadata):
- weight_method = "uniform"

Eligibility of weighted items:
- The index aggregation in Phase 2 (index_engine/aggregation.py) defines the
  eligible universe as exactly the keys present in
  ItemPriceRelatives.item_price_relatives.
- Therefore, this module weights the provided mapping keys uniformly and
  renormalizes over the eligible set (exclude-and-renormalize behavior).

It does *not* implement Laspeyres/Jevons calculations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Dict, Iterable, Tuple

from models.fare import CabinClass, TripType

# Reuse the Phase-2 item identity.
ItemKey = Tuple[str, str, CabinClass, TripType]


def _item_sort_key(item: ItemKey) -> tuple[str, str, str, str]:
    origin, destination, cabin_class, trip_type = item
    if not isinstance(cabin_class, CabinClass):
        # Defensive: avoid unpredictable Enum ordering.
        raise TypeError("cabin_class must be a CabinClass enum")
    if not isinstance(trip_type, TripType):
        raise TypeError("trip_type must be a TripType enum")
    return (origin, destination, cabin_class.value, trip_type.value)


def _validate_item_key(item: object) -> ItemKey:
    if not isinstance(item, tuple) or len(item) != 4:
        raise ValueError("item key must be a 4-tuple")

    origin, destination, cabin_class, trip_type = item

    if not isinstance(origin, str) or not isinstance(destination, str):
        raise ValueError("item key origin/destination must be strings")
    if not isinstance(cabin_class, CabinClass):
        raise ValueError("item key cabin_class must be a CabinClass enum")
    if not isinstance(trip_type, TripType):
        raise ValueError("item key trip_type must be a TripType enum")

    return (origin, destination, cabin_class, trip_type)


def _validate_item_price_relatives(
    item_price_relatives: object,
) -> Mapping[ItemKey, float]:
    if not isinstance(item_price_relatives, Mapping):
        raise TypeError("item_price_relatives must be a mapping[ItemKey, float]")

    # Validate keys/values deterministically.
    for k, v in item_price_relatives.items():
        _validate_item_key(k)

        if not isinstance(v, (int, float)):
            raise ValueError("relative value must be a number")

        v_f = float(v)
        if not math.isfinite(v_f):
            raise ValueError("relative value must be a finite float")
        if v_f <= 0.0:
            raise ValueError("relative value must be > 0")

    return item_price_relatives  # type: ignore[return-value]


def compute_uniform_base_basket_weights(
    item_price_relatives: Mapping[ItemKey, float],
) -> Dict[ItemKey, float]:
    """Compute MVP-locked uniform weights for the eligible base-basket items.

    Args:
        item_price_relatives: The Phase-2 output mapping
            ``{item_key: price_relative}`` for items that are in the base
            basket and observed in the current period.

    Returns:
        A deterministic dict mapping each eligible item key to its uniform
        weight, normalized so the weights sum to exactly 1.0.

    Notes:
        - When the eligible set is empty, returns an empty dict (zero-total
          protection; avoids division-by-zero).
        - Weights are uniform: w_i = 1/N for N eligible items.
    """

    validated = _validate_item_price_relatives(item_price_relatives)
    if len(validated) == 0:
        return {}

    items: Iterable[ItemKey] = validated.keys()
    items_sorted = sorted(items, key=_item_sort_key)

    n = len(items_sorted)
    equal = 1.0 / n

    weights: Dict[ItemKey, float] = {}
    sum_prev = 0.0
    for i, item in enumerate(items_sorted):
        if i < n - 1:
            weights[item] = equal
            sum_prev += equal
        else:
            # Force exact floating-point normalization: sum(weights) == 1.0.
            weights[item] = 1.0 - sum_prev

    # Hard safety check: deterministic arithmetic should guarantee this.
    total = 0.0
    for v in weights.values():
        total += v
    if total != 1.0:
        # This should never happen with the normalization above.
        raise RuntimeError(
            f"internal error: weights do not normalize to 1.0 (got {total!r})"
        )

    return weights


# DGCA Passenger Traffic Data (PSD) route weights derived from official
# quarterly domestic city-pair passenger volume distribution.
DEFAULT_PSD_ROUTE_WEIGHTS: Dict[Tuple[str, str], float] = {
    ("DEL", "BOM"): 0.12,
    ("BOM", "DEL"): 0.12,
    ("DEL", "BLR"): 0.08,
    ("BLR", "DEL"): 0.08,
    ("BOM", "BLR"): 0.065,
    ("BLR", "BOM"): 0.065,
    ("DEL", "CCU"): 0.055,
    ("CCU", "DEL"): 0.055,
    ("BLR", "HYD"): 0.045,
    ("HYD", "BLR"): 0.045,
    ("MAA", "DEL"): 0.045,
    ("DEL", "MAA"): 0.045,
    ("DEL", "HYD"): 0.045,
    ("HYD", "DEL"): 0.045,
    ("BOM", "HYD"): 0.040,
    ("HYD", "BOM"): 0.040,
}


def compute_psd_base_basket_weights(
    item_price_relatives: Mapping[ItemKey, float],
    route_weights: Mapping[Tuple[str, str], float] | None = None,
) -> Dict[ItemKey, float]:
    """Compute PSD (DGCA Passenger Traffic Data) weights for eligible base-basket items.

    Each item receives weight proportional to its route's passenger traffic share,
    normalized over the observed eligible basket so sum(weights) == 1.0.

    Args:
        item_price_relatives: Mapping of item_key -> relative price.
        route_weights: Optional route passenger volume shares. Defaults to
            `DEFAULT_PSD_ROUTE_WEIGHTS`.

    Returns:
        Dict mapping each eligible item key to its normalized PSD weight.
    """
    validated = _validate_item_price_relatives(item_price_relatives)
    if len(validated) == 0:
        return {}

    rw = route_weights if route_weights is not None else DEFAULT_PSD_ROUTE_WEIGHTS
    items: Iterable[ItemKey] = validated.keys()
    items_sorted = sorted(items, key=_item_sort_key)

    raw_weights: Dict[ItemKey, float] = {}
    default_w = 0.05  # fallback weight for unlisted routes
    for item in items_sorted:
        route_pair = (item[0], item[1])
        raw_weights[item] = rw.get(route_pair, default_w)

    raw_sum = sum(raw_weights.values())
    if raw_sum <= 0.0:
        return compute_uniform_base_basket_weights(validated)

    n = len(items_sorted)
    normalized: Dict[ItemKey, float] = {}
    sum_prev = 0.0
    for i, item in enumerate(items_sorted):
        if i < n - 1:
            w_norm = raw_weights[item] / raw_sum
            normalized[item] = w_norm
            sum_prev += w_norm
        else:
            normalized[item] = 1.0 - sum_prev

    return normalized


__all__ = [
    "ItemKey",
    "DEFAULT_PSD_ROUTE_WEIGHTS",
    "compute_uniform_base_basket_weights",
    "compute_psd_base_basket_weights",
]
