"""Canonical Route domain model.

This module defines the Route contract: an origin/destination pair of IATA
airport codes for an Indian domestic flight. It is intentionally minimal and
contains no scraping, persistence, or airline/OTA-specific logic.

The Route model is the spatial dimension of a fare observation. It is
referenced by the Fare contract (see :mod:`models.fare`) and consumed
downstream by the cleaning/normalization pipeline and the index engine.

IATA airport codes are three uppercase Latin letters (e.g. ``"DEL"`` for
New Delhi, ``"BOM"`` for Mumbai). Codes are stored uppercased and validated
to a strict ``^[A-Z]{3}$`` pattern. A route is invalid if origin and
destination are identical.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["Route"]


class Route(BaseModel):
    """An origin/destination airport pair (Indian domestic).

    Attributes:
        origin: IATA code of the departure airport (e.g. ``"DEL"``).
        destination: IATA code of the arrival airport (e.g. ``"BOM"``).
        distance_km: Optional great-circle distance between the airports in
            kilometres. Optional because not every source exposes it; when
            present it must be non-negative.

    Notes:
        Codes are normalized to uppercase on assignment. ``origin`` and
        ``destination`` must differ. The model is deliberately agnostic to
        whether the route is one-way or round-trip — trip type is a property
        of a fare observation, not of the route geometry, and lives on
        :class:`models.fare.Fare`.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        frozen=True,
    )

    origin: str = Field(
        ...,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="IATA code of the departure airport, e.g. 'DEL'.",
    )
    destination: str = Field(
        ...,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="IATA code of the arrival airport, e.g. 'BOM'.",
    )
    distance_km: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Optional great-circle distance between airports in kilometres. "
            "Non-negative when present."
        ),
    )

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def _normalize_code(cls, v: str) -> str:
        """Uppercase and strip whitespace from an IATA code before validation."""
        if not isinstance(v, str):
            return v
        return v.strip().upper()

    @model_validator(mode="after")
    def _origin_must_differ_from_destination(self) -> "Route":
        """Reject routes where origin and destination are the same airport."""
        if self.origin == self.destination:
            raise ValueError(
                f"origin and destination must differ (got '{self.origin}' for both)"
            )
        return self
