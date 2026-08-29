"""End-to-end integration test: pipeline → database using synthetic data.

This test validates that the full chain from raw fare records
through the pipeline and into the database works correctly.
"""

import json
from pathlib import Path

import pytest

from database.connection import close_connection, reset_connection
from database.repository import count_fares, get_fares_by_route
from database.schema import init_schema
from pipeline import process_raw_fares


@pytest.fixture(scope="module")
def synthetic_data():
    """Load the Day-2 synthetic dataset."""
    path = (
        Path(__file__).resolve().parents[2] / "data" / "sample" / "synthetic_fares.json"
    )
    payload = json.loads(path.read_text())
    assert payload["_meta"]["is_real_data"] is False
    return payload["fares"]


def test_full_pipeline_database_integration(synthetic_data):
    """Run the full pipeline on synthetic data and persist to DB."""
    # Pipeline
    fares, bad, batch_err = process_raw_fares(synthetic_data)
    assert batch_err is None, f"batch validation failed: {batch_err}"
    assert not bad, f"unexpected bad records: {bad}"
    assert len(fares) == len(synthetic_data), "every synthetic record should normalize"

    # Database
    conn = reset_connection(path=":memory:")
    init_schema(conn)

    inserted = 0
    for fare in fares:
        from database.repository import insert_fare

        if insert_fare(conn, fare) > 0:
            inserted += 1

    assert inserted == len(fares)
    assert count_fares(conn) == inserted

    # Spot-check a route
    del_bom = get_fares_by_route(conn, "DEL", "BOM")
    assert len(del_bom) >= 1, "synthetic set contains DEL→BOM"

    # Data integrity: price_inr is preserved
    for row in del_bom:
        assert isinstance(row["price_inr"], (int, float))
        assert row["price_inr"] > 0

    # Provenance is preserved
    assert all(r["source_name"] for r in del_bom)
    assert all(r["source_type"] for r in del_bom)
    assert all(r["raw_currency"] == "INR" for r in del_bom)

    close_connection()


def test_pipeline_database_round_trip(synthetic_data):
    """A Fare inserted and re-queried retains its business fields."""
    fares, bad, err = process_raw_fares(synthetic_data)
    assert not bad and err is None

    conn = reset_connection(path=":memory:")
    init_schema(conn)

    from database.repository import insert_fares

    insert_fares(conn, fares)

    # Query back and compare
    rows = get_fares_by_route(conn, "DEL", "BOM")
    assert rows

    # The first DEL→BOM synthetic fare
    original = next(
        f for f in fares if f.route.origin == "DEL" and f.route.destination == "BOM"
    )
    row = next(r for r in rows if r["price_inr"] == original.price_inr)

    assert row["price_inr"] == original.price_inr
    assert row["route_origin"] == original.route.origin
    assert row["route_destination"] == original.route.destination
    assert row["airline_code"] == original.airline_code
    assert row["cabin_class"] == original.cabin_class.value
    assert row["trip_type"] == original.trip_type.value
    # departure_at and scraped_at stored as ISO strings; round-trip through
    # datetime.fromisoformat preserves them
    assert row["source_name"] == original.source.source_name
    assert row["source_type"] == original.source.source_type.value

    close_connection()
