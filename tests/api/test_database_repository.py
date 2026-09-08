"""Deterministic unit tests for database schema and repository.

Runs against the live PostgreSQL test database.
"""

from database.repository import (
    count_fares,
    get_fare_by_offer_id,
    get_fares,
    get_fares_by_route,
    insert_fares,
)
from models.fare import Fare
from tests.pipeline.test_fare_model import _valid_source  # noqa: F401, noqa: T001

# --- schema ---


def test_schema_creates_fares_table(db):
    """The schema creates the fares table with expected columns."""
    cur = db.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'fares'
        """
    )
    columns = {row["column_name"] for row in cur.fetchall()}
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


def test_schema_creates_indexes(db):
    """The schema creates useful indexes for queries."""
    cur = db.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'fares'")
    indexes = {row["indexname"] for row in cur.fetchall()}
    assert "idx_fares_route_origin" in indexes
    assert "idx_fares_route_destination" in indexes
    assert "idx_fares_scraped_at" in indexes


# --- insert ---


def test_insert_fares_returns_count(db):
    """Inserting fares returns the count inserted."""
    from tests.pipeline.test_fare_model import _valid_fare

    fare = _valid_fare()
    count = insert_fares(db, [fare])
    assert count == 1


def test_insert_fares_persists_to_db(db):
    """Inserted fares are retrievable from the DB."""
    from tests.pipeline.test_fare_model import _valid_fare

    fare = _valid_fare()
    insert_fares(db, [fare])
    assert count_fares(db) == 1


# --- query ---


def test_get_fares_by_route_returns_matching_rows(db):
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
    insert_fares(db, [f1, f2, other])

    rows = get_fares_by_route(db, "DEL", "BOM")
    assert len(rows) == 2
    assert rows[0]["price_inr"] == 5000.0
    assert rows[1]["price_inr"] == 6000.0


def test_get_fares_by_route_ordered_by_scraped_at(db):
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

    insert_fares(db, [later, earlier])

    rows = get_fares_by_route(db, "DEL", "BOM")
    assert rows[0]["scraped_at"] == "2026-08-27T10:00:00+00:00"
    assert rows[1]["scraped_at"] == "2026-08-28T12:00:00+00:00"


def test_get_fare_by_offer_id_returns_row(db):
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
    insert_fares(db, [fare])

    row = get_fare_by_offer_id(db, "TEST-ID-123")
    assert row is not None
    assert row["price_inr"] == 5000.0


def test_get_fares_skips_rows_with_null_provenance_fields(db):
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
    insert_fares(db, [valid])

    db.execute(
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

    fares = get_fares(db)

    assert len(fares) == 1
    assert fares[0].price_inr == 5000.0
    assert fares[0].source.source_name == valid.source.source_name
