"""Database Seeder: Populates 35+ Days of High-Frequency Airfare Observations.

Generates realistic, DGCA-aligned observations across representative city-pairs,
major Indian airlines and OTAs, and advance booking windows (T+1, T+7, T+15, T+30, T+45).
Also computes and persists daily APIx indices.
"""

from __future__ import annotations

import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

# Ensure repository root is on sys.path when executed directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database.connection import get_connection
from database.repository import (
    count_fares,
    get_fares,
    insert_fares,
    insert_index_result,
)
from database.schema import init_schema
from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_psd_base_basket_weights
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.route import Route

# Representative domestic sectors with great-circle distance & baseline fare
SECTORS = [
    ("DEL", "BOM", 1138.0, 5450.0),
    ("BOM", "DEL", 1138.0, 5420.0),
    ("DEL", "BLR", 1740.0, 6120.0),
    ("BLR", "DEL", 1740.0, 6090.0),
    ("BOM", "BLR", 842.0, 4380.0),
    ("BLR", "BOM", 842.0, 4350.0),
    ("DEL", "CCU", 1305.0, 5850.0),
    ("CCU", "DEL", 1305.0, 5820.0),
    ("BLR", "HYD", 500.0, 3650.0),
    ("HYD", "BLR", 500.0, 3620.0),
    ("MAA", "DEL", 1760.0, 6200.0),
    ("DEL", "MAA", 1760.0, 6180.0),
    ("DEL", "HYD", 1253.0, 4920.0),
    ("HYD", "DEL", 1253.0, 4890.0),
]

AIRLINES = [
    ("6E", "IndiGo", 0.98),         # code, name, price factor
    ("AI", "Air India", 1.04),
    ("IX", "Air India Express", 0.92),
    ("QP", "Akasa Air", 0.94),
    ("SG", "SpiceJet", 0.95),
]

OTAS = ["MakeMyTrip", "ClearTrip", "EaseMyTrip", "Ixigo", "Yatra"]

WINDOWS = [1, 7, 15, 30, 45]


def _window_multiplier(lead_days: int) -> float:
    """Dynamic pricing curve: sharp surge close to departure (T+1), discount at T+45."""
    if lead_days <= 1:
        return 1.65  # +65% surge last-minute
    elif lead_days <= 3:
        return 1.45
    elif lead_days <= 7:
        return 1.20  # +20% week of flight
    elif lead_days <= 15:
        return 1.05
    elif lead_days <= 30:
        return 0.95  # baseline advance
    else:
        return 0.86  # advance saver (-14%)


def generate_seed_fares(
    start_date: date = date(2026, 8, 1),
    num_days: int = 39,
) -> List[Fare]:
    """Generate deterministic, statistically consistent fare quotes."""
    rng = random.Random(42)  # Deterministic seed for reproducible evaluation
    fares: List[Fare] = []

    for day_offset in range(num_days):
        current_day = start_date + timedelta(days=day_offset)
        scrape_dt = datetime(
            current_day.year, current_day.month, current_day.day,
            10, 0, 0, tzinfo=timezone.utc
        )

        day_of_week = current_day.weekday()
        # Weekend effect in Indian travel: Friday & Sunday flights are pricier
        dow_factor = 1.07 if day_of_week in (4, 6) else (0.96 if day_of_week in (1, 2) else 1.0)
        # Macro drift simulating jet fuel & festive demand rise towards September
        macro_drift = 1.0 + (day_offset * 0.0018) + (0.025 * math.sin(day_offset * 0.4))

        for origin, dest, dist, base_fare in SECTORS:
            route = Route(origin=origin, destination=dest, distance_km=dist)

            for lead_days in WINDOWS:
                dep_date = current_day + timedelta(days=lead_days)
                dep_dt = datetime(
                    dep_date.year, dep_date.month, dep_date.day,
                    8, 30, 0, tzinfo=timezone.utc
                )
                w_mult = _window_multiplier(lead_days)

                for code, airline_name, carrier_mult in AIRLINES:
                    # Random small fluctuation (+/- 2.5%)
                    jitter = rng.uniform(0.975, 1.025)
                    final_fare = round(base_fare * w_mult * carrier_mult * dow_factor * macro_drift * jitter, 2)

                    # Determine source (mix of direct airline and OTAs)
                    is_ota = rng.random() > 0.4
                    if is_ota:
                        source_name = rng.choice(OTAS)
                        source_type = SourceType.OTA
                        source_url = f"https://www.{source_name.lower()}.com/flights/{origin}-{dest}"
                    else:
                        source_name = airline_name
                        source_type = SourceType.AIRLINE
                        source_url = f"https://www.{airline_name.lower().replace(' ', '')}.in/flights/{origin}-{dest}"

                    offer_id = f"SEED-{current_day.isoformat()}-{origin}-{dest}-{code}-{lead_days}D"

                    fare = Fare(
                        route=route,
                        airline_code=code,
                        price_inr=final_fare,
                        cabin_class=CabinClass.ECONOMY,
                        departure_at=dep_dt,
                        scraped_at=scrape_dt,
                        trip_type=TripType.ONE_WAY,
                        source=RawFareSource(
                            source_name=source_name,
                            source_type=source_type,
                            raw_price=final_fare,
                            raw_currency="INR",
                            raw_cabin_label="Economy",
                            source_url=source_url,
                            raw_offer_id=offer_id,
                        ),
                    )
                    fares.append(fare)

    return fares


def seed_database(force: bool = False) -> int:
    """Populate database with fares and compute daily APIx index time-series."""
    conn = get_connection()
    init_schema(conn)

    existing = count_fares(conn)
    if existing > 0 and not force:
        print(f"Database already contains {existing} fare observations. Skipping seeding.")
        return existing

    print("Generating 35+ days of rich, multi-sector, multi-window fare observations...")
    fares = generate_seed_fares(start_date=date(2026, 8, 1), num_days=39)
    print(f"Inserting {len(fares)} fare observations into PostgreSQL...")
    inserted = insert_fares(conn, fares)
    print(f"Successfully inserted {inserted} fare observations.")

    # Compute daily indices for all days
    print("Computing daily Airfare Price Index (APIx) time-series...")
    all_stored_fares = get_fares(conn)
    dates = sorted({f.scraped_at.date() for f in all_stored_fares})

    indices_created = 0
    for d in dates:
        try:
            relatives = aggregate_item_price_relatives(all_stored_fares, current_period=d)
            weights = compute_psd_base_basket_weights(relatives.item_price_relatives)
            index_res = compute_overall_airfare_index(relatives, weights)
            insert_index_result(conn, index_res)
            indices_created += 1
        except Exception as e:
            print(f"Warning: could not index period {d}: {e}")

    print(f"Computed and persisted {indices_created} daily index results.")
    return inserted


if __name__ == "__main__":
    seed_database(force=True)
