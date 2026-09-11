"""Dashboard Web Application & API Controller.

Serves the interactive web-based dashboard and UI endpoints for the
Real-time Airfare Price Index (APIx) platform.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from dashboard.charts import (
    get_backtest_chart_data,
    get_carrier_chart_data,
    get_elasticity_chart_data,
    get_trend_chart_data,
)
from dashboard.components import get_dashboard_kpis
from dashboard.heatmap import get_heatmap_matrix

router = APIRouter(tags=["Dashboard"])

_CHARTS_CACHE = None
_CHARTS_CACHE_TIME = 0.0
_CHARTS_CACHE_TTL = 3600.0

_HEATMAP_CACHE = None
_HEATMAP_CACHE_TIME = 0.0
_HEATMAP_CACHE_TTL = 3600.0

_INITIAL_PAYLOADS = None
_INITIAL_PAYLOADS_LOCK = threading.Lock()


@router.get("/dashboard/api/kpis")
def dashboard_kpis(refresh: bool = False):
    """Return live KPI scorecards for dashboard dynamic refresh."""
    if refresh:
        from dashboard.components import invalidate_kpi_cache
        invalidate_kpi_cache()
    return get_dashboard_kpis()


@router.get("/dashboard/api/charts")
def dashboard_charts(refresh: bool = False):
    """Return all chart payloads in a single structured JSON response."""
    global _CHARTS_CACHE, _CHARTS_CACHE_TIME
    now = time.time()
    if not refresh and _CHARTS_CACHE is not None and (now - _CHARTS_CACHE_TIME) < _CHARTS_CACHE_TTL:
        return _CHARTS_CACHE

    payload = {
        "trend": get_trend_chart_data(),
        "elasticity": get_elasticity_chart_data(),
        "carrier": get_carrier_chart_data(),
        "backtest": get_backtest_chart_data(),
    }
    _CHARTS_CACHE = payload
    _CHARTS_CACHE_TIME = time.time()
    return payload


@router.get("/dashboard/api/heatmap")
def dashboard_heatmap(refresh: bool = False):
    """Return sector heatmap matrix data."""
    global _HEATMAP_CACHE, _HEATMAP_CACHE_TIME
    now = time.time()
    if not refresh and _HEATMAP_CACHE is not None and (now - _HEATMAP_CACHE_TIME) < _HEATMAP_CACHE_TTL:
        return _HEATMAP_CACHE

    payload = get_heatmap_matrix()
    _HEATMAP_CACHE = payload
    _HEATMAP_CACHE_TIME = time.time()
    return payload


def prewarm_dashboard() -> None:
    """Build the initial dashboard payloads in the background."""
    global _INITIAL_PAYLOADS
    try:
        from dashboard.blueprint_service import get_blueprint_data
        from dashboard.flight_explorer import (
            get_available_routes,
            get_route_flight_details,
        )
        from index_engine.cpi_client import fetch_cpi_data, get_cpi_options

        payloads = {
            "kpis": dashboard_kpis(),
            "charts": dashboard_charts(),
            "heatmap": dashboard_heatmap(),
            "routes": get_available_routes(),
            "flights": get_route_flight_details("ALL", "ALL", limit=300),
            "cpi_options": get_cpi_options(),
            "cpi": fetch_cpi_data(year=2026, item_code="07.3.3"),
            "blueprint": get_blueprint_data(),
        }
        with _INITIAL_PAYLOADS_LOCK:
            _INITIAL_PAYLOADS = payloads
    except Exception:
        return


def _initial_payloads():
    with _INITIAL_PAYLOADS_LOCK:
        return _INITIAL_PAYLOADS


@router.get("/dashboard/api/routes")
def dashboard_routes():
    """Return all available routes with flight counts and airport labels."""
    from dashboard.flight_explorer import get_available_routes
    return get_available_routes()


@router.get("/dashboard/api/route-flights")
def dashboard_route_flights(
    origin: str = "DEL",
    destination: str = "BOM",
    airline_code: Optional[str] = None,
    lead_window: Optional[str] = None,
    sort_by: Optional[str] = "price_asc",
    limit: int = 100,
):
    """Return comprehensive route stats and individual flight quotes."""
    from dashboard.flight_explorer import get_route_flight_details
    return get_route_flight_details(
        origin=origin,
        destination=destination,
        airline_code=airline_code,
        lead_window=lead_window,
        sort_by=sort_by,
        limit=limit,
    )


@router.get("/dashboard/api/cpi")
def dashboard_cpi_data(
    year: Optional[int] = 2026,
    item_code: Optional[str] = "07.3.3",
    base_year: Optional[int] = 2024,
    group_code: Optional[int] = 24,
    class_code: Optional[int] = 58,
    limit: Optional[int] = 100,
    sector: Optional[str] = None,
    refresh: bool = False,
):
    """Fetch live or cached CPI data with selectable year and item/index."""
    from index_engine.cpi_client import fetch_cpi_data
    return fetch_cpi_data(
        year=year,
        item_code=item_code,
        base_year=base_year,
        group_code=group_code,
        class_code=class_code,
        limit=limit,
        sector=sector,
        force_refresh=refresh,
    )


@router.get("/dashboard/api/cpi/options")
def dashboard_cpi_options():
    """Return selectable CPI choices for years and index items."""
    from index_engine.cpi_client import get_cpi_options
    return get_cpi_options()


@router.get("/dashboard/api/blueprint")
def dashboard_blueprint(refresh: bool = False):
    """Return comprehensive data payload powering all 13 sections of the blueprint."""
    from dashboard.blueprint_service import get_blueprint_data
    return get_blueprint_data(force_refresh=refresh)


@router.get("/dashboard/api/pipeline/pending-scrapes")
def get_pending_scrapes():
    """List available scraped files in data/normalized/."""
    from pipeline.ingest import list_normalized_files
    return list_normalized_files()


@router.post("/dashboard/api/pipeline/ingest")
def trigger_pipeline_ingest(file_path: Optional[str] = None):
    """Ingest scraped files from data/normalized/cleartrip or a specific file path,
    or run a collection cycle to scrape, process, and persist data."""
    from pipeline.ingest import ingest_normalized_directory, ingest_normalized_file
    if file_path:
        return ingest_normalized_file(file_path)
    res = ingest_normalized_directory()
    if res.get("files_processed", 0) == 0:
        try:
            from scheduler.jobs import run_collection_cycle
            cycle_res = run_collection_cycle()
            res["collection_cycle"] = cycle_res
            from pipeline.ingest import invalidate_all_caches
            invalidate_all_caches()
        except Exception as exc:
            res["collection_cycle_error"] = str(exc)
    return res


@router.get("/dashboard/static/chart.umd.min.js")
def get_chart_js():
    """Serve bundled Chart.js UMD distribution for fast, reliable client-side rendering."""
    from fastapi.responses import FileResponse
    import os
    file_path = os.path.join(os.path.dirname(__file__), "static", "chart.umd.min.js")
    return FileResponse(file_path, media_type="application/javascript")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the complete, modern, interactive executive Airfare Price Index dashboard."""
    with open(__file__.replace("app.py", "template.html"), "r", encoding="utf-8") as f:
        html_content = f.read()

    payloads = _initial_payloads()
    if payloads is None:
        payloads = {
            "kpis": {},
            "charts": {},
            "heatmap": {},
            "routes": [],
            "flights": {"flights": []},
            "cpi_options": {},
            "cpi": {},
            "blueprint": None,
        }

    kpis_json = json.dumps(payloads["kpis"])
    charts_json = json.dumps(payloads["charts"])
    heatmap_json = json.dumps(payloads["heatmap"])
    routes_json = json.dumps(payloads["routes"])
    initial_flight_json = json.dumps(payloads["flights"])
    cpi_options_json = json.dumps(payloads["cpi_options"])
    initial_cpi_json = json.dumps(payloads["cpi"])
    blueprint_json = json.dumps(payloads["blueprint"])

    rendered = (
        html_content
        .replace("/* INITIAL_KPIS */ null", kpis_json)
        .replace("/* INITIAL_CHARTS */ null", charts_json)
        .replace("/* INITIAL_HEATMAP */ null", heatmap_json)
        .replace("/* INITIAL_ROUTES */ null", routes_json)
        .replace("/* INITIAL_FLIGHTS */ null", initial_flight_json)
        .replace("/* INITIAL_CPI_OPTIONS */ null", cpi_options_json)
        .replace("/* INITIAL_CPI */ null", initial_cpi_json)
        .replace("/* INITIAL_BLUEPRINT */ null", blueprint_json)
    )
    return HTMLResponse(content=rendered)

