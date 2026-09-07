"""End-to-end test: scraper → pipeline → database using MMT mock data.

This validates the full Day-4 vertical slice without requiring MakeMyTrip
to be online: mock HTML → MakeMyTripScraper → pipeline → Fare → SQLite.
"""

import pytest

from database.connection import close_connection, reset_connection
from database.repository import count_fares, get_fares_by_route, insert_fare
from database.schema import init_schema
from pipeline import process_raw_fares
from scraper.otas.mmt import _MOCK_FLIGHT_CARD, MakeMyTripScraper


@pytest.fixture()
def conn():
    """An isolated in-memory SQLite database with the fares schema."""
    connection = reset_connection(path=":memory:")
    init_schema(connection)
    yield connection
    close_connection()


def test_e2e_scraper_pipeline_database(conn):
    """Full flow: MMT mock HTML → scraper → pipeline → Fare → SQLite."""
    # 1. Extract from mock HTML
    scraper = MakeMyTripScraper()
    raw_fares = scraper.extract(_MOCK_FLIGHT_CARD)
    assert len(raw_fares) == 1, f"Expected 1 fare, got {len(raw_fares)}"

    # 2. Run pipeline
    fares, bad, batch_err = process_raw_fares(raw_fares)
    assert batch_err is None, f"Batch validation failed: {batch_err}"
    assert not bad, f"Unexpected bad records: {bad}"
    assert len(fares) == 1, "Pipeline should produce one valid Fare"

    # 3. Persist to the isolated in-memory database
    assert insert_fare(conn, fares[0]) > 0, "Failed to insert fare"
    assert count_fares(conn) == 1, "Database should contain exactly one fare"

    # 4. Verify data integrity of the stored row
    fare = fares[0]
    stored_rows = get_fares_by_route(conn, "DEL", "BOM")
    assert len(stored_rows) == 1
    stored = stored_rows[0]
    assert stored["price_inr"] == fare.price_inr
    assert stored["route_origin"] == fare.route.origin
    assert stored["route_destination"] == fare.route.destination
    assert stored["airline_code"] == fare.airline_code
    assert stored["cabin_class"] == fare.cabin_class.value
    assert stored["trip_type"] == fare.trip_type.value
    assert stored["source_name"] == fare.source.source_name
    assert stored["source_type"] == fare.source.source_type.value
    assert stored["raw_currency"] == "INR"
    assert stored["raw_offer_id"] == fare.source.raw_offer_id


def test_e2e_scrape_runs_are_deterministic(conn):
    """Two identical scrape runs over one connection produce no duplicates."""
    scraper = MakeMyTripScraper()
    html = _MOCK_FLIGHT_CARD

    for run_index in range(2):
        raw_batch = scraper.extract(html)
        assert len(raw_batch) == 1, "Each scrape run should emit one record"

        fares, bad, err = process_raw_fares(raw_batch)
        assert err is None and not bad
        assert len(fares) == 1, "Decision pipeline should preserve the single fare"

        inserted = insert_fare(conn, fares[0])
        if run_index == 0:
            assert inserted > 0, "First run should persist the fare"
        else:
            assert inserted == 0, "Second run should be rejected as a duplicate"

        assert count_fares(conn) == 1, "Duplicate persisted fares must be blocked"


def test_e2e_bad_html_to_empty_database(conn):
    """Malformed HTML yields no records — pipeline and DB stay empty."""
    scraper = MakeMyTripScraper()
    raw_fares = scraper.extract(
        '<div class="flight-card" data-route="DEL-BOM">no price</div>'
    )
    assert raw_fares == []

    fares, bad, err = process_raw_fares([])
    assert err is not None  # batch validation rejects empty input
    assert fares == []
    assert count_fares(conn) == 0
