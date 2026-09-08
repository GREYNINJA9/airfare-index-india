"""Integration tests for Analytics and Dashboard endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.main import app


@pytest.mark.asyncio
async def test_dashboard_html_serves():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/dashboard")
        assert res.status_code == 200
        assert "APIx India" in res.text
        assert "Problem ID: 26056" in res.text

        # Root route also serves dashboard
        root_res = await client.get("/")
        assert root_res.status_code == 200
        assert "APIx India" in root_res.text


@pytest.mark.asyncio
async def test_dashboard_kpis_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/dashboard/api/kpis")
        assert res.status_code == 200
        data = res.json()
        assert "apix_laspeyres" in data
        assert "apix_jevons" in data
        assert "pipeline_health" in data


@pytest.mark.asyncio
async def test_dashboard_charts_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/dashboard/api/charts")
        assert res.status_code == 200
        data = res.json()
        assert "trend" in data
        assert "elasticity" in data
        assert "carrier" in data
        assert "backtest" in data


@pytest.mark.asyncio
async def test_sector_heatmap_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/analytics/sector-heatmap")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_lead_time_elasticity_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/analytics/lead-time-elasticity")
        assert res.status_code == 200
        data = res.json()
        assert "overall_curve" in data
        assert "route_curves" in data
        assert "market_elasticity_coefficient" in data


@pytest.mark.asyncio
async def test_dgca_backtest_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/analytics/dgca-backtest")
        assert res.status_code == 200
        data = res.json()
        assert data["total_backtest_days"] >= 30
        assert data["pearson_correlation"] >= 0.8
        assert len(data["daily_series"]) >= 30


@pytest.mark.asyncio
async def test_rbi_nso_feed_endpoint(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # JSON test
        res_json = await client.get("/api/analytics/rbi-nso-feed?format=json")
        assert res_json.status_code == 200
        assert res_json.json()["institution"] == "MoSPI / RBI High-Frequency Data Feed"

        # CSV test
        res_csv = await client.get("/api/analytics/rbi-nso-feed?format=csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]


@pytest.mark.asyncio
async def test_fares_summary_and_sectors(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sum_res = await client.get("/api/fares/summary")
        assert sum_res.status_code == 200
        assert "total_observations" in sum_res.json()

        sec_res = await client.get("/api/fares/sectors")
        assert sec_res.status_code == 200
        assert isinstance(sec_res.json(), list)
