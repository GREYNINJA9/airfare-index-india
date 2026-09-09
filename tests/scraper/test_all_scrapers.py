"""Unit tests verifying all 10 scrapers (5 Airlines and 5 OTAs)."""

from __future__ import annotations

import pytest

from models.fare import SourceType
from models.route import Route
from scraper.airlines.air_india import AirIndiaScraper
from scraper.airlines.air_india_express import AirIndiaExpressScraper
from scraper.airlines.akasa import AkasaScraper
from scraper.airlines.indigo import IndiGoScraper
from scraper.airlines.spicejet import SpiceJetScraper
from scraper.otas.cleartrip import ClearTripScraper
from scraper.otas.easemytrip import EaseMyTripScraper
from scraper.otas.ixigo import IxigoScraper
from scraper.otas.mmt import MakeMyTripScraper
from scraper.otas.yatra import YatraScraper

ALL_SCRAPERS = [
    (MakeMyTripScraper, "MakeMyTrip", SourceType.OTA),
    (ClearTripScraper, "ClearTrip", SourceType.OTA),
    (EaseMyTripScraper, "EaseMyTrip", SourceType.OTA),
    (IxigoScraper, "Ixigo", SourceType.OTA),
    (YatraScraper, "Yatra", SourceType.OTA),
    (IndiGoScraper, "IndiGo", SourceType.AIRLINE),
    (AirIndiaScraper, "Air India", SourceType.AIRLINE),
    (AirIndiaExpressScraper, "Air India Express", SourceType.AIRLINE),
    (AkasaScraper, "Akasa Air", SourceType.AIRLINE),
    (SpiceJetScraper, "SpiceJet", SourceType.AIRLINE),
]


@pytest.mark.parametrize("cls,expected_name,expected_type", ALL_SCRAPERS)
def test_scraper_properties_and_safe_failure(cls, expected_name, expected_type):
    scraper = cls()
    assert scraper.name == expected_name
    assert scraper.source_type == expected_type

    # Safe failure mode on broken HTML: should return [] without raising
    assert scraper.extract("<div>No flight data</div>") == []
    assert scraper.extract("") == []


@pytest.mark.parametrize("cls,expected_name,expected_type", ALL_SCRAPERS)
def test_scraper_mock_extraction(cls, expected_name, expected_type):
    scraper = cls()
    template = getattr(scraper, "_templates", {}).get("del_bom_economy")
    assert template is not None, f"{cls.__name__} must define del_bom_economy template"

    route = Route(origin="DEL", destination="BOM")
    records = scraper.extract(template, route=route)

    assert len(records) >= 1
    rec = records[0]
    assert rec["route"]["origin"] == "DEL"
    assert rec["route"]["destination"] == "BOM"
    assert rec["price_inr"] > 0
    assert rec["cabin_class"] == "ECONOMY"
    assert rec["source"]["source_name"] == expected_name
    assert rec["source"]["source_type"] == expected_type.value
