"""Models for lead-time price elasticity and dynamic pricing analysis.

Tracks price progression across advance-purchase windows:
T+1, T+7, T+15, T+30, T+45 days.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LeadTimeWindowStat(BaseModel):
    """Aggregated fare metrics for a specific advance-purchase window."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    window_label: str = Field(..., description="E.g. T+1, T+7, T+15, T+30, T+45")
    target_days: int = Field(..., ge=0, description="Target lead time in days")
    median_price_inr: float = Field(..., gt=0.0)
    mean_price_inr: float = Field(..., gt=0.0)
    min_price_inr: float = Field(..., gt=0.0)
    max_price_inr: float = Field(..., gt=0.0)
    observation_count: int = Field(..., ge=1)


class RouteElasticityCurve(BaseModel):
    """Lead-time elasticity curve for a specific sector or carrier."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    origin: str = Field(..., pattern=r"^[A-Z]{3}$")
    destination: str = Field(..., pattern=r"^[A-Z]{3}$")
    airline_code: Optional[str] = Field(default=None, pattern=r"^[A-Z0-9]{2}$")
    window_stats: List[LeadTimeWindowStat] = Field(..., min_length=1)
    elasticity_beta: float = Field(
        ..., description="Log-linear lead-time elasticity coefficient d(ln P)/d(ln Days)"
    )
    surge_multiplier: float = Field(
        ..., description="Price ratio P(T+1) / P(T+30), measuring late-booking premium"
    )
    r_squared: float = Field(..., ge=0.0, le=1.0, description="Goodness-of-fit for elasticity curve")


class ElasticityAnalysisResult(BaseModel):
    """System-wide lead-time elasticity output for API and dashboard."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    computed_at_date: date
    overall_curve: List[LeadTimeWindowStat]
    route_curves: List[RouteElasticityCurve]
    carrier_curves: Dict[str, List[LeadTimeWindowStat]]
    average_surge_multiplier: float
    market_elasticity_coefficient: float
