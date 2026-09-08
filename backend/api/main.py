"""Main FastAPI application entry point.

Mounts:
- Core index routes (/fares, /index, /index/history)
- Analytics routes (/api/analytics/...)
- Fares search routes (/api/fares/...)
- Interactive web dashboard (/, /dashboard)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.analytics import router as analytics_router
from backend.api.dashboard.app import router as dashboard_router
from backend.api.fares import router as fares_router
from backend.api.routes import router as api_router
from backend.database.connection import get_connection
from backend.database.schema import init_schema

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("airfare_index_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema on startup...")
    conn = get_connection()
    init_schema(conn)
    yield


app = FastAPI(
    title="Real-time Airfare Price Index API",
    description="Automated Airfare Price Index & CPI Augmentation Platform for MoSPI and RBI (SIH 2026 - Problem 26056)",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for external research/institutional dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount domain routers
app.include_router(dashboard_router)
app.include_router(api_router)
app.include_router(fares_router)
app.include_router(analytics_router)


@app.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint proving application container is alive."""
    logger.info("Health check endpoint pinged")
    return {
        "status": "healthy",
        "service": "airfare-index-india",
        "version": "1.0.0",
        "problem_statement_id": "26056",
        "organization": "MoSPI / DIID",
    }
