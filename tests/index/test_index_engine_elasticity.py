"""Unit tests for lead-time elasticity and dynamic pricing curve fitting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from index_engine.elasticity import (
    compute_lead_time_elasticity,
    compute_route_elasticity,
    compute_window_stats,
)
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.route import Route


def _make_fare(days_ahead: int, price: float, origin: str = "DEL", dest: str = "BOM") -> Fare:
    scrape_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    dep_time = scrape_time + timedelta(days=days_ahead)
    return Fare(
        route=Route(origin=origin, destination=dest),
        airline_code="6E",
        price_inr=price,
        cabin_class=CabinClass.ECONOMY,
        departure_at=dep_time,
        scraped_at=scrape_time,
        trip_type=TripType.ONE_WAY,
        source=RawFareSource(
            source_name="IndiGo",
            source_type=SourceType.AIRLINE,
            raw_price=price,
            raw_currency="INR",
            raw_cabin_label="Economy",
            source_url="https://goindigo.in",
            raw_offer_id=f"test-{days_ahead}-{price}",
        ),
    )


def test_compute_window_stats():
    fares = [
        _make_fare(1, 8500.0),   # T+1
        _make_fare(2, 8000.0),   # T+1
        _make_fare(7, 6200.0),   # T+7
        _make_fare(15, 5100.0),  # T+15
        _make_fare(30, 4200.0),  # T+30
        _make_fare(45, 3800.0),  # T+45
    ]

    stats = compute_window_stats(fares)
    assert len(stats) == 5
    t1 = next(s for s in stats if s.window_label == "T+1")
    t30 = next(s for s in stats if s.window_label == "T+30")

    assert t1.observation_count == 2
    assert t1.median_price_inr == 8250.0
    assert t30.median_price_inr == 4200.0


def test_route_elasticity_surge_multiplier():
    fares = [
        _make_fare(1, 8000.0),
        _make_fare(7, 6000.0),
        _make_fare(15, 5000.0),
        _make_fare(30, 4000.0),
        _make_fare(45, 3600.0),
    ]

    curve = compute_route_elasticity(fares, "DEL", "BOM")
    assert curve.origin == "DEL"
    assert curve.destination == "BOM"
    # Surge multiplier: 8000 / 4000 = 2.0
    assert curve.surge_multiplier == pytest.approx(2.0, rel=0.05)
    # Elasticity beta should be negative (as days increase, price decreases)
    assert curve.elasticity_beta < 0.0
    assert curve.r_squared > 0.8


def test_system_lead_time_elasticity():
    fares = [
        _make_fare(1, 7500.0, "DEL", "BOM"),
        _make_fare(15, 5200.0, "DEL", "BOM"),
        _make_fare(30, 4100.0, "DEL", "BOM"),
        _make_fare(1, 9000.0, "DEL", "BLR"),
        _make_fare(15, 6100.0, "DEL", "BLR"),
        _make_fare(30, 4800.0, "DEL", "BLR"),
    ]

    result = compute_lead_time_elasticity(fares)
    assert len(result.overall_curve) == 5
    assert len(result.route_curves) == 2
    assert result.average_surge_multiplier > 1.0
    assert result.market_elasticity_coefficient < 0.0
