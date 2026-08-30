"""Load and validate source configuration.

Minimal runtime contract for scraper source descriptors.
Used by scheduler and any runtime discovery of available scrapers.
"""

from __future__ import annotations

import importlib
from typing import Any, List

from pydantic import BaseModel, Field

from models.fare import SourceType


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
