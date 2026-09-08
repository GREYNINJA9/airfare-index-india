"""Unit tests for MakeMyTrip scraper.

Tests the mock-based extraction logic deterministically without any network
access. All HTML strings are hand-authored mock data.
"""

import pytest

from models.fare import RawFareSource
from scraper.otas.mmt import MakeMyTripScraper


def test_mmt_scraper_extract_valid_html():
    """Valid mock HTML should produce one or more raw fare dictionaries."""
    scraper = MakeMyTripScraper()
    html = scraper._templates["del_bom_economy"]
    fares = scraper.extract(html)
    assert isinstance(fares, list)
    assert len(fares) >= 1
    for fare in fares:
        # Must be compatible with RawFareSource validation
        try:
            RawFareSource.model_validate(fare["source"])
        except Exception as e:
            pytest.fail(f"RawFareSource validation failed: {e}")
        assert fare["route"]["origin"] == "DEL"
        assert fare["route"]["destination"] == "BOM"
        assert fare["source"]["source_name"] == "MakeMyTrip"
        assert fare["source"]["source_type"] == "OTA"
        assert fare["source"]["raw_currency"] == "INR"


def test_mmt_scraper_skips_invalid_html():
    """Malformed or empty HTML should return empty list (safe failure)."""
    scraper = MakeMyTripScraper()
    assert scraper.extract("not a real page") == []
    assert scraper.extract("") == []
    # HTML with DEL-BOM route but missing price should be skipped
    bad_html = """
    <div class="flight-card" data-route="DEL-BOM">
        <span class="cabin">Economy</span>
        <a href="/flights">Book</a>
    </div>
    """
    assert scraper.extract(bad_html) == []


def test_mmt_scraper_multiple_fares():
    """Scraper should handle multiple flight cards in one HTML string."""
    scraper = MakeMyTripScraper()
    # Create HTML with two flight cards
    html = scraper._templates["del_bom_economy"] + scraper._templates["del_bom_economy"]
    fares = scraper.extract(html)
    assert len(fares) == 2
    # Second fare should have different offer_id
    offer_ids = {f["source"]["raw_offer_id"] for f in fares}
    assert len(offer_ids) == 2


def test_mmt_scraper_case_insensitive():
    """Scraper should handle case variations in mock data."""
    scraper = MakeMyTripScraper()
    # Modify template to use lowercase tags
    html = scraper._templates["del_bom_economy"].replace(
        'class="flight-card"', 'class="FLIGHT-CARD"'
    )
    fares = scraper.extract(html)
    assert len(fares) >= 1
    assert fares[0]["route"]["origin"] == "DEL"


def test_mmt_scraper_empty_returns_empty():
    """A fresh scraper instance should still work (no config required)."""
    scraper = MakeMyTripScraper()
    assert scraper.extract("") == []
    assert scraper.name == "MakeMyTrip"
    assert scraper.source_type.value == "OTA"
