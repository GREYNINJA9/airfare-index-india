import logging
from typing import Any, Dict

from fastapi import FastAPI

from api.routes import router as api_router

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("airfare_index_api")

app = FastAPI(
    title="Real-time Airfare Price Index API",
    description="API foundation for India Consumer Price Index (CPI) Augmentation",
    version="0.1.0",
)


app.include_router(api_router)


@app.get("/health", response_model=Dict[str, Any])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint to prove application container is alive."""
    logger.info("Health check endpoint pinged")
    return {"status": "healthy", "service": "airfare-index-india", "version": "0.1.0"}
