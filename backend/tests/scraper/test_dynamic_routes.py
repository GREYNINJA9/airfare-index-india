"""Dynamic route integration tests (deterministic, mock HTML only).

These tests validate that scrapers can accept a supplied `models.route.Route`
object and constrain extraction/output accordingly.

No live network calls are made; HTML inputs are deterministic and derived
from the existing mock templates.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config.loader import load_route_objects
from backend.database.repository import get_fares_by_route, insert_fare
from backend.models.route import Route
from backend.pipeline import process_raw_fares
from backend.scraper.otas.cleartrip import _MOCK_FLIGHT_CARD as CT_MOCK_CARD
from backend.scraper.otas.cleartrip import ClearTripScraper
from backend.scraper.otas.mmt import _MOCK_FLIGHT_CARD as MMT_MOCK_CARD
from backend.scraper.otas.mmt import MakeMyTripScraper


def _render_mock_html(template: str, route: Route) -> str:
    """Render a deterministic mock HTML card for `route`.

    The existing mock templates are written for DEL→BOM and embed that token
    in `data-route`, href, and offer-id-like substrings. Extraction logic
    only requires the `data-route` marker; replacing the token keeps the
    rest of the HTML deterministic.
    """

    return template.replace("DEL-BOM", f"{route.origin}-{route.destination}")


def _configured_route(origin: str, destination: str) -> Route:
    routes = load_route_objects()
    for r in routes:
        if r.origin == origin and r.destination == destination:
            return r
    raise AssertionError(f"Configured route not found: {origin} → {destination}")


# ── Route construction / invalid-input behavior ──────────────────────────


def test_invalid_route_rejected_before_scraping() -> None:
    with pytest.raises(ValidationError):
        Route(origin="DE", destination="BOM")

    with pytest.raises(ValidationError):
        Route(origin="DEL", destination="DEL")


# ── MMT: dynamic route input ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "origin,destination",
    [
        ("DEL", "BOM"),
        ("BOM", "DEL"),
        ("DEL", "BLR"),
    ],
)
def test_mmt_extract_accepts_supplied_route(origin: str, destination: str) -> None:
    route = _configured_route(origin, destination)
    scraper = MakeMyTripScraper()

    html = _render_mock_html(MMT_MOCK_CARD, route)
    raw = scraper.extract(html, route=route)

    assert len(raw) == 1
    assert raw[0]["route"]["origin"] == origin
    assert raw[0]["route"]["destination"] == destination
    # Configured routes omit distance_km; scrapers must not invent it.
    assert raw[0]["route"]["distance_km"] is None
    assert raw[0]["source"]["raw_offer_id"] == f"MT-{origin}-{destination}-1"


def test_mmt_extract_filters_by_supplied_route() -> None:
    scraper = MakeMyTripScraper()

    requested = Route(origin="BOM", destination="DEL")
    wrong_route = Route(origin="DEL", destination="BOM")
    wrong_html = _render_mock_html(MMT_MOCK_CARD, wrong_route)

    raw = scraper.extract(wrong_html, route=requested)
    assert raw == []


def test_mmt_configured_routes_pipeline_database(db) -> None:
    scraper = MakeMyTripScraper()

    routes = [
        _configured_route("DEL", "BOM"),
        _configured_route("BOM", "DEL"),
        _configured_route("DEL", "BLR"),
    ]

    raw_batch: list[dict] = []
    for route in routes:
        html = _render_mock_html(MMT_MOCK_CARD, route)
        raw_batch.extend(scraper.extract(html, route=route))

    fares, bad, err = process_raw_fares(raw_batch)
    assert err is None
    assert not bad
    assert len(fares) == 3

    for fare in fares:
        assert insert_fare(db, fare) > 0

    assert len(get_fares_by_route(db, "DEL", "BOM")) == 1
    assert len(get_fares_by_route(db, "BOM", "DEL")) == 1
    assert len(get_fares_by_route(db, "DEL", "BLR")) == 1


# ── ClearTrip: dynamic route input ─────────────────────────────────────────


@pytest.mark.parametrize(
    "origin,destination",
    [
        ("DEL", "BOM"),
        ("BOM", "DEL"),
        ("DEL", "BLR"),
    ],
)
def test_cleartrip_extract_accepts_supplied_route(
    origin: str,
    destination: str,
) -> None:
    route = _configured_route(origin, destination)
    scraper = ClearTripScraper()

    html = _render_mock_html(CT_MOCK_CARD, route)
    raw = scraper.extract(html, route=route)

    assert len(raw) == 1
    assert raw[0]["route"]["origin"] == origin
    assert raw[0]["route"]["destination"] == destination
    assert raw[0]["route"]["distance_km"] is None
    assert raw[0]["source"]["raw_offer_id"] == f"CT-{origin}-{destination}-1"


def test_cleartrip_extract_filters_by_supplied_route() -> None:
    scraper = ClearTripScraper()

    requested = Route(origin="BOM", destination="DEL")
    wrong_html = _render_mock_html(CT_MOCK_CARD, Route(origin="DEL", destination="BOM"))

    raw = scraper.extract(wrong_html, route=requested)
    assert raw == []


def test_cleartrip_configured_routes_pipeline_database(db) -> None:
    scraper = ClearTripScraper()

    routes = [
        _configured_route("DEL", "BOM"),
        _configured_route("BOM", "DEL"),
        _configured_route("DEL", "BLR"),
    ]

    raw_batch: list[dict] = []
    for route in routes:
        html = _render_mock_html(CT_MOCK_CARD, route)
        raw_batch.extend(scraper.extract(html, route=route))

    fares, bad, err = process_raw_fares(raw_batch)
    assert err is None
    assert not bad
    assert len(fares) == 3

    for fare in fares:
        assert insert_fare(db, fare) > 0

    assert len(get_fares_by_route(db, "DEL", "BOM")) == 1
    assert len(get_fares_by_route(db, "BOM", "DEL")) == 1
    assert len(get_fares_by_route(db, "DEL", "BLR")) == 1
