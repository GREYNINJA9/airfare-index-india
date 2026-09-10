"""Production scheduler entry point for configured Cleartrip searches."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from config.loader import load_route_objects
from scheduler.jobs import run_configured_search_cycle

logger = logging.getLogger("scheduler.runner")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _configured_dates() -> list[str]:
    configured = os.environ.get("SCHEDULER_DEPARTURE_DATES", "").strip()
    if configured:
        return [value.strip() for value in configured.split(",") if value.strip()]
    return [datetime.now(timezone.utc).strftime("%Y-%m-%d")]


def _configured_routes():
    configured = os.environ.get("SCHEDULER_ROUTES", "").strip()
    routes = load_route_objects()
    if not configured:
        return routes

    wanted = {
        tuple(part.strip().upper() for part in value.split("-", 1))
        for value in configured.split(",")
        if "-" in value
    }
    return [route for route in routes if (route.origin, route.destination) in wanted]


def run_once() -> dict:
    """Execute one configured collection cycle and return its real summary."""
    routes = _configured_routes()
    dates = _configured_dates()
    if not routes:
        raise ValueError("SCHEDULER_ROUTES did not match any configured route")

    logger.info(
        "Starting collection cycle: routes=%d dates=%s", len(routes), dates
    )
    summary = run_configured_search_cycle(
        routes=routes,
        dates=dates,
        save_raw=_env_bool("SAVE_RAW"),
        compute_index=True,
    )
    logger.info("Collection cycle summary: %s", summary)
    return summary


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    interval = max(60, int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "3600")))
    run_once()
    if _env_bool("SCHEDULER_ONCE"):
        return 0

    while True:
        logger.info("Next collection cycle in %d seconds", interval)
        time.sleep(interval)
        run_once()


if __name__ == "__main__":
    raise SystemExit(main())
