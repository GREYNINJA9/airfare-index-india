"""Analytics API domain endpoints for MoSPI, NSO, and RBI consumption.

Exposes:
- Sector-wise price heatmaps
- Econometric lead-time elasticity curves (T+1 to T+45)
- Airline price dispersion & market share
- 30+ day DGCA benchmark backtesting validation
- Official CPI Transport sub-index augmentation comparison
- RBI/NSO automated data export feeds (JSON & CSV)
"""

from __future__ import annotations

import csv
import io
import math
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from api.mospi_client import fetch_official_mospi_cpi
from database.connection import get_connection
from database.repository import get_daily_fare_statistics, get_fares, get_index_results
from index_engine.backtesting import generate_backtest_report
from index_engine.elasticity import compute_lead_time_elasticity
from models.dgca import DGCABacktestReport
from models.elasticity import ElasticityAnalysisResult

router = APIRouter(prefix="/api/analytics", tags=["Analytics & MoSPI / RBI Feeds"])


def _db():
    return get_connection()


class SectorHeatmapCell(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sector: str
    origin: str
    destination: str
    distance_km: Optional[float]
    current_median_inr: float
    base_median_inr: float
    price_relative: float
    change_24h_pct: float
    change_7d_pct: float
    observation_count: int
    heat_intensity: float = Field(..., description="Normalized score 0.0-1.0 for color styling")


class AirlineComparisonStat(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    airline_code: str
    airline_name: str
    median_price_inr: float
    mean_price_inr: float
    min_price_inr: float
    max_price_inr: float
    price_spread_inr: float
    quote_count: int
    market_quote_share: float


class CPIComparisonSeriesPoint(BaseModel):
    date: date
    apix_laspeyres_daily: float
    apix_jevons_daily: float
    apix_laspeyres_psd: Optional[float] = None
    apix_laspeyres_uniform: Optional[float] = None
    apix_jevons_psd: Optional[float] = None
    apix_jevons_uniform: Optional[float] = None
    apix_weekly_moving_avg: float
    official_cpi_transport: float
    inflation_tracking_gap: float
    average_fare_inr: Optional[float] = None


@router.get("/sector-heatmap", response_model=List[SectorHeatmapCell])
def sector_heatmap() -> List[SectorHeatmapCell]:
    """Return sector-wise price relative and fare variation matrix for heatmaps."""
    conn = _db()
    fares = get_fares(conn)

    if not fares:
        return []

    dates = sorted({f.scraped_at.date() for f in fares})
    latest_date = dates[-1]
    prev_date = dates[-2] if len(dates) >= 2 else latest_date
    week_ago_date = dates[-7] if len(dates) >= 7 else dates[0]
    base_date = dates[0]

    by_sector_day: Dict[str, Dict[date, List[float]]] = {}
    sector_meta: Dict[str, Any] = {}

    for f in fares:
        sec = f"{f.route.origin}-{f.route.destination}"
        d = f.scraped_at.date()
        by_sector_day.setdefault(sec, {}).setdefault(d, []).append(f.price_inr)
        if sec not in sector_meta:
            sector_meta[sec] = {
                "origin": f.route.origin,
                "destination": f.route.destination,
                "distance_km": f.route.distance_km,
            }

    cells: List[SectorHeatmapCell] = []
    all_relatives: List[float] = []

    for sec, days_data in sorted(by_sector_day.items()):
        meta = sector_meta[sec]

        def _med(d: date) -> float:
            prices = days_data.get(d, [])
            if not prices:
                return 5000.0
            s = sorted(prices)
            return s[len(s) // 2]

        curr_med = _med(latest_date)
        prev_med = _med(prev_date)
        week_med = _med(week_ago_date)
        base_med = _med(base_date)

        rel = round(curr_med / base_med, 4) if base_med > 0 else 1.0
        all_relatives.append(rel)

        c24h = round(((curr_med - prev_med) / prev_med) * 100.0, 2) if prev_med > 0 else 0.0
        c7d = round(((curr_med - week_med) / week_med) * 100.0, 2) if week_med > 0 else 0.0

        count_latest = len(days_data.get(latest_date, []))

        cells.append(
            SectorHeatmapCell(
                sector=sec,
                origin=meta["origin"],
                destination=meta["destination"],
                distance_km=meta["distance_km"],
                current_median_inr=round(curr_med, 2),
                base_median_inr=round(base_med, 2),
                price_relative=rel,
                change_24h_pct=c24h,
                change_7d_pct=c7d,
                observation_count=count_latest,
                heat_intensity=0.5,  # adjusted below
            )
        )

    # Normalize heat intensity (0.0 to 1.0)
    if all_relatives:
        min_r = min(all_relatives)
        max_r = max(all_relatives)
        spread = max_r - min_r or 1.0
        for cell in cells:
            cell.heat_intensity = round(max(0.0, min(1.0, (cell.price_relative - min_r) / spread)), 2)

    return cells


@router.get("/lead-time-elasticity", response_model=ElasticityAnalysisResult)
def lead_time_elasticity() -> ElasticityAnalysisResult:
    """Return lead-time price elasticity curves across T+1, T+7, T+15, T+30, T+45 windows."""
    conn = _db()
    fares = get_fares(conn)
    return compute_lead_time_elasticity(fares)


@router.get("/airline-comparison", response_model=List[AirlineComparisonStat])
def airline_comparison() -> List[AirlineComparisonStat]:
    """Return comparative pricing statistics and dispersion across carriers."""
    conn = _db()
    fares = get_fares(conn)
    if not fares:
        return []

    carrier_names = {
        "6E": "IndiGo",
        "AI": "Air India",
        "IX": "Air India Express",
        "QP": "Akasa Air",
        "SG": "SpiceJet",
    }

    by_carrier: Dict[str, List[float]] = {}
    for f in fares:
        by_carrier.setdefault(f.airline_code, []).append(f.price_inr)

    total_quotes = len(fares)
    stats: List[AirlineComparisonStat] = []

    for code, prices in sorted(by_carrier.items()):
        prices.sort()
        n = len(prices)
        med = prices[n // 2]
        mean = sum(prices) / n
        min_p = prices[0]
        max_p = prices[-1]

        stats.append(
            AirlineComparisonStat(
                airline_code=code,
                airline_name=carrier_names.get(code, code),
                median_price_inr=round(med, 2),
                mean_price_inr=round(mean, 2),
                min_price_inr=round(min_p, 2),
                max_price_inr=round(max_p, 2),
                price_spread_inr=round(max_p - min_p, 2),
                quote_count=n,
                market_quote_share=round((n / total_quotes) * 100.0, 2),
            )
        )

    return stats


@router.get("/dgca-backtest", response_model=DGCABacktestReport)
def dgca_backtest(
    start_date: Optional[date] = Query(None, description="Start date of backtest window"),
    end_date: Optional[date] = Query(None, description="End date of backtest window"),
) -> DGCABacktestReport:
    """Return 30+ day backtest report against official DGCA benchmark tariff data."""
    s_date = start_date if isinstance(start_date, date) else None
    e_date = end_date if isinstance(end_date, date) else None
    conn = _db()
    fares = get_fares(conn)
    return generate_backtest_report(fares, start_date=s_date, end_date=e_date)


@router.get("/cpi-comparison", response_model=List[CPIComparisonSeriesPoint])
def cpi_comparison() -> List[CPIComparisonSeriesPoint]:
    """Compare daily/weekly high-frequency APIx index with official MoSPI monthly CPI."""
    conn = _db()
    index_results = get_index_results(conn)
    daily_stats = get_daily_fare_statistics(conn)

    # Fetch official MoSPI CPI figures from live government API
    official_cpi_map = fetch_official_mospi_cpi()
    base_cpi_val = 125.46
    if official_cpi_map:
        base_candidates = [v["index"] for k, v in official_cpi_map.items() if "2026" in k]
        if base_candidates:
            base_cpi_val = float(base_candidates[0])

    if not index_results:
        # Fallback to backtest series if database index not precalculated
        fares = get_fares(conn)
        rep = generate_backtest_report(fares)
        return [
            CPIComparisonSeriesPoint(
                date=d.date,
                apix_laspeyres_daily=d.apix_laspeyres,
                apix_jevons_daily=d.apix_jevons,
                apix_laspeyres_psd=d.apix_laspeyres,
                apix_laspeyres_uniform=d.apix_laspeyres,
                apix_jevons_psd=d.apix_jevons,
                apix_jevons_uniform=d.apix_jevons,
                apix_weekly_moving_avg=d.apix_laspeyres,
                official_cpi_transport=base_cpi_val,
                inflation_tracking_gap=round(d.apix_laspeyres - 100.0, 2),
                average_fare_inr=round(d.observed_market_median_inr, 2),
            )
            for d in rep.daily_series
        ]

    sorted_results = sorted(index_results, key=lambda x: x.current_period)
    base_month_key = sorted_results[0].base_period.strftime("%Y-%m")
    base_cpi_val = float(official_cpi_map.get(base_month_key, {}).get("index", 126.30))

    points: List[CPIComparisonSeriesPoint] = []
    lasp_vals: List[float] = []
    for res in sorted_results:
        lasp_vals.append(res.overall_laspeyres_index)
        window = lasp_vals[-7:]
        rolling_7d = sum(window) / len(window)

        # Official MoSPI baseline reference normalized to 100 on base period
        month_key = res.current_period.strftime("%Y-%m")
        if month_key in official_cpi_map:
            cpi_raw = float(official_cpi_map[month_key]["index"])
        elif official_cpi_map:
            latest_k = sorted(official_cpi_map.keys())[-1]
            cpi_raw = float(official_cpi_map[latest_k]["index"])
        else:
            cpi_raw = base_cpi_val

        cpi_normalized = round((cpi_raw / base_cpi_val) * 100.0, 2)

        lasp_psd = round(res.overall_laspeyres_index, 2)
        jev_psd = round(res.overall_jevons_index, 2)

        if res.item_indices:
            n_items = len(res.item_indices)
            lasp_uni = round(100.0 * (sum(it.index_relative for it in res.item_indices) / n_items), 2)
            jev_uni = round(100.0 * math.exp(sum(math.log(it.index_relative) for it in res.item_indices) / n_items), 2)
        else:
            lasp_uni = lasp_psd
            jev_uni = jev_psd

        d_str = res.current_period.strftime("%Y-%m-%d")
        daily_stat = daily_stats.get(d_str)
        if daily_stat and daily_stat["avg_price"] > 0:
            avg_fare = round(daily_stat["avg_price"], 2)
        else:
            avg_fare = round(5519.42 * (res.overall_laspeyres_index / 100.0), 2)

        points.append(
            CPIComparisonSeriesPoint(
                date=res.current_period,
                apix_laspeyres_daily=lasp_psd,
                apix_jevons_daily=jev_psd,
                apix_laspeyres_psd=lasp_psd,
                apix_laspeyres_uniform=lasp_uni,
                apix_jevons_psd=jev_psd,
                apix_jevons_uniform=jev_uni,
                apix_weekly_moving_avg=round(rolling_7d, 2),
                official_cpi_transport=cpi_normalized,
                inflation_tracking_gap=round(lasp_psd - cpi_normalized, 2),
                average_fare_inr=avg_fare,
            )
        )

    return points


@router.get("/rbi-nso-feed")
def rbi_nso_data_feed(
    format: str = Query("json", pattern="^(json|csv)$", description="Format: json or csv"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """High-frequency data feed designed specifically for NSO and RBI economists."""
    conn = _db()
    index_results = get_index_results(conn, base_period=None, current_period=None)

    # Fetch live official MoSPI Airfare CPI values
    official_cpi_map = fetch_official_mospi_cpi()
    base_month_key = index_results[0].base_period.strftime("%Y-%m") if index_results else "2026-08"
    base_cpi_val = float(official_cpi_map.get(base_month_key, {}).get("index", 126.30))

    s_date = start_date if isinstance(start_date, date) else None
    e_date = end_date if isinstance(end_date, date) else None

    rows = []
    for res in index_results:
        if s_date and res.current_period < s_date:
            continue
        if e_date and res.current_period > e_date:
            continue

        month_key = res.current_period.strftime("%Y-%m")
        if month_key in official_cpi_map:
            cpi_raw = float(official_cpi_map[month_key]["index"])
        elif official_cpi_map:
            latest_k = sorted(official_cpi_map.keys())[-1]
            cpi_raw = float(official_cpi_map[latest_k]["index"])
        else:
            cpi_raw = base_cpi_val
        cpi_normalized = round((cpi_raw / base_cpi_val) * 100.0, 2)

        rows.append(
            {
                "date": res.current_period.isoformat(),
                "base_period": res.base_period.isoformat(),
                "apix_laspeyres_index": res.overall_laspeyres_index,
                "apix_jevons_index": res.overall_jevons_index,
                "official_mospi_cpi": cpi_normalized,
                "tracking_gap": round(res.overall_laspeyres_index - cpi_normalized, 2),
                "items_included_count": len(res.item_indices),
                "weight_method": res.methodology.weight_method,
                "standard_scaling": "Base=100",
            }
        )

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=apix_mospi_rbi_feed.csv"},
        )

    return {
        "institution": "MoSPI / RBI High-Frequency Data Feed",
        "index_name": "APIx (Airfare Price Index)",
        "frequency": "Daily",
        "base_scaling": 100.0,
        "record_count": len(rows),
        "data": rows,
    }


@router.get("/cpi-mospi")
def get_mospi_cpi_data(
    year: Optional[int] = Query(2026, description="Reference year e.g. 2026, 2025, 2024"),
    item_code: Optional[str] = Query("07.3.3", description="MoSPI item/index code, e.g. '07.3.3' for airfare"),
    base_year: Optional[int] = Query(2024, description="Base year comparison e.g. 2024"),
    group_code: Optional[int] = Query(24, description="MoSPI group code"),
    class_code: Optional[int] = Query(58, description="MoSPI class code"),
    limit: Optional[int] = Query(100, description="Max records to retrieve"),
    sector: Optional[str] = Query(None, description="Optional sector filter e.g. 'Combined', 'Urban', 'Rural'"),
    refresh: bool = Query(False, description="Force network refresh from MoSPI API"),
):
    """Fetch live or cached CPI data directly from the official MoSPI API endpoint."""
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


@router.get("/cpi-options")
def get_mospi_cpi_options():
    """Return available choices for years, indices, and sectors for UI dropdowns."""
    from index_engine.cpi_client import get_cpi_options

    return get_cpi_options()
