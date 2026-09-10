"""Interactive user-initiated Cleartrip search endpoints."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database.repository import get_fares
from models.fare import Fare
from scheduler.jobs import run_search_job
from scheduler.search import SearchJob

logger = logging.getLogger("api.search")
router = APIRouter(prefix="/search", tags=["Interactive Search"])
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="interactive-search")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class InteractiveSearchRequest(BaseModel):
    """Exact user search contract accepted by the backend."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: str
    return_date: str | None = None
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    infants: int = Field(default=0, ge=0)
    cabin: str = Field(
        default="ECONOMY",
        pattern="^(ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST)$",
    )
    trip_type: str = Field(default="ONE_WAY", pattern="^(ONE_WAY|ROUND_TRIP)$")

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return str(value).strip().upper()

    @field_validator("departure_date", "return_date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(value.strip(), fmt).date()
                if parsed < date.today():
                    raise ValueError("departure and return dates cannot be in the past")
                return parsed.isoformat()
            except ValueError as exc:
                if "cannot be in the past" in str(exc):
                    raise
        raise ValueError("date must be YYYY-MM-DD or DD/MM/YYYY")

    @model_validator(mode="after")
    def validate_search(self) -> "InteractiveSearchRequest":
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.trip_type == "ROUND_TRIP":
            raise ValueError("round-trip interactive searches are not supported yet")
        if self.return_date is not None:
            raise ValueError("return_date is only valid for supported round-trip searches")
        return self

    def to_job(self) -> SearchJob:
        return SearchJob(
            source="cleartrip",
            origin=self.origin,
            destination=self.destination,
            departure_date=self.departure_date,
            adults=self.adults,
            children=self.children,
            infants=self.infants,
            cabin=self.cabin,
            trip_type=self.trip_type,
        )


def _fare_matches(fare: Fare, job: SearchJob) -> bool:
    """Keep only observations belonging to this exact user search."""
    return (
        fare.route.origin == job.origin
        and fare.route.destination == job.destination
        and fare.cabin_class.value == job.cabin
        and fare.trip_type.value == job.trip_type
        and fare.departure_at.date().isoformat() == job.iso_date
        and fare.source.source_name.lower() == "cleartrip"
    )


def _serialize_fare(fare: Fare) -> dict[str, Any]:
    data = fare.model_dump(mode="json")
    data["source"] = data["source"]
    return data


def _run_interactive_job(job_id: str, job: SearchJob) -> None:
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        summary = run_search_job(job, save_raw=False, compute_index=False)
        from database.connection import get_connection

        matching = [fare for fare in get_fares(get_connection()) if _fare_matches(fare, job)]
        with _jobs_lock:
            _jobs[job_id].update(
                status="completed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                summary=summary,
                result_count=len(matching),
                results=[_serialize_fare(fare) for fare in matching],
            )
    except Exception as exc:
        logger.exception("Interactive search failed: job_id=%s", job_id)
        with _jobs_lock:
            _jobs[job_id].update(
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_search_job(request: InteractiveSearchRequest) -> dict[str, Any]:
    job = request.to_job()
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "job_id": job_id,
        "status": "queued",
        "source": job.source,
        "origin": job.origin,
        "destination": job.destination,
        "departure_date": job.iso_date,
        "return_date": job.return_date,
        "adults": job.adults,
        "children": job.children,
        "infants": job.infants,
        "cabin": job.cabin,
        "trip_type": job.trip_type,
        "created_at": now,
        "result_count": 0,
        "results": [],
    }
    with _jobs_lock:
        _jobs[job_id] = record
    _executor.submit(_run_interactive_job, job_id, job)
    return {key: value for key, value in record.items() if key != "results"}


@router.get("/jobs/{job_id}")
def get_search_job(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        record = _jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="search job not found")
        return dict(record)
