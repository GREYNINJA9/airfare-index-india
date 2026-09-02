from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest

from config.loader import load_route_objects
from database.connection import close_connection, reset_connection
from database.repository import get_fares, get_index_results
from database.schema import init_schema
from scheduler.jobs import run_collection_cycle


@pytest.fixture()
def conn():
    connection = reset_connection(path=":memory:")
    init_schema(connection)
    yield connection
    close_connection()


def _assert_both_sources_contributed(fares):
    source_names = {f.source.source_name for f in fares}
    assert source_names == {"MakeMyTrip", "ClearTrip"}


def test_successful_collection_cycle_both_sources_and_multiple_routes(conn):
    summary = run_collection_cycle(conn=conn)

    assert summary["sources_attempted"] == 2
    assert summary["sources_successful"] == 2
    assert summary["sources_failed"] == 0
    assert summary["source_errors"] == {}

    routes = load_route_objects()
    assert len(routes) == 6

    assert summary["raw_records_extracted"] == len(routes) * 2
    assert summary["normalized_fares"] == len(routes) * 2
    assert summary["fares_inserted"] == len(routes) * 2
    assert summary["duplicate_fares_skipped"] == 0

    assert summary["index_generated"] is True
    assert summary["current_period"] is not None
    assert summary["base_period"] is not None

    # Scrapers in this repo emit deterministic scraped_at=2026-08-27.
    assert summary["current_period"] == "2026-08-27"
    assert summary["base_period"] == "2026-08-27"

    # With a single-day dataset, all relatives are 1.0 → indices are 100.0.
    assert summary["overall_laspeyres_index"] == pytest.approx(100.0)
    assert summary["overall_jevons_index"] == pytest.approx(100.0)

    persisted = get_index_results(
        conn,
        base_period=date.fromisoformat(summary["base_period"]),
        current_period=date.fromisoformat(summary["current_period"]),
    )
    assert len(persisted) == 1

    fares = get_fares(conn)
    assert len(fares) == len(routes) * 2
    _assert_both_sources_contributed(fares)


def test_one_source_failure_does_not_block_other_sources(conn, tmp_path: Path):
    # ClearTrip module import will fail; MakeMyTrip should still run.
    sources_yaml = textwrap.dedent(
        """
        sources:
          - name: MakeMyTrip
            source_type: OTA
            enabled: true
            module: scraper.otas.mmt
            class: MakeMyTripScraper
          - name: ClearTrip
            source_type: OTA
            enabled: true
            module: scraper.otas.this_module_does_not_exist
            class: NoSuchClass
        """
    ).strip()

    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(sources_yaml, encoding="utf-8")

    summary = run_collection_cycle(conn=conn, sources_path=str(sources_path))

    assert summary["sources_attempted"] == 2
    assert summary["sources_successful"] == 1
    assert summary["sources_failed"] == 1
    assert "ClearTrip" in summary["source_errors"]

    routes = load_route_objects()
    assert summary["normalized_fares"] == len(routes)
    assert summary["fares_inserted"] == len(routes)

    fares = get_fares(conn)
    assert {f.source.source_name for f in fares} == {"MakeMyTrip"}

    assert summary["index_generated"] is True
    assert summary["current_period"] == "2026-08-27"


def test_zero_extracted_fares_skips_index_and_persistence(conn, tmp_path: Path):
    # Create a deterministic dummy scraper that returns [] for all routes.
    empty_scraper_py = textwrap.dedent(
        """
        from __future__ import annotations

        from models.fare import SourceType


        class EmptyScraper:
            _templates = {
                "del_bom_economy": (
                    "<div class=\"flight-card\" data-route=\"DEL-BOM\"></div>"
                )
            }

            def __init__(self) -> None:
                self._name = "Empty"
                self._source_type = SourceType.OTA

            @property
            def name(self) -> str:
                return self._name

            @property
            def source_type(self) -> SourceType:
                return self._source_type

            def extract(self, html: str, route=None):
                return []
        """
    ).strip()

    module_path = tmp_path / "empty_scraper.py"
    module_path.write_text(empty_scraper_py, encoding="utf-8")

    # Ensure the temporary directory is importable.
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        sources_yaml = textwrap.dedent(
            """
            sources:
              - name: Empty
                source_type: OTA
                enabled: true
                module: empty_scraper
                class: EmptyScraper
            """
        ).strip()

        sources_path = tmp_path / "sources.yaml"
        sources_path.write_text(sources_yaml, encoding="utf-8")

        summary = run_collection_cycle(conn=conn, sources_path=str(sources_path))

        assert summary["raw_records_extracted"] == 0
        assert summary["normalized_fares"] == 0
        assert summary["fares_inserted"] == 0
        assert summary["duplicate_fares_skipped"] == 0
        assert summary["index_generated"] is False
        assert summary["index_skipped_reason"] == "no_normalized_fares"

        assert get_index_results(conn) == []
        assert get_index_results(conn, base_period=None, current_period=None) == []

    finally:
        # Best-effort cleanup of sys.path.
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_duplicate_collection_cycle_is_idempotent(conn):
    summary1 = run_collection_cycle(conn=conn)
    fares_after_first = len(get_fares(conn))
    assert summary1["fares_inserted"] == fares_after_first
    assert summary1["duplicate_fares_skipped"] == 0
    assert summary1["index_generated"] is True

    summary2 = run_collection_cycle(conn=conn)
    fares_after_second = len(get_fares(conn))
    assert fares_after_second == fares_after_first

    assert summary2["normalized_fares"] == fares_after_first
    assert summary2["fares_inserted"] == 0
    assert summary2["duplicate_fares_skipped"] == fares_after_first
    assert summary2["index_generated"] is False

    persisted = get_index_results(
        conn,
        base_period=date.fromisoformat(summary1["base_period"]),
        current_period=date.fromisoformat(summary1["current_period"]),
    )
    assert len(persisted) == 1


def test_disabled_source_is_not_executed(conn, tmp_path: Path):
    sources_yaml = textwrap.dedent(
        """
        sources:
          - name: MakeMyTrip
            source_type: OTA
            enabled: true
            module: scraper.otas.mmt
            class: MakeMyTripScraper
          - name: ClearTrip
            source_type: OTA
            enabled: false
            module: scraper.otas.cleartrip
            class: ClearTripScraper
        """
    ).strip()

    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(sources_yaml, encoding="utf-8")

    summary = run_collection_cycle(conn=conn, sources_path=str(sources_path))

    assert summary["sources_attempted"] == 1
    assert summary["sources_successful"] == 1
    assert summary["sources_failed"] == 0

    routes = load_route_objects()
    assert summary["normalized_fares"] == len(routes)

    fares = get_fares(conn)
    assert {f.source.source_name for f in fares} == {"MakeMyTrip"}


def test_deterministic_run_on_fresh_db(conn):
    summary1 = run_collection_cycle(conn=conn)

    # Fresh DB with same configuration should produce identical summary fields.
    conn2 = reset_connection(path=":memory:")
    try:
        init_schema(conn2)
        summary2 = run_collection_cycle(conn=conn2)

        assert summary2["raw_records_extracted"] == summary1["raw_records_extracted"]
        assert summary2["normalized_fares"] == summary1["normalized_fares"]
        assert summary2["fares_inserted"] == summary1["fares_inserted"]
        assert (
            summary2["duplicate_fares_skipped"] == summary1["duplicate_fares_skipped"]
        )

        assert summary2["index_generated"] is True
        assert summary2["base_period"] == summary1["base_period"]
        assert summary2["current_period"] == summary1["current_period"]
        assert (
            summary2["overall_laspeyres_index"] == summary1["overall_laspeyres_index"]
        )
        assert summary2["overall_jevons_index"] == summary1["overall_jevons_index"]
    finally:
        close_connection()
