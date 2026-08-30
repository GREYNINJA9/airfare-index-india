"""Load and validate source and route configuration.

Minimal runtime contract for scraper source descriptors and route definitions.
Used by scheduler and any runtime discovery of available scrapers.
"""

from __future__ import annotations

import importlib
from typing import Any, List

from pydantic import BaseModel, Field, model_validator

from models.fare import SourceType
from models.route import Route


class SourceConfig(BaseModel):
    name: str = Field(..., min_length=1)
    source_type: str = Field(..., pattern="^(AIRLINE|OTA)$")
    enabled: bool
    module: str = Field(..., min_length=1)
    class_: str = Field(..., alias="class", min_length=1)

    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }

    def import_and_instantiate(self) -> Any:
        """Import the module and instantiate the class; return an instance.

        Raises:
            ImportError: module cannot be imported.
            AttributeError: class not found in module.
        """
        mod = importlib.import_module(self.module)
        cls = getattr(mod, self.class_)
        # __init__ must be parameterless for all configured sources
        return cls()

    def source_type_enum(self) -> SourceType:
        """Return the SourceType enum value, validating against the model contract."""
        try:
            return SourceType(self.source_type)
        except ValueError as e:
            raise ValueError(
                f"Invalid source_type '{self.source_type}'; expected one of "
                f"{[e.value for e in SourceType]}"
            ) from e


class RouteConfig(BaseModel):
    """Configuration contract for a single route (origin → destination)."""

    origin: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    destination: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    distance_km: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Optional distance in kilometres. Must be non-negative when present."
        ),
    )

    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }

    @model_validator(mode="after")
    def _origin_must_differ_from_destination(self) -> "RouteConfig":
        """Reject routes where origin and destination are the same airport."""
        if self.origin == self.destination:
            raise ValueError(
                f"origin and destination must differ (got '{self.origin}' for both)"
            )
        return self


def load_sources(path: str = "config/sources.yaml") -> List[SourceConfig]:
    """Load and validate all source configurations from a YAML file.

    Returns a list of SourceConfig instances. Raises FileNotFoundError if the
    file is missing, ValueError for structural problems (bad top-level keys or
    malformed YAML), and ValidationError for entries that fail field
    validation.
    """
    import yaml

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "sources" not in raw:
        raise ValueError(f"Top-level 'sources' key missing in {path}")

    sources_data = raw["sources"]
    if not isinstance(sources_data, list):
        raise ValueError(f"'sources' must be a list in {path}")

    # SourceConfig validation failures propagate as ValidationError naturally.
    return [SourceConfig(**entry) for entry in sources_data]


def load_routes(path: str = "config/routes.yaml") -> List[RouteConfig]:
    """Load and validate route configurations from a YAML file.

    Returns a list of RouteConfig instances. Raises FileNotFoundError if the
    file is missing, ValueError for structural problems (bad top-level keys or
    malformed YAML), for duplicate routes, and ValidationError for entries that
    fail field validation.

    A route is considered duplicate if its origin and destination pair is
    identical (regardless of optional distance_km).
    """
    import yaml

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "routes" not in raw:
        raise ValueError(f"Top-level 'routes' key missing in {path}")

    routes_data = raw["routes"]
    if not isinstance(routes_data, list):
        raise ValueError(f"'routes' must be a list in {path}")

    # Track seen route pairs to detect duplicates.
    seen_pairs = set()

    route_configs = []
    for idx, entry in enumerate(routes_data, start=1):
        # Basic type/struct validation before RouteConfig construction.
        if not isinstance(entry, dict):
            raise ValueError(
                f"Route entry at index {idx} is not a valid dict: {entry!r}"
            )
        if "origin" not in entry or "destination" not in entry:
            raise ValueError(
                f"Route entry at index {idx} missing required "
                "'origin' or 'destination' keys"
            )

        route_pair = (entry["origin"], entry["destination"])
        origin, destination = route_pair
        if route_pair in seen_pairs:
            raise ValueError(
                f"Duplicate route definition at index {idx}: "
                f"'{origin}' → '{destination}' (already defined at previous index)"
            )
        seen_pairs.add(route_pair)

        # Validate with RouteConfig - this enforces IATA code pattern and origin!=dest.
        try:
            route_config = RouteConfig(**entry)
        except Exception as validation_error:
            raise ValueError(
                f"Invalid route definition at index {idx} "
                f"({entry!r}): {validation_error}"
            ) from validation_error

        route_configs.append(route_config)

    return route_configs


def load_route_objects(path: str = "config/routes.yaml") -> List[Route]:
    """Convenience: Load and convert route configurations to Route domain models.

    Returns a list of Route instances with distance_km population from configs.

    Raises ImportError if loading routes fails, or ValidationError for any
    invalid definition.
    """
    configs = load_routes(path)
    return [
        Route(
            origin=config.origin,
            destination=config.destination,
            distance_km=config.distance_km,
        )
        for config in configs
    ]
