"""Unit tests for Cleartrip live scraper adapter and parser.

These tests run entirely in-memory and deterministically using captured
Cleartrip JSON fixtures. No live network requests are made.

Tests:
- direct itinerary parsing
- connecting itinerary parsing
- multiple fares per flight
- datetime preservation
- overnight flight date rollover
- stops and flight chain integrity
- terminal and timezone extraction
- fare class and available seats
- malformed response handling
- missing fare handling
- security challenge classification
- pipeline raw record conversion and validation
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from cleartrip_ui import classify_page, parse_v2_response
from models.fare import Fare, SourceType
from pipeline import process_raw_fares
from scheduler.search import SearchJob
from scraper.otas.cleartrip_live import (
    ClearTripLiveScraper,
    _deterministic_offer_id,
    flight_to_raw_records,
)

FIXTURE_PATH = Path("data/raw/cleartrip/cleartrip_raw_20260909T053756Z.json")


@pytest.fixture(scope="module")
def captured_v2_payload() -> dict:
    """Load the captured /flight/search/v2 response from the repository fixture."""
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Captured fixture not found at {FIXTURE_PATH}")
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    v2 = data.get("responses", {}).get("flight_search_v2")
    if not v2:
        pytest.skip("Fixture has no flight_search_v2 response")
    return v2


def test_cleartrip_direct_itinerary(captured_v2_payload):
    """Direct flight keeps 0 stops, one-leg chain, valid route, and departure."""
    parsed = parse_v2_response(captured_v2_payload, "DEL", "BLR", "16/09/2026")
    flights = parsed["flights"]
    assert len(flights) > 0

    direct = [f for f in flights if f["stops"] == 0]
    assert len(direct) > 0, "Expected at least one direct flight"

    f0 = direct[0]
    assert f0["route"]["origin"] == "DEL"
    assert f0["route"]["destination"] == "BLR"
    assert f0["stops"] == 0
    assert len(f0["flight_chain"]) == 1
    assert f0["airline_code"] is not None
    assert f0["flight_number"] is not None
    assert f0["departure"]["datetime"] is not None
    assert f0["arrival"]["datetime"] is not None
    assert f0["duration"] is not None
    assert len(f0["fares"]) >= 1
    assert f0["fares"][0]["total_price"] > 0


def test_cleartrip_connecting_itinerary(captured_v2_payload):
    """Connecting itinerary preserves layover legs and intermediate airports."""
    parsed = parse_v2_response(captured_v2_payload, "DEL", "BLR", "16/09/2026")
    connecting = [f for f in parsed["flights"] if f["stops"] > 0]
    assert len(connecting) > 0, "Expected connecting flights in capture"

    c0 = connecting[0]
    assert c0["stops"] >= 1
    assert len(c0["flight_chain"]) >= 2

    # First leg originates at DEL; final leg arrives at BLR
    assert c0["flight_chain"][0]["origin"] == "DEL"
    assert c0["flight_chain"][-1]["destination"] == "BLR"

    # Intermediate transfer point exists
    intermediate = c0["flight_chain"][0]["destination"]
    assert intermediate != "BLR"
    assert c0["flight_chain"][1]["origin"] == intermediate


def test_cleartrip_overnight_flight(captured_v2_payload):
    """Overnight flights keep correct date rollover across midnight."""
    parsed = parse_v2_response(captured_v2_payload, "DEL", "BLR", "16/09/2026")
    overnight = [
        f
        for f in parsed["flights"]
        if f["departure"]["datetime"][:10] != f["arrival"]["datetime"][:10]
    ]
    assert len(overnight) > 0, "Expected overnight flights in capture"

    o0 = overnight[0]
    dep_dt = datetime.fromisoformat(o0["departure"]["datetime"])
    arr_dt = datetime.fromisoformat(o0["arrival"]["datetime"])
    assert arr_dt > dep_dt
    assert arr_dt.date() > dep_dt.date()


def test_cleartrip_terminal_and_timezone_extraction(captured_v2_payload):
    """Terminals and timezones are preserved when exposed by Cleartrip."""
    parsed = parse_v2_response(captured_v2_payload, "DEL", "BLR", "16/09/2026")
    flights = parsed["flights"]

    # At least some flights should have terminal information
    has_terminal = [
        f
        for f in flights
        if f["departure"].get("terminal") or f["arrival"].get("terminal")
    ]
    assert len(has_terminal) > 0  # At least some flights should have terminal info

    # Timezones where present should be preserved
    has_tz = [
        f
        for f in flights
        if f["departure"].get("timezone") or f["arrival"].get("timezone")
    ]
    assert len(has_tz) > 0


def test_cleartrip_multiple_fares():
    """A flight with multiple fare options yields multiple raw records."""
    mock_flight = {
        "route": {"origin": "DEL", "destination": "BLR"},
        "airline_code": "6E",
        "flight_number": "501",
        "travel_option_id": "6E-501-DEL-BLR-123456",
        "departure": {"datetime": "2026-09-16T08:00:00+05:30", "terminal": "T3"},
        "arrival": {"datetime": "2026-09-16T10:45:00+05:30", "terminal": "T1"},
        "duration": "2h 45m",
        "stops": 0,
        "flight_chain": [],
        "fares": [
            {
                "fare_id": "SAVER_123",
                "total_price": 5400.0,
                "base_fare": 4200.0,
                "tax": 1200.0,
                "currency": "INR",
                "display_title": "Saver",
                "fare_family_subtype": "SAVER",
                "flight_fare": [{"fare_class": "E", "available_seat_count": 4}],
            },
            {
                "fare_id": "FLEXI_456",
                "total_price": 6800.0,
                "base_fare": 5600.0,
                "tax": 1200.0,
                "currency": "INR",
                "display_title": "Flexi Plus",
                "fare_family_subtype": "FLEXI",
                "flight_fare": [{"fare_class": "Y", "available_seat_count": 9}],
            },
        ],
    }

    job = SearchJob(
        source="cleartrip", origin="DEL", destination="BLR", departure_date="2026-09-16"
    )
    records = flight_to_raw_records(mock_flight, job=job)
    assert len(records) == 2

    assert records[0]["price_inr"] == 5400.0
    assert records[0]["source"]["raw_cabin_label"] == "Saver"
    assert records[0]["fare_class"] == "E"
    assert records[0]["available_seats"] == 4

    assert records[1]["price_inr"] == 6800.0
    assert records[1]["source"]["raw_cabin_label"] == "Flexi Plus"
    assert records[1]["fare_class"] == "Y"
    assert records[1]["available_seats"] == 9

    # Unique offer IDs
    assert records[0]["source"]["raw_offer_id"] != records[1]["source"]["raw_offer_id"]

    # Both pass pipeline
    fares, bad, err = process_raw_fares(records)
    assert err is None and not bad
    assert len(fares) == 2


def test_cleartrip_malformed_response_safe_failure():
    """Malformed or non-dict payloads return [] safely without exceptions."""
    scraper = ClearTripLiveScraper()
    job = SearchJob(
        source="cleartrip", origin="DEL", destination="BLR", departure_date="2026-09-16"
    )

    assert scraper.extract_v2({}, job=job) == []
    assert scraper.extract_v2({"cards": None}, job=job) == []
    assert scraper.extract_v2({"cards": {"J1": "corrupt"}}, job=job) == []
    assert scraper.extract_v2("not a dict", job=job) == []


def test_cleartrip_missing_fare_skipped():
    """Flight record with no fares or 0 price produces no raw fare records."""
    mock_flight = {
        "route": {"origin": "DEL", "destination": "BLR"},
        "airline_code": "6E",
        "flight_number": "101",
        "departure": {"datetime": "2026-09-16T08:00:00+05:30"},
        "fares": [],
        "cheapest_fare": None,
    }
    records = flight_to_raw_records(mock_flight)
    assert records == []

    mock_flight_zero_price = {
        "route": {"origin": "DEL", "destination": "BLR"},
        "airline_code": "6E",
        "flight_number": "101",
        "departure": {"datetime": "2026-09-16T08:00:00+05:30"},
        "fares": [{"total_price": 0.0, "currency": "INR"}],
    }
    records2 = flight_to_raw_records(mock_flight_zero_price)
    assert records2 == []


def test_cleartrip_security_challenge_classification():
    """Classification detects security challenges and ignores normal content."""
    assert classify_page("Please complete the captcha below to proceed") == "CAPTCHA"
    assert classify_page("Cloudflare Turnstile - verify you are human") == "TURNSTILE"
    assert (
        classify_page("403 Forbidden - Request Blocked Access Denied")
        == "ACCESS_DENIED"
    )
    assert (
        classify_page("Checking your browser before accessing cleartrip...")
        == "SECURITY_CHECK"
    )
    assert classify_page("Welcome to Cleartrip Flight Search results") is None


def test_deterministic_offer_id_length_bound():
    """Offer ID must be bounded to <= 200 characters even with huge fare IDs."""
    huge_fare_id = "X" * 500
    offer_id = _deterministic_offer_id("6E-101-DEL-BLR", huge_fare_id, 0)
    assert len(offer_id) <= 200
    assert offer_id.startswith("CT-")


def test_adapter_extract_v2_to_pipeline_to_fare(captured_v2_payload):
    """Full adapter extraction of captured fixture through process_raw_fares."""
    scraper = ClearTripLiveScraper()
    job = SearchJob(
        source="cleartrip", origin="DEL", destination="BLR", departure_date="2026-09-16"
    )

    raw_records = scraper.extract_v2(captured_v2_payload, job=job)
    assert len(raw_records) > 0

    fares, bad, batch_err = process_raw_fares(raw_records)
    assert batch_err is None, f"Batch validation failed: {batch_err}"
    assert len(bad) == 0, f"Bad records: {bad[:2]}"
    assert len(fares) == len(raw_records)

    # Validate Fare domain properties
    f = fares[0]
    assert isinstance(f, Fare)
    assert f.route.origin == "DEL"
    assert f.route.destination == "BLR"
    assert f.price_inr > 0
    assert f.source.source_name == "ClearTrip"
    assert f.source.source_type == SourceType.OTA
    assert f.source.raw_currency == "INR"
    assert f.departure_at.tzinfo is not None
    assert f.scraped_at.tzinfo is not None
