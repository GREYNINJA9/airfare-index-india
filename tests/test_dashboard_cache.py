"""Unit tests for repository caching and dashboard speed optimizations."""

from unittest.mock import MagicMock

from database.repository import (
    get_fares,
    invalidate_fares_cache,
    invalidate_index_cache,
)


def test_invalidate_fares_cache():
    invalidate_fares_cache()
    from database import repository
    assert repository._FARES_CACHE is None
    assert repository._FARES_CACHE_TIME == 0.0

def test_invalidate_index_cache():
    invalidate_index_cache()
    from database import repository
    assert repository._INDEX_CACHE is None
    assert repository._INDEX_CACHE_TIME == 0.0

def test_get_fares_uses_cache_on_second_call():
    fake_conn = MagicMock()
    fake_conn.execute.return_value.fetchall.return_value = [
        {
            "route_origin": "DEL",
            "route_destination": "BOM",
            "route_distance_km": 1138.0,
            "airline_code": "6E",
            "price_inr": 5400.0,
            "cabin_class": "ECONOMY",
            "departure_at": "2026-09-10T10:00:00+00:00",
            "scraped_at": "2026-09-08T10:00:00+00:00",
            "trip_type": "ONE_WAY",
            "source_name": "IndiGo",
            "source_type": "AIRLINE",
            "raw_price": 5400.0,
            "raw_currency": "INR",
            "raw_cabin_label": "Economy",
            "source_url": "https://goindigo.in",
            "raw_offer_id": "TEST-1",
        }
    ]

    invalidate_fares_cache()

    # First call hits fake_conn
    fares1 = get_fares(fake_conn)
    assert len(fares1) == 1
    assert fake_conn.execute.call_count == 1

    # Second call uses in-memory cache without hitting conn.execute again
    fares2 = get_fares(fake_conn)
    assert len(fares2) == 1
    assert fake_conn.execute.call_count == 1

    # Invalidate clears cache
    invalidate_fares_cache()
    fares3 = get_fares(fake_conn)
    assert len(fares3) == 1
    assert fake_conn.execute.call_count == 2
