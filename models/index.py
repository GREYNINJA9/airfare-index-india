"""Index engine result contracts.

This module defines the *data contract* that the index engine produces.

Currently, the mathematical engine is not implemented in index_engine/.
Nevertheless, we lock the MVP output schema here so that later phases can
compute deterministically and shape responses without re-defining types.

All models follow the same Pydantic v2 conventions as other domain contracts:
- no new dependencies
- extra fields are forbidden
- string inputs are whitespace-stripped
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.fare import CabinClass, TripType

__all__ = [
    "IndexMethodologyMetadata",
    "ItemIndex",
    "ItemKey",
    "IndexResult",
]


class ItemKey(BaseModel):
    """Item identity used for item-level indices.

    MVP item identity is: (origin, destination, cabin_class, trip_type).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        frozen=True,
    )

    origin: str = Field(
        ..., pattern=r"^[A-Z]{3}$", description="IATA origin airport code"
    )
    destination: str = Field(
        ..., pattern=r"^[A-Z]{3}$", description="IATA destination airport code"
    )
    cabin_class: CabinClass
    trip_type: TripType


class ItemIndex(BaseModel):
    """Index value for one item in one current period."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    item: ItemKey
    # Price relatives are strictly positive since Fare.price_inr > 0.
    index_relative: float = Field(..., gt=0.0)

    @staticmethod
    def _ensure_finite(v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("index_relative must be a finite float")
        return v

    @field_validator("index_relative", mode="after")
    @classmethod
    def _validate_index_relative(cls, v: float) -> float:
        return cls._ensure_finite(v)


class IndexMethodologyMetadata(BaseModel):
    """Methodology metadata for the locked MVP specification."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    methodology_version: str = Field(
        default="mvp-locked-1",
        description="Identifier for this locked MVP specification.",
    )

    item_granularity: Literal["route+cabin_class+trip_type"] = (
        "route+cabin_class+trip_type"
    )

    daily_period_definition: Literal["utc-date-from-scraped_at"] = (
        "utc-date-from-scraped_at"
    )

    quote_aggregation: Literal["median"] = "median"

    weight_method: Literal["uniform"] = "uniform"

    laspeyres_form: Literal["weighted-arithmetic-mean-of-relatives"] = (
        "weighted-arithmetic-mean-of-relatives"
    )

    jevons_form: Literal["weighted-geometric-mean-of-relatives"] = (
        "weighted-geometric-mean-of-relatives"
    )

    missing_current_item_policy: Literal["exclude-and-renormalize"] = (
        "exclude-and-renormalize"
    )

    new_item_policy: Literal["exclude-until-rebased"] = "exclude-until-rebased"

    scaling_convention_internal: Literal["index=1.0-at-base"] = "index=1.0-at-base"


class IndexResult(BaseModel):
    """Complete output of the index engine for one current day."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    base_period: date = Field(..., description="UTC daily period date used as base")
    current_period: date = Field(
        ..., description="UTC daily period date for the current index computation"
    )

    overall_laspeyres_index: float = Field(..., gt=0.0)
    overall_jevons_index: float = Field(..., gt=0.0)

    # Item-level indices are returned for items that were observed in the current
    # period and included in the calculation.
    item_indices: List[ItemIndex] = Field(..., min_length=0)

    methodology: IndexMethodologyMetadata

    @staticmethod
    def _ensure_finite(v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("index values must be finite floats")
        return v

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.overall_laspeyres_index = self._ensure_finite(self.overall_laspeyres_index)
        self.overall_jevons_index = self._ensure_finite(self.overall_jevons_index)


# Convenience type for downstream code; kept explicit to avoid importing typing.
IndexResultJSON = Dict[str, Any]
