import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_api_import() -> None:
    """Ensure API app can be imported and initialized."""
    assert app.title == "Real-time Airfare Price Index API"


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    """Ensure /health endpoint returns HTTP 200 and valid JSON."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "airfare-index-india"
