"""End-to-end integration test: ClearTrip scraper → pipeline → database.

Validates the ClearTrip vertical slice without requiring ClearTrip to be
online: mock HTML → ClearTripScraper → pipeline → Fare → SQLite.
"""

import pytest

from database.connection import close_connection, reset_connection
from database.repository import count_fares, get_fares_by_route, insert_fare
from database.schema import init_schema
from pipeline import process_raw_fares
from scraper.otas.cleartrip import _MOCK_FLIGHT_CARD, ClearTripScraper
from scraper.otas.mmt import MakeMyTripScraper


@pytest.fixture()
def conn():
    """An isolated in-memory SQLite database with the fares schema."""
    connection = reset_connection(path=":memory:")
    init_schema(connection)
    yield connection
    close_connection()


def test_cleartrip_e2e_scraper_pipeline_database(conn):
    """Full flow: ClearTrip mock HTML → scraper → pipeline → Fare → SQLite."""
    # 1. Extract from mock HTML
    scraper = ClearTripScraper()
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


def test_cleartrip_e2e_scrape_runs_are_deterministic(conn):
    """Two identical ClearTrip scrape runs collapse to one fare."""
    scraper = ClearTripScraper()
    html = _MOCK_FLIGHT_CARD

    raw_batch = scraper.extract(html + html)
    assert len(raw_batch) == 2, "Scraper should emit one record per card"

    fares, bad, err = process_raw_fares(raw_batch)
    assert err is None and not bad
    assert len(fares) == 1, "Deduplicator should collapse identical fares"

    for fare in fares:
        insert_fare(conn, fare)
    assert count_fares(conn) == 1


def test_cleartrip_e2e_bad_html_to_empty_database(conn):
    """Malformed ClearTrip HTML yields no records — pipeline and DB stay empty."""
    scraper = ClearTripScraper()
    raw_fares = scraper.extract(
        '<div class="flight-card" data-route="DEL-BOM">no price</div>'
    )
    assert raw_fares == []

    fares, bad, err = process_raw_fares([])
    assert err is not None
    assert fares == []
    assert count_fares(conn) == 0


def test_cleartrip_and_mmt_coexist_without_false_dedup(conn):
    """MMT and ClearTrip fares must coexist in the database.

    The two scrapers use different carriers (6E vs AI), prices, and scrape
    times, so they represent distinct business observations. Both must be
    stored and neither may be incorrectly collapsed into the other.
    """
    mmt_scraper = MakeMyTripScraper()
    ct_scraper = ClearTripScraper()

    mmt_raw = mmt_scraper.extract(mmt_scraper._templates["del_bom_economy"])
    ct_raw = ct_scraper.extract(ct_scraper._templates["del_bom_economy"])
    assert len(mmt_raw) == 1 and len(ct_raw) == 1

    # Different sources must not be collapsed by the batch validator
    # (which keys on (source_name, raw_offer_id)).
    fares, bad, err = process_raw_fares(mmt_raw + ct_raw)
    assert err is None, f"batch validation failed: {err}"
    assert not bad, f"unexpected bad records: {bad}"
    assert len(fares) == 2, (
        "MMT and ClearTrip fares are distinct business observations "
        "and must both survive the pipeline"
    )

    # Distinct provenance
    assert fares[0].source.source_name != fares[1].source.source_name
    assert fares[0].source.raw_offer_id != fares[1].source.raw_offer_id

    for fare in fares:
        insert_fare(conn, fare)
    assert count_fares(conn) == 2

    # Both rows present on the shared route, distinguished by source/price
    rows = get_fares_by_route(conn, "DEL", "BOM")
    assert len(rows) == 2
    prices = {r["price_inr"] for r in rows}
    assert prices == {f.price_inr for f in fares}
    sources = {r["source_name"] for r in rows}
    assert sources == {"MakeMyTrip", "ClearTrip"}
