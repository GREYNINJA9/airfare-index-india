import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI

from api.routes import router as api_router
from database.connection import get_connection
from database.schema import init_schema

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
    # Could close connection pool here if applicable


app = FastAPI(
    title="Real-time Airfare Price Index API",
    description="API foundation for India Consumer Price Index (CPI) Augmentation",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(api_router)


@app.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint to prove application container is alive."""
    logger.info("Health check endpoint pinged")
    return {"status": "healthy", "service": "airfare-index-india", "version": "0.1.0"}
