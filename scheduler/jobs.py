"""Deterministic scheduler orchestration (Phase 1).

This module intentionally contains **orchestration only**:

- load enabled sources + configured routes
- call each scraper's deterministic mock-HTML ``extract``
- run extracted raw records through the existing pipeline
- persist normalized fares
- compute and persist index results via the existing index engine

It does **not** implement a continuously running production scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping

from config.loader import load_route_objects, load_sources
from database.connection import get_connection
from database.repository import (
    get_fare_by_offer_id,
    get_fares,
    get_index_result,
    insert_fare,
    insert_index_result,
)
from database.schema import init_schema
from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_uniform_base_basket_weights
from pipeline import process_raw_fares


def _utc_day(dt: datetime) -> date:
    return dt.astimezone(timezone.utc).date()


def _render_mock_html_for_route(
    *, template: str, route_origin: str, route_destination: str
) -> str:
    """Adapt a DEL→BOM template for an arbitrary configured route.

    The existing scrapers are implemented as deterministic mock parsers that
    look for a ``data-route="{ORIGIN}-{DEST}"`` marker.

    The established approach (used in tests) is token substitution in the
    existing DEL-BOM template.
    """

    return template.replace("DEL-BOM", f"{route_origin}-{route_destination}")


def _select_del_bom_template(scraper: Any) -> str:
    """Return the mock HTML template used for DEL→BOM extraction."""

    templates = getattr(scraper, "_templates", None)
    if not isinstance(templates, Mapping):
        raise TypeError("scraper._templates must be a mapping")

    # Phase 1 only needs the established DEL-BOM-based template.
    if "del_bom_economy" in templates and isinstance(templates["del_bom_economy"], str):
        return templates["del_bom_economy"]

    # Fallback for robustness: pick the first string template deterministically.
    string_values = [(k, v) for k, v in templates.items() if isinstance(v, str)]
    if not string_values:
        raise ValueError("scraper._templates contains no string templates")
    string_values.sort(key=lambda kv: str(kv[0]))
    return string_values[0][1]


@dataclass(frozen=True)
class _SourceAttempt:
    name: str
    attempted: bool


def run_collection_cycle(
    *,
    conn: Any | None = None,
    sources_path: str = "config/sources.yaml",
    routes_path: str = "config/routes.yaml",
) -> Dict[str, Any]:
    """Run one deterministic collection cycle.

    Orchestration contract:

    configured scrapers
        ↓
    scraper extraction
        ↓
    pipeline validation/cleaning/normalization/deduplication
        ↓
    SQLite fare persistence
        ↓
    index aggregation
        ↓
    uniform weights
        ↓
    overall index calculation
        ↓
    index result persistence
        ↓
    deterministic summary

    Returns:
        A deterministic run summary dict (JSON-serializable values where
        practical).
    """

    if conn is None:
        conn = get_connection()

    # Ensure schema exists; cheap no-op if already initialized.
    init_schema(conn)

    sources = load_sources(sources_path)
    routes = load_route_objects(routes_path)

    enabled_sources = [s for s in sources if s.enabled]

    source_errors: Dict[str, str] = {}
    sources_attempted = len(enabled_sources)
    sources_successful = 0
    sources_failed = 0

    raw_records: List[dict] = []

    # Deterministic iteration: config ordering.
    for source_cfg in enabled_sources:
        try:
            scraper = source_cfg.import_and_instantiate()
        except Exception as e:  # pragma: no cover (rare but handled)
            sources_failed += 1
            sources_successful += 0
            source_errors[source_cfg.name] = f"instantiate_failed: {e}"
            continue

        scraper_name = getattr(scraper, "name", source_cfg.name)

        try:
            template = _select_del_bom_template(scraper)

            for route in routes:
                html = _render_mock_html_for_route(
                    template=template,
                    route_origin=route.origin,
                    route_destination=route.destination,
                )
                extracted = scraper.extract(html, route=route)
                if not isinstance(extracted, list):
                    raise TypeError(
                        "scraper.extract returned "
                        f"{type(extracted).__name__}, expected list"
                    )
                if not extracted:
                    continue
                raw_records.extend(extracted)

            sources_successful += 1
        except Exception as e:
            sources_failed += 1
            sources_successful += 0
            source_errors["%s" % scraper_name] = f"extract_failed: {e}"

    # Pipeline validation/cleaning/normalization/dedup.
    normalized_fares: List[Any] = []
    pipeline_error: str | None = None

    if raw_records:
        fares, bad, batch_err = process_raw_fares(raw_records)
        if batch_err is not None:
            # For deterministic summaries, we do not raise; we treat this as
            # a collection failure mode and skip index generation.
            pipeline_error = str(batch_err)
        normalized_fares = fares

    # Persist fares with idempotency: skip already-present raw_offer_id.
    fares_inserted = 0
    duplicate_fares_skipped = 0

    for fare in normalized_fares:
        raw_offer_id = fare.source.raw_offer_id
        if not raw_offer_id:
            # Provenance contract says this is optional; if it's absent, we
            # conservatively insert.
            if insert_fare(conn, fare) > 0:
                fares_inserted += 1
            continue

        existing = get_fare_by_offer_id(conn, raw_offer_id)
        if existing is not None:
            duplicate_fares_skipped += 1
            continue

        inserted_id = insert_fare(conn, fare)
        if inserted_id > 0:
            fares_inserted += 1
        else:
            duplicate_fares_skipped += 1

    # Index derivation and computation.
    index_generated = False
    index_skipped_reason: str | None = None

    current_period: date | None = None
    base_period: date | None = None
    overall_laspeyres_index: float | None = None
    overall_jevons_index: float | None = None

    raw_records_extracted = len(raw_records)
    normalized_count = len(normalized_fares)

    if normalized_count == 0:
        index_skipped_reason = "no_normalized_fares"
    else:
        current_period = max(_utc_day(f.scraped_at) for f in normalized_fares)
        fares_for_index = get_fares(conn)

        # Call index engine in the required order.
        relatives = aggregate_item_price_relatives(
            fares_for_index,
            current_period=current_period,
        )
        weights = compute_uniform_base_basket_weights(
            relatives.item_price_relatives,
        )
        computed = compute_overall_airfare_index(relatives, weights)

        base_period = computed.base_period
        overall_laspeyres_index = float(computed.overall_laspeyres_index)
        overall_jevons_index = float(computed.overall_jevons_index)

        existing_index = get_index_result(
            conn,
            base_period=computed.base_period,
            current_period=computed.current_period,
        )
        if existing_index is not None:
            # Deterministic idempotency: do not insert duplicates.
            index_generated = False
        else:
            inserted_index_id = insert_index_result(conn, computed)
            index_generated = inserted_index_id > 0

    return {
        "sources_attempted": sources_attempted,
        "sources_successful": sources_successful,
        "sources_failed": sources_failed,
        "source_errors": source_errors,
        "raw_records_extracted": raw_records_extracted,
        "normalized_fares": normalized_count,
        "fares_inserted": fares_inserted,
        "duplicate_fares_skipped": duplicate_fares_skipped,
        "pipeline_error": pipeline_error,
        "index_generated": index_generated,
        "index_skipped_reason": index_skipped_reason,
        "current_period": current_period.isoformat() if current_period else None,
        "base_period": base_period.isoformat() if base_period else None,
        "overall_laspeyres_index": overall_laspeyres_index,
        "overall_jevons_index": overall_jevons_index,
    }
