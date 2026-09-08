"""Unit tests for DGCA 30-day backtesting engine."""

from __future__ import annotations

from datetime import date

import pytest

from backend.index_engine.backtesting import generate_backtest_report, load_dgca_benchmarks


def test_load_dgca_benchmarks():
    benchmarks, cpi = load_dgca_benchmarks()
    assert len(benchmarks) >= 6
    del_bom = next(b for b in benchmarks if b.origin == "DEL" and b.destination == "BOM")
    assert del_bom.monthly_avg_fare_inr > 3000
    assert del_bom.dgca_passenger_share > 0.15
    assert "2026-08" in cpi


def test_generate_backtest_report_30_plus_days():
    report = generate_backtest_report(
        fares=[],
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert report.total_backtest_days >= 30
    assert len(report.daily_series) >= 30
    assert report.pearson_correlation >= 0.85
    assert report.r_squared >= 0.70
    assert report.mean_absolute_error_inr > 0
    assert report.mean_absolute_error_pct < 15.0  # within 15% tracking error
    assert "DGCA Backtest passed" in report.summary_verdict
