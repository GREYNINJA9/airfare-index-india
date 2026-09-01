"""Thin FastAPI routes layer.

This module intentionally contains *no* index math and *no* raw SQL.
It orchestrates request handling by delegating to:

- database/repository.py for persistence and fare/index retrieval
- index_engine/* for deterministic index computation

The API surface is MVP-minimal so Swagger/OpenAPI can drive the frontend.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from database.connection import get_connection
from database.repository import (
    get_fares,
    get_index_result,
    get_index_results,
    insert_index_result,
)
from database.schema import init_schema
from index_engine.aggregation import aggregate_item_price_relatives
from index_engine.api_index import compute_overall_airfare_index
from index_engine.weights import compute_uniform_base_basket_weights
from models.fare import Fare
from models.index import IndexResult

router = APIRouter()


def _db_conn():
    conn = get_connection()
    init_schema(conn)
    return conn


@router.get("/fares", response_model=List[Fare])
def list_fares(
    origin: Optional[str] = Query(
        default=None,
        min_length=3,
        max_length=3,
        description="IATA origin airport code (e.g. DEL).",
    ),
    destination: Optional[str] = Query(
        default=None,
        min_length=3,
        max_length=3,
        description="IATA destination airport code (e.g. BOM).",
    ),
):
    """Return persisted Fare observations.

    If both `origin` and `destination` are provided, the response is filtered
    to that route.
    """

    if (origin is None) != (destination is None):
        raise HTTPException(
            status_code=400,
            detail="Provide both origin and destination to filter by route.",
        )

    conn = _db_conn()
    fares = get_fares(conn)
    if origin is not None and destination is not None:
        origin_norm = origin.strip().upper()
        destination_norm = destination.strip().upper()
        fares = [
            f
            for f in fares
            if f.route.origin == origin_norm and f.route.destination == destination_norm
        ]
    return fares


@router.get("/index", response_model=IndexResult)
def get_index(
    current_period: date = Query(
        ..., description="UTC daily period date for the index computation."
    ),
) -> IndexResult:
    """Compute (and persist) the overall airfare index for `current_period`.

    Base period selection is handled by the existing Phase-2 aggregation
    implementation.
    """

    conn = _db_conn()
    fares = get_fares(conn)

    try:
        relatives = aggregate_item_price_relatives(
            fares,
            current_period=current_period,
        )
        weights = compute_uniform_base_basket_weights(relatives.item_price_relatives)
        computed = compute_overall_airfare_index(relatives, weights)
    except ValueError as e:
        # Preserve the index engine's defined error semantics.
        raise HTTPException(status_code=400, detail=str(e)) from e

    existing = get_index_result(
        conn,
        base_period=computed.base_period,
        current_period=computed.current_period,
    )
    if existing is not None:
        return existing

    insert_index_result(conn, computed)
    persisted = get_index_result(
        conn,
        base_period=computed.base_period,
        current_period=computed.current_period,
    )
    if persisted is None:
        raise HTTPException(
            status_code=500,
            detail="IndexResult persistence failed unexpectedly.",
        )
    return persisted


@router.get("/index/history", response_model=List[IndexResult])
def index_history(
    base_period: Optional[date] = Query(
        default=None,
        description="Optional filter: base period date (YYYY-MM-DD).",
    ),
    current_period: Optional[date] = Query(
        default=None,
        description="Optional filter: current period date (YYYY-MM-DD).",
    ),
) -> List[IndexResult]:
    """Return persisted IndexResult history."""

    conn = _db_conn()
    return get_index_results(
        conn,
        base_period=base_period,
        current_period=current_period,
    )
