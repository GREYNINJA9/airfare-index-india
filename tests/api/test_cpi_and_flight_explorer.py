"""Unit and integration tests for MoSPI CPI Client and Route/Flight Explorer."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from dashboard.flight_explorer import get_available_routes, get_route_flight_details
from index_engine.cpi_client import fetch_cpi_data, get_cpi_api_config, get_cpi_options


def test_cpi_config_and_options():
    cfg = get_cpi_api_config()
    assert "https://api.mospi.gov.in" in cfg["base_url"]
    assert cfg["base_year"] == "2024"
    assert cfg["item_code"] == "07.3.3"

    opts = get_cpi_options()
    assert 2026 in opts["available_years"]
    assert 2025 in opts["available_years"]
    codes = [item["code"] for item in opts["common_items"]]
    assert "07.3.3" in codes
    assert "07.3" in codes


def test_fetch_cpi_data_structure():
    data = fetch_cpi_data(year=2026, item_code="07.3.3")
    assert data["status"] == "success"
    assert data["source_mode"] in ("live_mospi_api", "cache", "fallback_generated")
    assert "summary" in data
    assert data["summary"]["item_code"] == "07.3.3"
    assert "records" in data
    assert isinstance(data["records"], list)
    if data["records"]:
        rec = data["records"][0]
        assert "year" in rec
        assert "index" in rec


def test_fetch_cpi_data_year_and_sector_filter():
    d_2025 = fetch_cpi_data(year=2025, item_code="07.3.3")
    assert d_2025["status"] == "success"
    assert d_2025["summary"]["year"] == "2025"

    d_urban = fetch_cpi_data(year=2026, item_code="07.3.3", sector="Urban")
    assert d_urban["status"] == "success"
    for r in d_urban["records"]:
        assert r["sector"].lower() == "urban"


def test_flight_explorer_available_routes():
    routes = get_available_routes()
    assert len(routes) >= 10
    sectors = [r["sector"] for r in routes]
    assert "DEL-BOM" in sectors
    assert "BOM-BLR" in sectors


def test_flight_explorer_route_details():
    details = get_route_flight_details("DEL", "BOM")
    assert details["status"] == "success"
    assert details["route"]["sector"] == "DEL-BOM"
    assert details["summary"]["total_route_quotes"] > 0
    assert details["summary"]["median_fare_inr"] > 0
    assert details["summary"]["dgca_benchmark_fare_inr"] == 5450.0
    assert len(details["carriers"]) > 0
    assert len(details["flights"]) > 0

    # Test filtering by airline
    details_6e = get_route_flight_details("DEL", "BOM", airline_code="6E")
    assert all(f["airline_code"] == "6E" for f in details_6e["flights"])

    # Test sorting by price desc
    details_desc = get_route_flight_details("DEL", "BOM", sort_by="price_desc", limit=5)
    prices = [f["price_inr"] for f in details_desc["flights"]]
    assert prices == sorted(prices, reverse=True)


@pytest.mark.asyncio
async def test_dashboard_routes_and_flights_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_routes = await client.get("/dashboard/api/routes")
        assert r_routes.status_code == 200
        assert len(r_routes.json()) >= 10

        r_flights = await client.get("/dashboard/api/route-flights?origin=DEL&destination=BOM&limit=5")
        assert r_flights.status_code == 200
        data = r_flights.json()
        assert data["status"] == "success"
        assert 0 < len(data["flights"]) <= 5


@pytest.mark.asyncio
async def test_dashboard_cpi_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_opt = await client.get("/dashboard/api/cpi/options")
        assert r_opt.status_code == 200
        assert "available_years" in r_opt.json()

        r_cpi = await client.get("/dashboard/api/cpi?year=2026&item_code=07.3.3")
        assert r_cpi.status_code == 200
        data = r_cpi.json()
        assert data["status"] == "success"
        assert "records" in data

        r_analytics = await client.get("/api/analytics/cpi-mospi?year=2026&item_code=07.3.3")
        assert r_analytics.status_code == 200
        assert r_analytics.json()["status"] == "success"


@pytest.mark.asyncio
async def test_dashboard_html_contains_new_features():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        html = res.text

        # 1. Help button & Layman modal
        assert "Help &amp; Terms (Layman Guide)" in html or "Help & Terms (Layman Guide)" in html
        assert "help-modal" in html
        assert "GLOSSARY_TERMS" in html
        assert "Laspeyres" in html
        assert "Jevons" in html

        # 2. MoSPI CPI Overview Comparison
        assert "Official MoSPI CPI" in html
        assert "overview-cpi-comp-apix" in html
        assert "Official MoSPI CPI (Item 07.3.3) vs High-Frequency APIx Comparison" in html
        assert "Evaluation Dimension" in html

        # 3. MoSPI CPI Explorer Tab
        assert "tab-cpi-explorer" in html
        assert "cpi-year-select" in html
        assert "cpi-item-select" in html
        assert "Fetch Official CPI Data" in html

        # 4. Confirm removed tabs are absent
        assert "tab-flight-explorer" not in html
        assert "tab-composition" not in html
        assert "tab-volatility" not in html
        assert "tab-basket" not in html
