"""One-shot real end-to-end verification script for Cleartrip live acquisition.

Tests the full acquisition chain:
SearchJob
   ↓
Scheduler / Cleartrip live adapter
   ↓
Playwright Chromium headless session
   ↓
/flight/search/v2 capture
   ↓
Cleartrip parser (direct, connecting, fares, datetimes, overnight, etc.)
   ↓
Pipeline (validation, cleaning, normalization, deduplication)
   ↓
Fare domain model
   ↓
Database repository (PostgreSQL persistence)
   ↓
Index Engine (price relatives, weights, overall Laspeyres/Jevons index)
   ↓
API (FastAPI endpoints: /fares, /index, /index/history)
"""

# ruff: noqa: E402

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.main import app
from database.connection import get_connection
from database.repository import (
    count_fares,
    get_fares,
)
from database.schema import init_schema, truncate_tables
from pipeline import process_raw_fares
from scheduler.search import SearchJob
from scraper.otas.cleartrip_live import ClearTripLiveScraper


def run_e2e_verification() -> bool:
    print("=" * 60)
    print("SIH 26056: CLEARTRIP LIVE END-TO-END PIPELINE VERIFICATION")
    print("=" * 60)

    # Step 1: Initialize Database Connection & Schema
    print("\n[STEP 1] Initializing PostgreSQL database connection and schema...")
    conn = get_connection()
    init_schema(conn)
    truncate_tables(conn)
    initial_count = count_fares(conn)
    print(f"  ✓ Database connected. Initial fares count: {initial_count}")

    # Step 2: Create SearchJob Contract
    print("\n[STEP 2] Constructing SearchJob...")
    job = SearchJob(
        source="cleartrip",
        origin="DEL",
        destination="BLR",
        departure_date="2026-09-16",
        adults=1,
        children=0,
        infants=0,
        cabin="ECONOMY",
        trip_type="ONE_WAY",
    )
    print(f"  ✓ SearchJob created: {job}")
    print(f"  ✓ Cleartrip search date: {job.cleartrip_date}, ISO date: {job.iso_date}")
    print(f"  ✓ Route model: {job.to_route()}")

    # Step 3: Run Cleartrip Live Scraper
    print("\n[STEP 3] Launching live Playwright session for Cleartrip...")
    scraper = ClearTripLiveScraper()
    print("  ✓ Scraper adapter instantiated:", scraper.name, scraper.source_type)

    start_time = datetime.now(timezone.utc)
    raw_records = scraper.search(job, wait_seconds=60, headless=True)
    duration_secs = (datetime.now(timezone.utc) - start_time).total_seconds()

    if not raw_records:
        print(f"  ⚠ Scraper returned 0 raw records after {duration_secs:.1f}s.")
        print(
            "  Checking if page encountered a security challenge or anti-bot"
            " verification..."
        )
        print("  Controlled failure was handled safely (no crash, 0 corrupt data).")
        return False

    print(
        "  ✓ Successfully captured and parsed live Cleartrip response in "
        f"{duration_secs:.1f}s!"
    )
    print(f"  ✓ Raw records extracted: {len(raw_records)}")

    sample = raw_records[0]
    print("  ✓ Sample record:")
    print(f"      Carrier: {sample.get('airline_code')} {sample.get('flight_number')}")
    print(
        f"      Route: {sample['route']['origin']} -> {sample['route']['destination']}"
    )
    print(f"      Departure: {sample.get('departure_at')}")
    print(f"      Price: ₹{sample.get('price_inr')}")
    print(f"      Stops: {sample.get('stops')}")
    print(f"      Raw Offer ID: {sample['source'].get('raw_offer_id')}")

    # Check for direct and connecting flights
    direct = [r for r in raw_records if r.get("stops") == 0]
    connecting = [r for r in raw_records if r.get("stops", 0) > 0]
    print(f"  ✓ Direct itineraries: {len(direct)}")
    print(f"  ✓ Connecting itineraries: {len(connecting)}")

    # Step 4: Run Common Pipeline
    print(
        "\n[STEP 4] Executing common pipeline: validate → clean → normalize → dedup..."
    )
    fares, bad, batch_err = process_raw_fares(raw_records)

    if batch_err is not None:
        print(f"  ✗ Pipeline batch error: {batch_err}")
        return False

    print("  ✓ Pipeline succeeded!")
    print(f"  ✓ Valid Fare domain models produced: {len(fares)}")
    print(f"  ✓ Rejected bad records: {len(bad)}")

    # Step 5: Persist to PostgreSQL Database
    print("\n[STEP 5] Persisting Fare domain models into PostgreSQL...")
    from database.repository import insert_fares

    inserted_count = insert_fares(conn, fares)
    total_db = count_fares(conn)
    print(f"  ✓ Inserted into PostgreSQL: {inserted_count} rows")
    print(f"  ✓ Total database rows in 'fares': {total_db}")

    # Step 6: Verify Persistence and Model Reconstruction
    print("\n[STEP 6] Reconstructing domain models from database...")
    db_fares = get_fares(conn)
    print(f"  ✓ Fully reconstructed {len(db_fares)} Fare instances from PostgreSQL")
    assert len(db_fares) == inserted_count
    assert db_fares[0].route.origin == "DEL"
    assert db_fares[0].route.destination == "BLR"

    # Step 7: Index Engine Aggregation & Calculation
    print("\n[STEP 7] Computing Price Index with Index Engine...")
    current_period = max(f.scraped_at.date() for f in db_fares)
    from database.repository import get_index_result, insert_index_result
    from index_engine.aggregation import aggregate_item_price_relatives
    from index_engine.api_index import compute_overall_airfare_index
    from index_engine.weights import compute_uniform_base_basket_weights

    relatives = aggregate_item_price_relatives(db_fares, current_period=current_period)
    weights = compute_uniform_base_basket_weights(relatives.item_price_relatives)
    computed_index = compute_overall_airfare_index(relatives, weights)
    print(f"  ✓ Base period: {computed_index.base_period}")
    print(f"  ✓ Current period: {computed_index.current_period}")
    print(f"  ✓ Laspeyres Index: {computed_index.overall_laspeyres_index}")
    print(f"  ✓ Jevons Index: {computed_index.overall_jevons_index}")

    insert_index_result(conn, computed_index)
    persisted_idx = get_index_result(
        conn,
        base_period=computed_index.base_period,
        current_period=computed_index.current_period,
    )
    assert persisted_idx is not None
    print("  ✓ Index result successfully persisted in PostgreSQL")

    # Step 8: Query via FastAPI Endpoints
    print("\n[STEP 8] Querying via FastAPI Client Endpoints...")
    client = TestClient(app)

    r_health = client.get("/health")
    assert r_health.status_code == 200
    print(f"  ✓ GET /health -> 200 OK: {r_health.json()}")

    r_fares = client.get("/fares?origin=DEL&destination=BLR")
    assert r_fares.status_code == 200
    fares_data = r_fares.json()
    assert len(fares_data) == inserted_count
    print(
        f"  ✓ GET /fares?origin=DEL&destination=BLR -> 200 OK: {len(fares_data)} fares"
    )

    r_index = client.get(f"/index?current_period={current_period.isoformat()}")
    assert r_index.status_code == 200
    idx_data = r_index.json()
    assert idx_data["overall_laspeyres_index"] == computed_index.overall_laspeyres_index
    print(
        "  ✓ GET /index?current_period="
        + current_period.isoformat()
        + " -> 200 OK: Laspeyres = "
        + str(idx_data["overall_laspeyres_index"])
    )

    r_hist = client.get("/index/history")
    assert r_hist.status_code == 200
    assert len(r_hist.json()) >= 1
    print(f"  ✓ GET /index/history -> 200 OK: {len(r_hist.json())} history entries")

    print("\n" + "=" * 60)
    print("ALL 8 VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_e2e_verification()
    sys.exit(0 if success else 1)
