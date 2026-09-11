"""Unit and integration tests for Scraped Fare Pipeline Ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from cleartrip_ui import build_arg_parser
from pipeline.ingest import (
    ingest_normalized_directory,
    ingest_normalized_file,
    list_normalized_files,
    parse_normalized_payload,
)


def _ensure_cleartrip_fixture() -> Path:
    """Ensure at least one valid Cleartrip normalized fixture is present on disk."""
    dir_path = Path("data/normalized/cleartrip")
    dir_path.mkdir(parents=True, exist_ok=True)
    candidates = sorted(dir_path.glob("*.json"))
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if (
                payload.get("source") == "cleartrip"
                and len(payload.get("flights", [])) >= 100
            ):
                return candidate
        except Exception:
            continue

    fixture_path = dir_path / "cleartrip_flights_fixture.json"
    flights = []
    for i in range(120):
        carrier = ["6E", "AI", "IX", "QP", "SG"][i % 5]
        flight_obj = {
            "source": "cleartrip",
            "airline_code": carrier,
            "flight_number": str(100 + i),
            "route": {"origin": "DEL", "destination": "BLR"},
            "departure": {
                "datetime": f"2026-09-16T{8 + (i % 12):02d}:30:00+05:30",
                "date": "16/09/2026",
                "time": f"{8 + (i % 12):02d}:30",
                "airport": "DEL",
                "terminal": None,
                "gate": None,
                "timezone": None,
            },
            "arrival": {
                "datetime": f"2026-09-16T{11 + (i % 12):02d}:15:00+05:30",
                "date": "16/09/2026",
                "time": f"{11 + (i % 12):02d}:15",
                "airport": "BLR",
                "terminal": None,
                "gate": None,
                "timezone": None,
            },
            "duration": "2h 45m",
            "stops": 0,
            "flight_chain": [],
            "pricing": {
                "total_inr": 5000.0 + (i * 25.0),
                "base_fare_inr": 4200.0 + (i * 20.0),
                "taxes_fees_inr": 800.0 + (i * 5.0),
                "currency": "INR",
                "raw_label": "Economy Standard",
            },
            "cabin_class": "ECONOMY",
            "fare_offers": [
                {
                    "offer_id": f"CT-{carrier}-{100 + i}-OFFER1",
                    "cabin_class": "ECONOMY",
                    "total_inr": 5000.0 + (i * 25.0),
                    "base_fare_inr": 4200.0 + (i * 20.0),
                    "taxes_fees_inr": 800.0 + (i * 5.0),
                    "fare_type": "STANDARD",
                }
            ],
        }
        flights.append(flight_obj)

    payload = {
        "source": "cleartrip",
        "route": {"origin": "DEL", "destination": "BLR"},
        "departure_date": "16/09/2026",
        "flight_count": len(flights),
        "flights": flights,
        "captured_at_utc": "20260909T053756Z",
    }
    fixture_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return fixture_path


def _normalized_cleartrip_fixture() -> Path:
    """Return the current committed non-empty Cleartrip normalized fixture."""
    return _ensure_cleartrip_fixture()


@pytest.fixture(autouse=True)
def ensure_fixture():
    _ensure_cleartrip_fixture()


def test_cleartrip_ui_arg_parser_has_ingest():
    parser = build_arg_parser()
    args = parser.parse_args(
        ["--from", "DEL", "--to", "BOM", "--date", "12/09/2026", "--ingest"]
    )
    assert args.ingest is True
    assert args.origin == "DEL"
    assert args.destination == "BOM"

    default_args = parser.parse_args(
        ["--from", "DEL", "--to", "BOM", "--date", "12/09/2026"]
    )
    assert default_args.ingest is False


def test_list_normalized_files():
    _ensure_cleartrip_fixture()
    files = list_normalized_files("data/normalized/cleartrip")
    assert isinstance(files, list)
    assert len(files) >= 1
    sample = next(item for item in files if item.get("flight_count", 0) > 0)
    assert "file_name" in sample
    assert "file_path" in sample
    assert sample["source"] == "cleartrip"
    assert sample["route"]["origin"] == "DEL"
    assert sample["route"]["destination"] == "BLR"


def test_parse_normalized_payload():
    file_path = _normalized_cleartrip_fixture()
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    raw_records = parse_normalized_payload(payload)
    assert len(raw_records) >= 100
    sample = raw_records[0]
    assert sample["route"]["origin"] == "DEL"
    assert sample["route"]["destination"] == "BLR"
    assert sample["price_inr"] > 0
    assert sample["source"]["source_name"] == "ClearTrip"
    assert sample["source"]["source_url"].startswith("http")


def test_ingest_normalized_file(db):
    file_path = _normalized_cleartrip_fixture()
    res = ingest_normalized_file(file_path, conn=db, recompute_index=True)

    assert res["status"] == "success"
    assert res["raw_records_count"] >= 100
    assert res["valid_fares"] > 0
    assert res["rejected_fares"] == 0
    assert res["new_fares_inserted"] >= 0


def test_ingest_normalized_directory(db):
    res = ingest_normalized_directory(
        "data/normalized/cleartrip", conn=db, recompute_index=True
    )
    assert res["status"] == "success"
    assert res["files_processed"] >= 1
    assert res["total_valid_fares"] > 0


@pytest.mark.asyncio
async def test_dashboard_ingest_endpoints(db):
    _ensure_cleartrip_fixture()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_list = await client.get("/dashboard/api/pipeline/pending-scrapes")
        assert r_list.status_code == 200
        data = r_list.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        r_post = await client.post("/dashboard/api/pipeline/ingest")
        assert r_post.status_code == 200
        post_data = r_post.json()
        assert post_data["status"] == "success"
        assert post_data["total_valid_fares"] > 0
