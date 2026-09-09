"""Integration test: Cleartrip live adapter → pipeline → database → index engine.

Runs deterministically with network boundary mocked using real captured Cleartrip JSON.
Verifies the complete flow without needing an active internet connection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from database.repository import (
    count_fares,
    get_fares_by_route,
    get_index_results,
)
from database.schema import truncate_tables
from pipeline import process_raw_fares
from scheduler.jobs import run_search_job
from scheduler.search import SearchJob
from scraper.otas.cleartrip_live import ClearTripLiveScraper

FIXTURE_PATH = Path("data/raw/cleartrip/cleartrip_raw_20260909T053756Z.json")


@pytest.fixture
def v2_fixture_data() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture {FIXTURE_PATH} not found")
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    v2 = data.get("responses", {}).get("flight_search_v2")
    if not v2:
        pytest.skip("Fixture has no flight_search_v2 response")
    return v2


class MockNetworkClearTripScraper(ClearTripLiveScraper):
    """ClearTrip live scraper mocked at the browser/network boundary."""

    def __init__(self, v2_payload: dict, simulate_challenge: bool = False) -> None:
        super().__init__()
        self.v2_payload = v2_payload
        self.simulate_challenge = simulate_challenge

    def search(self, job: SearchJob, *, save_raw: bool = False, **kwargs) -> list[dict]:
        if self.simulate_challenge:
            return []
        return self.extract_v2(
            self.v2_payload,
            job=job,
            source_url=f"https://www.cleartrip.com/flights/results?from={job.origin}&to={job.destination}",
        )


def test_cleartrip_live_mocked_network_to_database(db, v2_fixture_data):
    """Verify SearchJob → mock scraper → pipeline → Fare → PostgreSQL."""
    truncate_tables(db)

    job = SearchJob(
        source="cleartrip",
        origin="DEL",
        destination="BLR",
        departure_date="2026-09-16",
        adults=1,
        cabin="ECONOMY",
        trip_type="ONE_WAY",
    )

    scraper = MockNetworkClearTripScraper(v2_fixture_data)
    raw_records = scraper.search(job)
    assert len(raw_records) > 0, "Should extract raw records from captured response"

    # Pipeline
    fares, bad, batch_err = process_raw_fares(raw_records)
    assert batch_err is None
    assert len(bad) == 0
    assert len(fares) == len(raw_records)

    # Persist through repository
    from database.repository import insert_fares

    inserted = insert_fares(db, fares)
    assert inserted == len(fares)
    assert count_fares(db) == len(fares)

    # Verify stored records in DB
    stored_fares = get_fares_by_route(db, "DEL", "BLR")
    assert len(stored_fares) == len(fares)

    first_stored = stored_fares[0]
    assert first_stored["route_origin"] == "DEL"
    assert first_stored["route_destination"] == "BLR"
    assert first_stored["source_name"] == "ClearTrip"
    assert first_stored["source_type"] == "OTA"
    assert first_stored["raw_currency"] == "INR"
    assert first_stored["price_inr"] > 0
    assert first_stored["raw_offer_id"].startswith("CT-")


def test_scheduler_run_search_jobs_with_cleartrip(db, v2_fixture_data):
    """Scheduler runs SearchJob through Cleartrip adapter to DB and index."""
    truncate_tables(db)

    job = SearchJob(
        source="cleartrip",
        origin="DEL",
        destination="BLR",
        departure_date="2026-09-16",
    )

    mock_scraper = MockNetworkClearTripScraper(v2_fixture_data)
    summary = run_search_job(job, conn=db, scraper=mock_scraper, compute_index=True)

    assert summary["jobs_attempted"] == 1
    assert summary["jobs_successful"] == 1
    assert summary["jobs_failed"] == 0
    assert summary["job_errors"] == {}
    assert summary["raw_records_extracted"] > 0
    assert summary["normalized_fares"] > 0
    assert summary["fares_inserted"] == summary["normalized_fares"]
    assert summary["duplicate_fares_skipped"] == 0
    assert summary["pipeline_error"] is None

    assert summary["index_generated"] is True
    assert summary["overall_laspeyres_index"] == pytest.approx(100.0)
    assert summary["overall_jevons_index"] == pytest.approx(100.0)

    # Verify index result persisted in DB
    results = get_index_results(db)
    assert len(results) == 1
    assert results[0].overall_laspeyres_index == pytest.approx(100.0)


def test_cleartrip_challenge_at_boundary_safe_failure(db, v2_fixture_data):
    """When the network hits a challenge, scheduler keeps DB intact."""
    truncate_tables(db)

    job = SearchJob(
        source="cleartrip",
        origin="DEL",
        destination="BLR",
        departure_date="2026-09-16",
    )

    challenge_scraper = MockNetworkClearTripScraper(
        v2_fixture_data, simulate_challenge=True
    )
    summary = run_search_job(
        job, conn=db, scraper=challenge_scraper, compute_index=True
    )

    assert summary["jobs_attempted"] == 1
    assert summary["jobs_successful"] == 1
    assert summary["raw_records_extracted"] == 0
    assert summary["normalized_fares"] == 0
    assert summary["fares_inserted"] == 0
    assert summary["index_generated"] is False
    assert count_fares(db) == 0
