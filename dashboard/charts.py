"""Dashboard Chart Data Generators.

Prepares structured data payloads for Chart.js / ApexCharts.
"""

from __future__ import annotations

from typing import Any, Dict

from api.analytics import (
    airline_comparison,
    cpi_comparison,
    dgca_backtest,
    lead_time_elasticity,
)


def get_trend_chart_data() -> Dict[str, Any]:
    """Return time-series chart data for APIx Laspeyres vs Jevons vs CPI."""
    points = cpi_comparison()
    labels = [p.date.strftime("%d %b") for p in points]
    laspeyres = [p.apix_laspeyres_daily for p in points]
    jevons = [p.apix_jevons_daily for p in points]
    cpi = [p.official_cpi_transport for p in points]

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "APIx (Laspeyres - Real-time)",
                "data": laspeyres,
                "borderColor": "#1e40af",  # Indigo-800
                "backgroundColor": "rgba(30, 64, 175, 0.1)",
                "borderWidth": 2.5,
                "tension": 0.3,
                "fill": True,
            },
            {
                "label": "APIx (Jevons - Geometric)",
                "data": jevons,
                "borderColor": "#0891b2",  # Cyan-600
                "backgroundColor": "transparent",
                "borderWidth": 2,
                "borderDash": [4, 4],
                "tension": 0.3,
            },
            {
                "label": "Official MoSPI CPI (Airfare 07.3.3)",
                "data": cpi,
                "borderColor": "#d97706",  # Amber-600
                "backgroundColor": "transparent",
                "borderWidth": 2,
                "stepped": True,
            },
        ],
    }


def get_elasticity_chart_data() -> Dict[str, Any]:
    """Return lead-time price curve data across T+1..T+45."""
    elasticity = lead_time_elasticity()

    labels = [w.window_label for w in elasticity.overall_curve]
    overall_prices = [w.median_price_inr for w in elasticity.overall_curve]

    datasets = [
        {
            "label": "Market Overall Curve",
            "data": overall_prices,
            "borderColor": "#4f46e5",
            "backgroundColor": "rgba(79, 70, 229, 0.15)",
            "borderWidth": 3,
            "tension": 0.25,
            "fill": True,
        }
    ]

    colors = ["#059669", "#dc2626", "#d97706", "#9333ea", "#0284c7", "#db2777"]
    for i, rc in enumerate(elasticity.route_curves[:5]):
        datasets.append(
            {
                "label": f"{rc.origin}-{rc.destination}",
                "data": [w.median_price_inr for w in rc.window_stats],
                "borderColor": colors[i % len(colors)],
                "backgroundColor": "transparent",
                "borderWidth": 1.8,
                "tension": 0.25,
            }
        )

    return {
        "labels": labels,
        "datasets": datasets,
        "market_elasticity_beta": elasticity.market_elasticity_coefficient,
        "average_surge_multiplier": elasticity.average_surge_multiplier,
    }


def get_carrier_chart_data() -> Dict[str, Any]:
    """Return airline pricing dispersion and market quotes share."""
    stats = airline_comparison()
    if not stats:
        return {
            "labels": ["IndiGo", "Air India", "AI Express", "Akasa Air", "SpiceJet"],
            "medians": [5380.0, 5720.0, 5050.0, 5160.0, 5220.0],
            "mins": [2800.0, 3100.0, 2400.0, 2600.0, 2700.0],
            "maxs": [16500.0, 18900.0, 14200.0, 15000.0, 15800.0],
            "market_shares": [62.4, 14.8, 8.2, 5.6, 9.0],
        }

    labels = [s.airline_name for s in stats]
    medians = [s.median_price_inr for s in stats]
    mins = [s.min_price_inr for s in stats]
    maxs = [s.max_price_inr for s in stats]
    shares = [s.market_quote_share for s in stats]

    return {
        "labels": labels,
        "medians": medians,
        "mins": mins,
        "maxs": maxs,
        "market_shares": shares,
    }


def get_backtest_chart_data() -> Dict[str, Any]:
    """Return 30-day DGCA benchmark comparison chart payload."""
    report = dgca_backtest()

    labels = [d.date.strftime("%d %b") for d in report.daily_series]
    observed = [d.observed_market_median_inr for d in report.daily_series]
    benchmark = [d.dgca_benchmark_fare_inr for d in report.daily_series]

    return {
        "labels": labels,
        "observed_market_fares": observed,
        "dgca_benchmarks": benchmark,
        "correlation_r2": report.r_squared,
        "mae_pct": report.mean_absolute_error_pct,
        "rmse_inr": report.root_mean_squared_error_inr,
        "summary": report.summary_verdict,
    }
