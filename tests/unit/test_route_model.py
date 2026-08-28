"""Deterministic unit tests for the canonical Route domain model.

No network access, no wall-clock dependence.
"""

import pytest
from pydantic import ValidationError

from models.route import Route


def test_valid_route_creation() -> None:
    """A well-formed route is accepted and exposes its fields."""
    route = Route(origin="DEL", destination="BOM", distance_km=1138.0)
    assert route.origin == "DEL"
    assert route.destination == "BOM"
    assert route.distance_km == 1138.0


def test_route_distance_is_optional() -> None:
    """distance_km is optional and defaults to None."""
    route = Route(origin="DEL", destination="BOM")
    assert route.distance_km is None


def test_route_codes_are_uppercased() -> None:
    """Lowercase IATA codes are normalized to uppercase."""
    route = Route(origin="del", destination="bom")
    assert route.origin == "DEL"
    assert route.destination == "BOM"


def test_route_codes_are_whitespace_stripped() -> None:
    """Surrounding whitespace is stripped from IATA codes."""
    route = Route(origin=" del ", destination=" bom ")
    assert route.origin == "DEL"
    assert route.destination == "BOM"


def test_route_rejects_identical_origin_destination() -> None:
    """origin and destination must differ."""
    with pytest.raises(ValidationError):
        Route(origin="DEL", destination="DEL")


def test_route_rejects_identical_after_normalization() -> None:
    """The origin/destination check runs after case normalization."""
    with pytest.raises(ValidationError):
        Route(origin="del", destination="DEL")


@pytest.mark.parametrize("bad_code", ["DE", "DELH", "D3L", "de1", ""])
def test_route_rejects_malformed_codes(bad_code: str) -> None:
    """IATA codes must be exactly three Latin letters."""
    with pytest.raises(ValidationError):
        Route(origin=bad_code, destination="BOM")


def test_route_rejects_negative_distance() -> None:
    """distance_km must be non-negative when present."""
    with pytest.raises(ValidationError):
        Route(origin="DEL", destination="BOM", distance_km=-1.0)


def test_route_allows_zero_distance() -> None:
    """A zero distance is permitted (boundary value)."""
    route = Route(origin="DEL", destination="BOM", distance_km=0.0)
    assert route.distance_km == 0.0


def test_route_rejects_extra_fields() -> None:
    """Unknown fields are rejected (extra='forbid')."""
    with pytest.raises(ValidationError):
        Route.model_validate({"origin": "DEL", "destination": "BOM", "unexpected": 1})


def test_route_requires_both_endpoints() -> None:
    """origin and destination are required."""
    with pytest.raises(ValidationError):
        Route.model_validate({"origin": "DEL"})


def test_route_is_frozen() -> None:
    """Route instances are immutable."""
    route = Route(origin="DEL", destination="BOM")
    with pytest.raises(ValidationError):
        route.origin = "CCU"  # type: ignore[misc]


def test_route_serialization_roundtrip() -> None:
    """A route survives a JSON serialize/deserialize round-trip unchanged."""
    route = Route(origin="MAA", destination="HYD", distance_km=629.0)
    restored = Route.model_validate_json(route.model_dump_json())
    assert restored == route
