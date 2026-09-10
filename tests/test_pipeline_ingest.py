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


def test_cleartrip_ui_arg_parser_has_ingest():
    parser = build_arg_parser()
    args = parser.parse_args(["--from", "DEL", "--to", "BOM", "--date", "12/09/2026", "--ingest"])
    assert args.ingest is True
    assert args.origin == "DEL"
    assert args.destination == "BOM"

    default_args = parser.parse_args(["--from", "DEL", "--to", "BOM", "--date", "12/09/2026"])
    assert default_args.ingest is False


def test_list_normalized_files():
    files = list_normalized_files("data/normalized/cleartrip")
    assert isinstance(files, list)
    assert len(files) >= 1
    sample = files[0]
    assert "file_name" in sample
    assert "file_path" in sample
    assert sample["source"] == "cleartrip"
    assert sample["route"]["origin"] == "DEL"
    assert sample["route"]["destination"] == "BOM"


def test_parse_normalized_payload():
    file_path = Path("data/normalized/cleartrip/cleartrip_flights_20260910T062546Z.json")
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    raw_records = parse_normalized_payload(payload)
    assert len(raw_records) >= 100
    sample = raw_records[0]
    assert sample["route"]["origin"] == "DEL"
    assert sample["route"]["destination"] == "BOM"
    assert sample["price_inr"] > 0
    assert sample["source"]["source_name"] == "ClearTrip"
    assert sample["source"]["source_url"].startswith("http")


def test_ingest_normalized_file(db):
    file_path = Path("data/normalized/cleartrip/cleartrip_flights_20260910T062546Z.json")
    res = ingest_normalized_file(file_path, conn=db, recompute_index=True)

    assert res["status"] == "success"
    assert res["raw_records_count"] == 174
    assert res["valid_fares"] > 0
    assert res["rejected_fares"] == 0
    assert res["new_fares_inserted"] >= 0


def test_ingest_normalized_directory(db):
    res = ingest_normalized_directory("data/normalized/cleartrip", conn=db, recompute_index=True)
    assert res["status"] == "success"
    assert res["files_processed"] >= 1
    assert res["total_valid_fares"] > 0


@pytest.mark.asyncio
async def test_dashboard_ingest_endpoints(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
