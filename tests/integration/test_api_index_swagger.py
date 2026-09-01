"""Deterministic API tests for FastAPI Swagger-visible MVP endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from database.connection import close_connection, reset_connection
from database.repository import insert_fare
from database.schema import init_schema
from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_uniform_base_basket_weights
from models.fare import CabinClass, Fare, RawFareSource, SourceType, TripType
from models.index import IndexMethodologyMetadata, IndexResult
from models.route import Route


def _source(*, name: str, price_inr: float, raw_offer_id: str) -> RawFareSource:
    return RawFareSource.model_validate(
        {
            "source_name": name,
            "source_type": SourceType.OTA
            if name.endswith("OTA")
            else SourceType.AIRLINE,
            "raw_price": float(price_inr),
            "raw_currency": "INR",
            "raw_cabin_label": "Economy",
            "source_url": "https://example.com/fare",
            "raw_offer_id": raw_offer_id,
        }
    )


def _fare(
    *,
    origin: str,
    destination: str,
    cabin_class: CabinClass,
    trip_type: TripType,
    scraped_at: datetime,
    price_inr: float,
    airline_code: str,
    source_name: str,
    raw_offer_id: str,
) -> Fare:
    departure_at = scraped_at + timedelta(days=20)
    route = Route(origin=origin, destination=destination)

    return Fare.model_validate(
        {
            "route": route.model_dump(),
            "airline_code": airline_code,
            "price_inr": float(price_inr),
            "cabin_class": cabin_class,
            "departure_at": departure_at,
            "scraped_at": scraped_at,
            "trip_type": trip_type,
            "source": _source(
                name=source_name,
                price_inr=price_inr,
                raw_offer_id=raw_offer_id,
            ),
        }
    )


@pytest.fixture()
def api_db():
    """Isolated in-memory DB for each API test."""

    conn = reset_connection(path=":memory:")
    init_schema(conn)
    try:
        yield conn
    finally:
        close_connection()


@pytest.fixture()
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint_still_works(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_docs_and_openapi_present(client: AsyncClient) -> None:
    openapi = await client.get("/openapi.json")
    assert openapi.status_code == 200
    openapi_payload = openapi.json()
    assert "paths" in openapi_payload

    # Expected endpoints are visible to Swagger.
    paths = set(openapi_payload["paths"].keys())
    assert "/health" in paths
    assert "/fares" in paths
    assert "/index" in paths
    assert "/index/history" in paths

    docs = await client.get("/docs")
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text


@pytest.mark.asyncio
async def test_fares_empty_db_returns_empty_list(api_db, client: AsyncClient) -> None:
    response = await client.get("/fares")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_fares_route_filter_requires_both_origin_and_destination(
    api_db, client: AsyncClient
) -> None:
    response = await client.get("/fares", params={"origin": "DEL"})
    assert response.status_code == 400
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_fares_route_filter_returns_expected_rows(
    api_db, client: AsyncClient
) -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    fares = [
        _fare(
            origin="DEL",
            destination="BOM",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
            raw_offer_id="A-d0",
        ),
        _fare(
            origin="DEL",
            destination="HYD",
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=200.0,
            airline_code="6E",
            source_name="S2",
            raw_offer_id="B-d0",
        ),
    ]

    for f in fares:
        assert insert_fare(api_db, f) > 0

    response = await client.get(
        "/fares", params={"origin": "DEL", "destination": "BOM"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["route"]["origin"] == "DEL"
    assert payload[0]["route"]["destination"] == "BOM"
    assert payload[0]["price_inr"] == 100.0


@pytest.mark.asyncio
async def test_index_empty_db_returns_400(api_db, client: AsyncClient) -> None:
    response = await client.get("/index", params={"current_period": "2026-08-28"})
    assert response.status_code == 400
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_index_invalid_current_period_returns_422(
    api_db, client: AsyncClient
) -> None:
    response = await client.get("/index", params={"current_period": "bad"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_index_endpoint_computes_persists_and_history_works(
    api_db, client: AsyncClient
) -> None:
    d0 = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
    d1 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)

    item_a = ("DEL", "BOM")
    item_b = ("DEL", "HYD")

    fares = [
        _fare(
            origin=item_a[0],
            destination=item_a[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=100.0,
            airline_code="6E",
            source_name="S1",
            raw_offer_id="A-d0",
        ),
        _fare(
            origin=item_b[0],
            destination=item_b[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d0,
            price_inr=80.0,
            airline_code="6E",
            source_name="S2",
            raw_offer_id="B-d0",
        ),
        _fare(
            origin=item_a[0],
            destination=item_a[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=110.0,
            airline_code="6E",
            source_name="S1",
            raw_offer_id="A-d1",
        ),
        _fare(
            origin=item_b[0],
            destination=item_b[1],
            cabin_class=CabinClass.ECONOMY,
            trip_type=TripType.ONE_WAY,
            scraped_at=d1,
            price_inr=90.0,
            airline_code="6E",
            source_name="S2",
            raw_offer_id="B-d1",
        ),
    ]

    for f in fares:
        assert insert_fare(api_db, f) > 0

    # Expected from existing engine (no formula duplication).
    relatives = aggregate_item_price_relatives(fares, current_period=d1.date())
    weights = compute_uniform_base_basket_weights(relatives.item_price_relatives)
    expected = compute_overall_airfare_index(relatives, weights)
    assert expected.methodology == IndexMethodologyMetadata()
    assert isinstance(expected, IndexResult)

    response = await client.get(
        "/index", params={"current_period": d1.date().isoformat()}
    )
    assert response.status_code == 200
    actual_payload = response.json()

    actual = IndexResult.model_validate(actual_payload)
    assert actual == expected

    # Repeat call should return the same persisted result.
    response2 = await client.get(
        "/index", params={"current_period": d1.date().isoformat()}
    )
    assert response2.status_code == 200
    actual2 = IndexResult.model_validate(response2.json())
    assert actual2 == expected

    # History retrieval should return exactly one matching record.
    history = await client.get(
        "/index/history",
        params={
            "base_period": expected.base_period.isoformat(),
            "current_period": expected.current_period.isoformat(),
        },
    )
    assert history.status_code == 200
    history_payload = history.json()
    assert len(history_payload) == 1

    hist_result = IndexResult.model_validate(history_payload[0])
    assert hist_result == expected

    # Emptying scenario is not applicable here; DB has fares and persisted index.
