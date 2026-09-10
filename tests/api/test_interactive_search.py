
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.search import InteractiveSearchRequest
from cleartrip_ui import build_results_url


def test_interactive_request_maps_exact_search_job_fields():
    request = InteractiveSearchRequest(
        origin="del",
        destination="blr",
        departure_date="2026-09-16",
        adults=2,
        children=1,
        infants=0,
        cabin="ECONOMY",
        trip_type="ONE_WAY",
    )
    job = request.to_job()

    assert job.source == "cleartrip"
    assert job.origin == "DEL"
    assert job.destination == "BLR"
    assert job.iso_date == "2026-09-16"
    assert job.cleartrip_date == "16/09/2026"
    assert (job.adults, job.children, job.infants) == (2, 1, 0)
    assert job.cabin == "ECONOMY"
    assert job.trip_type == "ONE_WAY"

    url = build_results_url(
        origin=job.origin,
        destination=job.destination,
        depart_date=job.cleartrip_date,
        adults=job.adults,
        children=job.children,
        infants=job.infants,
    )
    assert "from=DEL" in url
    assert "to=BLR" in url
    assert "depart_date=16%2F09%2F2026" in url
    assert "adults=2" in url
    assert "childs=1" in url
    assert "infants=0" in url


def test_interactive_request_rejects_invalid_or_unsupported_searches():
    with pytest.raises(ValueError):
        InteractiveSearchRequest(
            origin="DEL", destination="DEL", departure_date="2026-09-16"
        )

    with pytest.raises(ValueError):
        InteractiveSearchRequest(
            origin="DEL",
            destination="BLR",
            departure_date="2026-09-16",
            adults=0,
        )

    with pytest.raises(ValueError):
        InteractiveSearchRequest(
            origin="DEL",
            destination="BLR",
            departure_date="2026-09-16",
            trip_type="ROUND_TRIP",
            return_date="2026-09-20",
        )


def test_unknown_interactive_job_returns_404():
    with TestClient(app) as client:
        response = client.get("/search/jobs/not-a-real-job")
    assert response.status_code == 404
