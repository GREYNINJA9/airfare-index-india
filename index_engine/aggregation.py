"""Index aggregation (MVP-locked).

This module is responsible for:
- UTC daily bucketing from ``Fare.scraped_at``
- grouping by item identity: (origin, destination, cabin_class, trip_type)
- computing an effective item-day price via MEDIAN across all quotes
- selecting the base day via the locked completeness/coverage algorithm
- computing price relatives r_i(d) = P_i(d) / P_i(d0)

It deliberately does *not* implement weights, Laspeyres/Jevons, API shaping,
or elasticity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timezone
from typing import Dict, Iterable, List, Set, Tuple

from models.fare import CabinClass, Fare, TripType

ItemKey = Tuple[str, str, CabinClass, TripType]


@dataclass(frozen=True)
class ItemPriceRelatives:
    """Aggregation result for one current UTC daily period."""

    base_period: date
    current_period: date
    # Only items that are in the base basket and observed in the current
    # period are included.
    item_price_relatives: Dict[ItemKey, float]


def _utc_day(scraped_at) -> date:
    # `Fare` guarantees timezone-aware datetimes.
    return scraped_at.astimezone(timezone.utc).date()


def _item_key(fare: Fare) -> ItemKey:
    return (
        fare.route.origin,
        fare.route.destination,
        fare.cabin_class,
        fare.trip_type,
    )


def _median(sorted_values: List[float]) -> float:
    n = len(sorted_values)
    if n == 0:
        raise ValueError("median requires at least one value")
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_values[mid])
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _group_median_prices(
    fares: Iterable[Fare],
) -> Tuple[
    Dict[Tuple[ItemKey, date], float],
    Dict[date, Set[ItemKey]],
    Set[ItemKey],
    List[date],
]:
    # quote_lists[(item, day)] = [price_inr, ...]
    quote_lists: Dict[Tuple[ItemKey, date], List[float]] = {}

    # items_by_day[day] = {item1, item2, ...}
    items_by_day: Dict[date, Set[ItemKey]] = {}
    item_universe: Set[ItemKey] = set()

    for fare in fares:
        day = _utc_day(fare.scraped_at)
        item = _item_key(fare)
        quote_lists.setdefault((item, day), []).append(fare.price_inr)
        items_by_day.setdefault(day, set()).add(item)
        item_universe.add(item)

    median_prices: Dict[Tuple[ItemKey, date], float] = {}
    for (item, day), prices in quote_lists.items():
        sorted_prices = sorted(prices)
        median_prices[(item, day)] = _median(sorted_prices)

    days_sorted = sorted(items_by_day.keys())

    return median_prices, items_by_day, item_universe, days_sorted


def _select_base_day(
    *,
    item_universe: Set[ItemKey],
    items_by_day: Dict[date, Set[ItemKey]],
    days_sorted: List[date],
) -> date:
    if not item_universe:
        raise ValueError("cannot select base day: item universe is empty")

    # Identify complete days where every item in U appears.
    complete_days: List[date] = []
    for d in days_sorted:
        observed_items = items_by_day.get(d, set())
        if item_universe.issubset(observed_items):
            complete_days.append(d)

    if complete_days:
        # Earliest complete day.
        return min(complete_days)

    # No complete day: choose maximum distinct-item coverage.
    best_day = days_sorted[0]
    best_coverage = -1

    for d in days_sorted:
        coverage = len(items_by_day.get(d, set()))
        if coverage > best_coverage:
            best_day = d
            best_coverage = coverage
        elif coverage == best_coverage and d < best_day:
            best_day = d

    return best_day


def aggregate_item_price_relatives(
    fares: List[Fare],
    *,
    current_period: date,
) -> ItemPriceRelatives:
    """Aggregate Fare quotes into item-day price relatives.

    Args:
        fares: normalized Fare observations.
        current_period: the UTC daily period date for which to compute
            price relatives.

    Returns:
        ItemPriceRelatives containing base_period and relative prices
        r_i(current_period) for items in the base basket that are observed in
        the current period.

    Raises:
        ValueError: if fares is empty.
        TypeError: if fares is not a list.
    """

    if not isinstance(fares, list):
        raise TypeError(f"fares must be a list[Fare], got {type(fares).__name__}")
    if len(fares) == 0:
        raise ValueError("fares must be non-empty")

    median_prices, items_by_day, item_universe, days_sorted = _group_median_prices(
        fares
    )

    base_period = _select_base_day(
        item_universe=item_universe,
        items_by_day=items_by_day,
        days_sorted=days_sorted,
    )

    base_items = items_by_day.get(base_period, set())
    current_items = items_by_day.get(current_period, set())

    observed_items = base_items.intersection(current_items)

    item_relatives: Dict[ItemKey, float] = {}
    for item in observed_items:
        base_price = median_prices[(item, base_period)]
        current_price = median_prices[(item, current_period)]
        item_relatives[item] = current_price / base_price

    return ItemPriceRelatives(
        base_period=base_period,
        current_period=current_period,
        item_price_relatives=item_relatives,
    )
