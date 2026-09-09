"""Fares API domain endpoints.

Provides enriched query capabilities, route-level filtering, pagination,
and advance booking window analysis.
"""

from __future__ import annotations

from datetime import date, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.connection import get_connection
from database.repository import get_fares
from models.fare import Fare

router = APIRouter(prefix="/api/fares", tags=["Fares"])


def _db():
    return get_connection()


class FareSummary(BaseModel):
    total_observations: int
    overall_median_inr: float
    overall_mean_inr: float
    min_price_inr: float
    max_price_inr: float
    airline_counts: Dict[str, int]
    sector_counts: Dict[str, int]


class SectorPriceInfo(BaseModel):
    sector: str
    origin: str
    destination: str
    distance_km: Optional[float]
    median_price_inr: float
    min_price_inr: float
    max_price_inr: float
    quote_count: int


@router.get("", response_model=List[Fare])
def list_fares(
    origin: Optional[str] = Query(None, min_length=3, max_length=3, description="Origin IATA code"),
    destination: Optional[str] = Query(None, min_length=3, max_length=3, description="Destination IATA code"),
    airline_code: Optional[str] = Query(None, description="Airline IATA code (e.g. 6E, AI)"),
    cabin_class: Optional[str] = Query(None, description="Cabin class (ECONOMY, BUSINESS)"),
    min_price: Optional[float] = Query(None, ge=0.0),
    max_price: Optional[float] = Query(None, ge=0.0),
    max_lead_days: Optional[int] = Query(None, ge=0, description="Max advance booking window in days"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[Fare]:
    """Retrieve filtered fare observations with pagination."""
    conn = _db()
    fares = get_fares(conn)

    filtered = fares
    if origin:
        filtered = [f for f in filtered if f.route.origin == origin.upper()]
    if destination:
        filtered = [f for f in filtered if f.route.destination == destination.upper()]
    if airline_code:
        filtered = [f for f in filtered if f.airline_code == airline_code.upper()]
    if cabin_class:
        filtered = [f for f in filtered if f.cabin_class.value == cabin_class.upper()]
    if min_price is not None:
        filtered = [f for f in filtered if f.price_inr >= min_price]
    if max_price is not None:
        filtered = [f for f in filtered if f.price_inr <= max_price]
    if max_lead_days is not None:
        filtered = [
            f for f in filtered
            if (f.departure_at.date() - f.scraped_at.date()).days <= max_lead_days
        ]

    return filtered[offset : offset + limit]


@router.get("/summary", response_model=FareSummary)
def fare_summary() -> FareSummary:
    """Return statistical summary of collected fares."""
    conn = _db()
    fares = get_fares(conn)

    if not fares:
        return FareSummary(
            total_observations=0,
            overall_median_inr=0.0,
            overall_mean_inr=0.0,
            min_price_inr=0.0,
            max_price_inr=0.0,
            airline_counts={},
            sector_counts={},
        )

    prices = sorted(f.price_inr for f in fares)
    n = len(prices)
    median = prices[n // 2]
    mean = sum(prices) / n

    airline_counts: Dict[str, int] = {}
    sector_counts: Dict[str, int] = {}
    for f in fares:
        airline_counts[f.airline_code] = airline_counts.get(f.airline_code, 0) + 1
        sec = f"{f.route.origin}-{f.route.destination}"
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

    return FareSummary(
        total_observations=n,
        overall_median_inr=round(median, 2),
        overall_mean_inr=round(mean, 2),
        min_price_inr=round(min(prices), 2),
        max_price_inr=round(max(prices), 2),
        airline_counts=airline_counts,
        sector_counts=sector_counts,
    )


@router.get("/sectors", response_model=List[SectorPriceInfo])
def list_sectors() -> List[SectorPriceInfo]:
    """Return sector-level aggregated pricing stats."""
    conn = _db()
    fares = get_fares(conn)

    sectors: Dict[str, List[Fare]] = {}
    for f in fares:
        sec = f"{f.route.origin}-{f.route.destination}"
        sectors.setdefault(sec, []).append(f)

    results: List[SectorPriceInfo] = []
    for sec, sector_fares in sorted(sectors.items()):
        prices = sorted(f.price_inr for f in sector_fares)
        n = len(prices)
        rep = sector_fares[0]
        results.append(
            SectorPriceInfo(
                sector=sec,
                origin=rep.route.origin,
                destination=rep.route.destination,
                distance_km=rep.route.distance_km,
                median_price_inr=round(prices[n // 2], 2),
                min_price_inr=round(prices[0], 2),
                max_price_inr=round(prices[-1], 2),
                quote_count=n,
            )
        )

    return results
