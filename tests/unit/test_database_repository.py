"""Deterministic unit tests for database schema and repository.

Uses an in-memory SQLite database; no file system changes.
"""

import pytest

from database.components import SQLiteConnector
from database.connection import reset_connection
from database.repository import (
    count_fares,
    get_fare_by_offer_id,
    get_fares,
    get_fares_by_route,
    insert_fares,
)
from database.schema import init_schema
from models.fare import Fare
from tests.unit.test_fare_model import _valid_source  # noqa: F401, noqa: T001


@pytest.fixture
def in_memory_db():
    """Provide a fresh in-memory SQLite connection and schema."""
    conn = reset_connection(path=":memory:")
    connector = SQLiteConnector(path=":memory:")
    conn = connector.connect()
    init_schema(conn)
    yield conn
    conn.close()


# --- schema ---


def test_schema_creates_fares_table(in_memory_db):
    """The schema creates the fares table with expected columns."""
    cur = in_memory_db.execute("PRAGMA table_info(fares)")
    columns = {row["name"] for row in cur.fetchall()}
    assert "id" in columns
    assert "route_origin" in columns
    assert "route_destination" in columns
    assert "airline_code" in columns
    assert "price_inr" in columns
    assert "departure_at" in columns
    assert "scraped_at" in columns
    assert "cabin_class" in columns
    assert "source_name" in columns
    assert "source_url" in columns


def test_schema_creates_indexes(in_memory_db):
    """The schema creates useful indexes for queries."""
    cur = in_memory_db.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row["name"] for row in cur.fetchall()}
    assert "idx_fares_route_origin" in indexes
    assert "idx_fares_route_destination" in indexes
    assert "idx_fares_scraped_at" in indexes


# --- insert ---


def test_insert_fares_returns_count(in_memory_db):
    """Inserting fares returns the count inserted."""
    from tests.unit.test_fare_model import _valid_fare

    fare = _valid_fare()
    count = insert_fares(in_memory_db, [fare])
    assert count == 1


def test_insert_fares_persists_to_db(in_memory_db):
    """Inserted fares are retrievable from the DB."""
    from tests.unit.test_fare_model import _valid_fare

    fare = _valid_fare()
    insert_fares(in_memory_db, [fare])
    assert count_fares(in_memory_db) == 1


# --- query ---


def test_get_fares_by_route_returns_matching_rows(in_memory_db):
    """Query by route returns all matching rows."""
    from datetime import datetime, timezone

    from models.fare import CabinClass, TripType
    from models.route import Route

    s1 = _valid_source(raw_offer_id="route1-offer")
    s2 = _valid_source(raw_offer_id="route2-offer")
    s3 = _valid_source(raw_offer_id="other-route-offer")
    f1 = Fare(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s1,
    )
    f2 = Fare(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=6000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s2,
    )
    other = Fare(
        route=Route(origin="CCU", destination="BLR"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s3,
    )
    insert_fares(in_memory_db, [f1, f2, other])

    rows = get_fares_by_route(in_memory_db, "DEL", "BOM")
    assert len(rows) == 2
    assert rows[0]["price_inr"] == 5000.0
    assert rows[1]["price_inr"] == 6000.0


def test_get_fares_by_route_ordered_by_scraped_at(in_memory_db):
    """Results are ordered by scraped_at ascending."""
    from datetime import datetime, timezone

    from models.fare import CabinClass, RawFareSource, SourceType, TripType
    from models.route import Route

    s = RawFareSource(
        source_name="X",
        source_type=SourceType.OTA,
        raw_price=100.0,
        raw_currency="INR",
        raw_cabin_label="E",
    )
    later = Fare(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s,
    )
    earlier = Fare(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s,
    )

    insert_fares(in_memory_db, [later, earlier])

    rows = get_fares_by_route(in_memory_db, "DEL", "BOM")
    assert rows[0]["scraped_at"] == "2026-08-27T10:00:00+00:00"
    assert rows[1]["scraped_at"] == "2026-08-28T12:00:00+00:00"


def test_get_fare_by_offer_id_returns_row(in_memory_db):
    """Lookup by raw_offer_id returns the matching row."""
    from pipeline.normalizer import normalize

    # normalize returns a Fare; get its raw_offer_id
    raw_record = {
        "route": {"origin": "DEL", "destination": "BOM"},
        "airline_code": "6E",
        "price_inr": 5000.0,
        "cabin_class": "ECONOMY",
        "departure_at": "2026-09-15T06:00:00+00:00",
        "scraped_at": "2026-08-27T10:00:00+00:00",
        "trip_type": "ONE_WAY",
        "source": {
            "source_name": "X",
            "source_type": "OTA",
            "raw_price": 5000.0,
            "raw_currency": "INR",
            "raw_cabin_label": "E",
            "raw_offer_id": "TEST-ID-123",
        },
    }
    fare = normalize(raw_record)
    insert_fares(in_memory_db, [fare])

    row = get_fare_by_offer_id(in_memory_db, "TEST-ID-123")
    assert row is not None
    assert row["price_inr"] == 5000.0


def test_get_fares_skips_rows_with_null_provenance_fields(in_memory_db):
    """Legacy rows with NULL provenance are ignored while complete rows still load."""
    from datetime import datetime, timezone

    from models.fare import CabinClass, TripType
    from models.route import Route

    valid = Fare(
        route=Route(origin="DEL", destination="BOM"),
        airline_code="6E",
        price_inr=5000.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=_valid_source(),
    )
    insert_fares(in_memory_db, [valid])

    in_memory_db.execute(
        """
        INSERT INTO fares (
            route_origin, route_destination, route_distance_km,
            airline_code, price_inr, cabin_class, departure_at, scraped_at,
            trip_type, source_name, source_type, raw_price, raw_currency,
            raw_cabin_label, source_url, raw_offer_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "DEL",
            "BOM",
            1500.0,
            "AI",
            4500.0,
            "ECONOMY",
            "2026-09-15T06:00:00+00:00",
            "2026-08-27T10:00:00+00:00",
            "ONE_WAY",
            None,
            None,
            None,
            "INR",
            "Economy",
            None,
            "bad-offer",
        ),
    )
    in_memory_db.commit()

    fares = get_fares(in_memory_db)

    assert len(fares) == 1
    assert fares[0].price_inr == 5000.0
    assert fares[0].source.source_name == valid.source.source_name
