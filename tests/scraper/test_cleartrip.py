"""Unit tests for ClearTrip OTA scraper.

Tests mirror the MMT pattern deterministically without network access.
"""

import pytest

from models.fare import RawFareSource, SourceType
from scraper.otas.cleartrip import _MOCK_FLIGHT_CARD, ClearTripScraper


def test_cleartrip_scraper_extract_valid_html():
    """Valid mock HTML should produce raw fare dictionaries."""
    scraper = ClearTripScraper()
    html = scraper._templates["del_bom_economy"]
    fares = scraper.extract(html)
    assert isinstance(fares, list)
    assert len(fares) >= 1
    for fare in fares:
        try:
            RawFareSource.model_validate(fare["source"])
        except Exception as e:
            pytest.fail(f"RawFareSource validation failed: {e}")
        assert fare["route"]["origin"] == "DEL"
        assert fare["route"]["destination"] == "BOM"
        assert fare["source"]["source_name"] == "ClearTrip"
        assert fare["source"]["source_type"] == "OTA"
        assert fare["source"]["raw_currency"] == "INR"


def test_cleartrip_scraper_skips_invalid_html():
    """Malformed or empty HTML should return empty list (safe failure)."""
    scraper = ClearTripScraper()
    assert scraper.extract("not a real page") == []
    assert scraper.extract("") == []
    bad_html = """
    <div class="flight-card" data-route="DEL-BOM">
        <span class="cabin">Economy</span>
        <a href="/flights">Book</a>
    </div>
    """
    assert scraper.extract(bad_html) == []


def test_cleartrip_scraper_multiple_fares():
    """Scraper should handle multiple flight cards."""
    scraper = ClearTripScraper()
    html = scraper._templates["del_bom_economy"] + scraper._templates["del_bom_economy"]
    fares = scraper.extract(html)
    assert len(fares) == 2
    offer_ids = {f["source"]["raw_offer_id"] for f in fares}
    assert len(offer_ids) == 2
    assert "CT-DEL-BOM-1" in offer_ids


def test_cleartrip_scraper_case_insensitive():
    """Scraper should handle case variations in mock data."""
    scraper = ClearTripScraper()
    html = scraper._templates["del_bom_economy"].replace(
        'class="flight-card"', 'class="FLIGHT-CARD"'
    )
    fares = scraper.extract(html)
    assert len(fares) >= 1
    assert fares[0]["route"]["origin"] == "DEL"


def test_cleartrip_scraper_empty_returns_empty():
    """A fresh scraper instance should still work (no config required)."""
    scraper = ClearTripScraper()
    assert scraper.extract("") == []
    assert scraper.name == "ClearTrip"
    assert scraper.source_type == SourceType.OTA


def test_cleartrip_scraper_validates_price_airline_cabin():
    """Each record must contain required fields with correct types."""
    scraper = ClearTripScraper()
    fares = scraper.extract(_MOCK_FLIGHT_CARD)
    assert len(fares) == 1
    f = fares[0]
    assert isinstance(f["price_inr"], float)
    assert f["price_inr"] > 0
    assert f["airline_code"] == "AI"
    assert f["cabin_class"] == "ECONOMY"
    assert f["trip_type"] == "ONE_WAY"
    assert f["route"]["distance_km"] == 1138.0
    assert f["departure_at"] == "2026-09-15T08:30:00+00:00"
    assert f["scraped_at"] == "2026-08-27T10:00:00+00:00"
    assert (
        f["source"]["source_url"]
        == "https://www.cleartrip.com/flights/DEL-BOM/2026-09-15"
    )
    assert f["source"]["raw_offer_id"] == "CT-DEL-BOM-1"
