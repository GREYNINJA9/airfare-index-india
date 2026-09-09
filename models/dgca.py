"""Models for DGCA benchmark backtesting and CPI comparison analysis.

Validates the high-frequency APIx index against publicly available DGCA
monthly average airfare data over at least 30 days.
"""

from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class DGCARouteBenchmark(BaseModel):
    """Official DGCA monthly average fare benchmark for a domestic sector."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    origin: str = Field(..., pattern=r"^[A-Z]{3}$")
    destination: str = Field(..., pattern=r"^[A-Z]{3}$")
    monthly_avg_fare_inr: float = Field(..., gt=0.0)
    dgca_passenger_share: float = Field(..., gt=0.0, le=1.0)
    reporting_month: str = Field(..., description="E.g. '2026-08' or '2026-09'")


class BacktestDayComparison(BaseModel):
    """Daily comparison between APIx price index, market fares, and DGCA benchmark."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    date: date
    apix_laspeyres: float = Field(..., description="APIx Laspeyres price index (Base=100)")
    apix_jevons: float = Field(..., description="APIx Jevons geometric price index (Base=100)")
    observed_market_median_inr: float = Field(..., gt=0.0)
    dgca_benchmark_fare_inr: float = Field(..., gt=0.0)
    tracking_diff_inr: float = Field(..., description="Observed Market Fare - DGCA Benchmark")
    tracking_diff_pct: float = Field(..., description="Percentage variance from DGCA benchmark")
    cpi_transport_subindex: float = Field(..., description="Official MoSPI CPI Transport sub-index")


class DGCABacktestReport(BaseModel):
    """Complete 30+ days backtesting report validating APIx against DGCA standards."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    evaluation_period_start: date
    evaluation_period_end: date
    total_backtest_days: int = Field(..., ge=30)
    pearson_correlation: float = Field(..., ge=-1.0, le=1.0)
    r_squared: float = Field(..., ge=0.0, le=1.0)
    mean_absolute_error_inr: float = Field(..., ge=0.0)
    mean_absolute_error_pct: float = Field(..., ge=0.0)
    root_mean_squared_error_inr: float = Field(..., ge=0.0)
    daily_series: List[BacktestDayComparison] = Field(..., min_length=30)
    route_benchmarks: List[DGCARouteBenchmark]
    summary_verdict: str = Field(..., description="Econometric assessment for MoSPI/RBI")
