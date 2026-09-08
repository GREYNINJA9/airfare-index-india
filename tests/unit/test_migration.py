"""Unit test for SQLite to PostgreSQL migration script logic."""

import sqlite3
from datetime import datetime, timezone

from database.repository import insert_fare
from database.schema import init_sqlite_schema
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.route import Route
from scripts.migrate_sqlite_to_pg import migrate_fares


class MockPgCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 0

    def mogrify(self, sql, args):
        return sql.encode("utf-8")

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return [len(self.executed)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPgConnection:
    def __init__(self):
        self.cursor_obj = MockPgCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_migrate_fares_from_sqlite():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_sqlite_schema(conn)

    s = RawFareSource(
        source_name="TestOTA",
        source_type=SourceType.OTA,
        raw_price=4500.0,
        raw_currency="INR",
        raw_cabin_label="Economy",
        raw_offer_id="MIGRATE-OFFER-1",
    )
    f = Fare(
        route=Route(origin="DEL", destination="BOM", distance_km=1148.0),
        airline_code="6E",
        price_inr=4500.0,
        cabin_class=CabinClass.ECONOMY,
        departure_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        scraped_at=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        trip_type=TripType.ONE_WAY,
        source=s,
    )
    insert_fare(conn, f)

    mock_pg = MockPgConnection()
    count = migrate_fares(conn, mock_pg)

    assert count == 1
    assert mock_pg.committed is True
    conn.close()
