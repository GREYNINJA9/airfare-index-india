import pytest
import yaml
from pydantic import ValidationError

from config.loader import SourceConfig, load_sources
from models.fare import SourceType
from scraper.otas.mmt import MakeMyTripScraper


def test_sources_yaml_exists() -> None:
    """Verify config/sources.yaml exists."""
    try:
        with open("config/sources.yaml", "r"):
            pass
    except FileNotFoundError:
        pytest.fail("config/sources.yaml does not exist")


def test_sources_yaml_valid() -> None:
    """Verify YAML syntax and basic structure."""
    with open("config/sources.yaml", "r") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "sources" not in raw:
        pytest.fail("Top-level 'sources' key missing")
    sources_data = raw["sources"]
    if not isinstance(sources_data, list):
        pytest.fail("'sources' must be a list")


def test_makemytrip_entry_exists() -> None:
    """Verify the MakeMyTrip entry is present."""
    configs = load_sources()
    names = [cfg.name for cfg in configs]
    assert "MakeMyTrip" in names, "MakeMyTrip entry missing"


def test_required_fields_validated() -> None:
    """Verify required fields are enforced."""
    with pytest.raises(ValidationError):
        SourceConfig(source_type="OTA", enabled=True, module="x", class_="X")
    with pytest.raises(ValidationError):
        SourceConfig(name="X", enabled=True, module="x", class_="X")
    with pytest.raises(ValidationError):
        SourceConfig(name="X", source_type="OTA", module="x", class_="X")
    with pytest.raises(ValidationError):
        SourceConfig(name="X", source_type="OTA", enabled=True, class_="X")
    with pytest.raises(ValidationError):
        SourceConfig(name="X", source_type="OTA", enabled=True, module="x")


def test_source_type_validation() -> None:
    """Verify source_type is restricted to AIRLINE/OTA."""
    with pytest.raises(ValidationError):
        SourceConfig(
            name="X",
            source_type="INVALID",
            enabled=True,
            module="x",
            class_="X",
        )


def test_module_class_import() -> None:
    """Verify MakeMyTrip's module/class can be imported."""
    configs = load_sources()
    mmt_cfg = next(cfg for cfg in configs if cfg.name == "MakeMyTrip")
    instance = mmt_cfg.import_and_instantiate()
    assert isinstance(instance, MakeMyTripScraper)


def test_source_type_enum_conversion() -> None:
    """Verify source_type maps to the SourceType enum."""
    configs = load_sources()
    mmt_cfg = next(cfg for cfg in configs if cfg.name == "MakeMyTrip")
    assert mmt_cfg.source_type_enum() == SourceType.OTA


def test_enabled_must_be_boolean() -> None:
    """Verify 'enabled' must be a boolean, not a string or number."""
    with pytest.raises(ValidationError):
        SourceConfig(
            name="X",
            source_type="OTA",
            enabled="not_a_bool",
            module="x",
            class_="X",
        )


def test_invalid_entry_rejected() -> None:
    """Verify an invalid source entry raises ValidationError."""
    with pytest.raises(ValidationError):
        SourceConfig(
            name="X",
            source_type="INVALID_TYPE",
            enabled=True,
            module="x",
            class_="X",
        )


def test_extra_fields_rejected() -> None:
    """Verify no speculative fields are allowed (extra='forbid')."""
    with pytest.raises(ValidationError):
        SourceConfig(
            name="X",
            source_type="OTA",
            enabled=True,
            module="x",
            class_="X",
            selectors={"foo": "bar"},  # speculative field must be rejected
        )
