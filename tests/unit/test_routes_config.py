"""Route configuration tests — validates config/routes.yaml and loader contract.

Focused, deterministic: never touches the real web, no database, no wall-clock
no scraper imports. Mirrors the structure of tests/unit/test_sources_config.py.
"""

from __future__ import annotations

import os
import tempfile
import textwrap

import pytest
import yaml
from pydantic import ValidationError

from config.loader import RouteConfig, load_route_objects, load_routes
from models.route import Route

# ── existence / structure ──────────────────────────────────────────────────


def test_routes_yaml_exists() -> None:
    """config/routes.yaml exists and is readable."""
    try:
        with open("config/routes.yaml", "r"):
            pass
    except FileNotFoundError:
        pytest.fail("config/routes.yaml does not exist")


def test_routes_yaml_parses() -> None:
    """YAML is valid and has a top-level 'routes' list."""
    with open("config/routes.yaml", "r") as f:
        raw = yaml.safe_load(f)
    assert isinstance(raw, dict), "routes.yaml did not parse into a dict"
    assert "routes" in raw, "top-level 'routes' key missing"
    assert isinstance(raw["routes"], list), "'routes' must be a list"
    assert len(raw["routes"]) > 0, "'routes' must be non-empty"


# ── required routes present ────────────────────────────────────────────────


def test_del_bom_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("DEL", "BOM") in pairs, "DEL → BOM entry missing from routes.yaml"


def test_bom_del_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("BOM", "DEL") in pairs, "BOM → DEL entry missing from routes.yaml"


def test_del_blr_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("DEL", "BLR") in pairs, "DEL → BLR entry missing from routes.yaml"


def test_blr_del_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("BLR", "DEL") in pairs, "BLR → DEL entry missing from routes.yaml"


def test_del_hyd_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("DEL", "HYD") in pairs, "DEL → HYD entry missing from routes.yaml"


def test_hyd_del_exists() -> None:
    routes = load_routes()
    pairs = {(r.origin, r.destination) for r in routes}
    assert ("HYD", "DEL") in pairs, "HYD → DEL entry missing from routes.yaml"


# ── basic properties of all configured routes ─────────────────────────────


def test_all_configured_routes_are_valid_route_objects() -> None:
    routes = load_route_objects()
    for route in routes:
        assert isinstance(route, Route)
        assert route.origin != route.destination


def test_all_routes_match_route_config_roundtrip() -> None:
    """RouteConfig → Route preserves the fields exactly."""
    configs = load_routes()
    models = load_route_objects()
    assert len(configs) == len(models)
    for cfg, mdl in zip(configs, models):
        assert cfg.origin == mdl.origin
        assert cfg.destination == mdl.destination
        assert cfg.distance_km == mdl.distance_km


def test_no_route_has_origin_equal_destination() -> None:
    routes = load_routes()
    for r in routes:
        assert r.origin != r.destination, f"origin equals destination for {r.origin}"


def test_distance_km_absent_is_allowed() -> None:
    configs = load_routes()
    # initial seed omits distance_km — confirm this doesn't reject the file
    assert all(c.distance_km is None for c in configs)


def test_load_routes_is_deterministic() -> None:
    first = load_routes()
    second = load_routes()
    assert first == second


def test_load_route_objects_is_deterministic() -> None:
    first = load_route_objects()
    second = load_route_objects()
    assert first == second


def test_no_duplicate_origin_destination_pairs() -> None:
    routes = load_routes()
    seen: set[tuple[str, str]] = set()
    for r in routes:
        pair = (r.origin, r.destination)
        assert pair not in seen, f"duplicate route pair {pair!r} found in config"
        seen.add(pair)


# ── RouteConfig direct-construction validation ─────────────────────────────

FALSY_IATA = [
    "DE",
    "DELH",
    "D3L",
    "de1",
    "",
    "12",
    "D L",
    "DE!",
    "DEL ",
]  # last has space


@pytest.mark.parametrize("bad", ["DE", "DELH", "D3L", "de1", "", "12", "D L"])
def test_route_config_rejects_invalid_iata_origin(bad: str) -> None:
    with pytest.raises(ValidationError):
        RouteConfig(origin=bad, destination="BOM")


@pytest.mark.parametrize("bad", ["DE", "BOMH", "B3M", "de1", "", "12", "B M"])
def test_route_config_rejects_invalid_iata_destination(bad: str) -> None:
    with pytest.raises(ValidationError):
        RouteConfig(origin="DEL", destination=bad)


def test_route_config_rejects_identical_origin_destination() -> None:
    with pytest.raises(ValidationError):
        RouteConfig(origin="DEL", destination="DEL")


def test_route_config_rejects_negative_distance() -> None:
    with pytest.raises(ValidationError):
        RouteConfig(origin="DEL", destination="BOM", distance_km=-1.0)


def test_route_config_allows_nonnegative_distance() -> None:
    for dist in [0.0, 0.5, 1138.0]:
        rc = RouteConfig(origin="DEL", destination="BOM", distance_km=dist)
        assert rc.distance_km == dist


def test_route_config_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RouteConfig(origin="DEL", destination="BOM", duration_minutes=60)


def test_route_config_requires_both_endpoints() -> None:
    with pytest.raises(ValidationError):
        RouteConfig.model_validate({"origin": "DEL"})
    with pytest.raises(ValidationError):
        RouteConfig.model_validate({"destination": "BOM"})


# ── loader validation against temporary files ──────────────────────────────


def _write_yaml_tmp(content: str) -> str:
    """Write content to a temp file and return its path; caller must unlink."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, textwrap.dedent(content).encode())
    os.close(fd)
    return path


def test_loader_rejects_invalid_iata_in_file() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DE
            destination: BOM
        """
    )
    try:
        with pytest.raises(ValueError, match="index 1|Invalid route"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_origin_equal_destination_in_file() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
            destination: DEL
        """
    )
    try:
        with pytest.raises(
            ValueError, match="origin and destination must differ|index 1"
        ):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_duplicate_route_in_file() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
            destination: BOM
          - origin: DEL
            destination: BOM
        """
    )
    try:
        with pytest.raises(ValueError, match="Duplicate route"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_negative_distance_in_file() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
            destination: BOM
            distance_km: -5
        """
    )
    try:
        with pytest.raises(ValueError, match="index 1|distance"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_malformed_entry_missing_destination() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
        """
    )
    try:
        with pytest.raises(ValueError, match="missing required|destination|index 1"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_malformed_entry_missing_origin() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - destination: BOM
        """
    )
    try:
        with pytest.raises(ValueError, match="missing required|origin|index 1"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_non_dict_entry() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - "DEL-BOM"
        """
    )
    try:
        with pytest.raises(ValueError, match="not a valid dict"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_missing_top_level_routes_key() -> None:
    path = _write_yaml_tmp(
        """
        cities: ["DEL", "BOM"]
        """
    )
    try:
        with pytest.raises(ValueError, match="Top-level 'routes' key missing"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_routes_not_a_list() -> None:
    path = _write_yaml_tmp(
        """
        routes: {DEL: BOM}
        """
    )
    try:
        with pytest.raises(ValueError, match="'routes' must be a list"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_rejects_malformed_yaml() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - {bad yaml: [[[
        """
    )
    try:
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_routes(path)
    finally:
        os.unlink(path)


def test_loader_accepts_optional_distance_km() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
            destination: BOM
            distance_km: 1138
          - origin: BOM
            destination: HYD
            distance_km: 712.5
        """
    )
    try:
        configs = load_routes(path)
        assert len(configs) == 2
        assert configs[0].distance_km == 1138.0
        assert configs[1].distance_km == 712.5
        # And the Route round-trip preserves them
        objs = load_route_objects(path)
        assert objs[0].distance_km == 1138.0
        assert objs[1].distance_km == 712.5
    finally:
        os.unlink(path)


def test_loader_accepts_distance_km_omitted() -> None:
    path = _write_yaml_tmp(
        """
        routes:
          - origin: DEL
            destination: BOM
          - origin: BOM
            destination: DEL
        """
    )
    try:
        configs = load_routes(path)
        assert all(c.distance_km is None for c in configs)
        objs = load_route_objects(path)
        assert all(o.distance_km is None for o in objs)
    finally:
        os.unlink(path)


def test_loader_nonexistent_file_raises_filenotfounderror() -> None:
    with pytest.raises(FileNotFoundError):
        load_routes("/nonexistent/path/routes.yaml")
