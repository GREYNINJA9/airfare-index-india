"""Cleartrip live acquisition adapter.

This adapter integrates the proven Cleartrip Playwright scraper and /flight/search/v2
response parser into the SIH 26056 acquisition pipeline.

Contract:
- Accepts a SearchJob contract (no hardcoded routes, dates, or passenger counts).
- Orchestrates Playwright Chromium sessions with realistic headers/locales (no
  hardcoded cookies/JWTs).
- Captures /flight/search/v2 JSON network response.
- Reuses the reference parser from cleartrip_ui.py to resolve cards, flights, fares,
  direct flights, connecting flight chains, overnight datetimes, terminals, and stops.
- Transforms parsed itineraries into common raw fare records matching RawFareSource.
- Detects security challenges (CAPTCHA, Turnstile, Access Denied, Security Check)
  and safely handles them without circumvention.
- Raw JSON file persistence is disabled by default (SAVE_RAW=false) and in-memory flow
  is the primary path: response → parser → pipeline → database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
    from patchright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = Exception  # type: ignore
    sync_playwright = None  # type: ignore

from cleartrip_ui import (
    build_results_url,
    classify_page,
    is_target_url,
    parse_v2_response,
    safe_json,
)
from models.fare import SourceType
from scheduler.search import SearchJob
from scraper.base import ScraperError

logger = logging.getLogger("cleartrip_live")

RAW_DIR = Path("data/raw/cleartrip")


class CleartripSecurityChallengeError(ScraperError):
    """Raised when a security challenge or access restriction is detected."""

    def __init__(self, challenge_type: str, page_url: str = "") -> None:
        super().__init__(
            f"Cleartrip security challenge detected: {challenge_type} at {page_url}"
        )
        self.challenge_type = challenge_type
        self.page_url = page_url


def _deterministic_offer_id(travel_option_id: str, fare_id: str, fare_idx: int) -> str:
    """Generate a unique, deterministic raw_offer_id guaranteed <= 200 chars."""
    raw_key = f"{travel_option_id}-{fare_id}"
    if len(raw_key) <= 150:
        return f"CT-{raw_key}"
    h = hashlib.sha256(fare_id.encode("utf-8")).hexdigest()[:16]
    clean_prefix = travel_option_id[:120]
    return f"CT-{clean_prefix}-{fare_idx}-{h}"


def flight_to_raw_records(
    flight: Dict[str, Any],
    job: Optional[SearchJob] = None,
    scraped_at: Optional[datetime] = None,
    source_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convert a parsed Cleartrip flight record into common raw fare records.

    Preserves rich flight metadata (airline, flight number, departure, arrival,
    duration, stops, flight chain, aircraft, terminal) while ensuring strict
    compatibility with RawFareSource and the normalization pipeline.
    """
    if scraped_at is None:
        scraped_at = datetime.now(timezone.utc)
    scraped_at_iso = scraped_at.isoformat()

    origin = flight.get("route", {}).get("origin") or (job.origin if job else "")
    destination = flight.get("route", {}).get("destination") or (
        job.destination if job else ""
    )
    airline_code = flight.get("airline_code") or ""
    flight_number = flight.get("flight_number") or ""

    dep_info = flight.get("departure") or {}
    arr_info = flight.get("arrival") or {}
    departure_at = dep_info.get("datetime")

    if not departure_at:
        return []

    fares = flight.get("fares") or []
    if not fares and flight.get("cheapest_fare"):
        fares = [flight["cheapest_fare"]]

    travel_opt_id = (
        flight.get("travel_option_id")
        or f"{origin}-{destination}-{airline_code}-{flight_number}"
    )
    cabin_class = (job.cabin if job else "ECONOMY").upper()
    trip_type = (job.trip_type if job else "ONE_WAY").upper()

    records: List[Dict[str, Any]] = []

    for fare_idx, fare in enumerate(fares):
        total_price = fare.get("total_price")
        if total_price is None:
            continue
        try:
            price_val = float(total_price)
            if price_val <= 0:
                continue
        except (ValueError, TypeError):
            continue

        raw_currency = str(fare.get("currency") or "INR").strip().upper()
        raw_cabin_label = (
            fare.get("display_title")
            or fare.get("fare_family_subtype")
            or fare.get("fare_family_type")
            or "Economy"
        )
        fare_id = str(fare.get("fare_id") or fare_idx)
        raw_offer_id = _deterministic_offer_id(travel_opt_id, fare_id, fare_idx)

        flight_fare = fare.get("flight_fare") or []
        first_ff = (
            flight_fare[0] if flight_fare and isinstance(flight_fare[0], dict) else {}
        )

        record: Dict[str, Any] = {
            "route": {
                "origin": origin,
                "destination": destination,
                "distance_km": None,
            },
            "airline_code": airline_code,
            "price_inr": price_val,
            "cabin_class": cabin_class,
            "departure_at": departure_at,
            "scraped_at": scraped_at_iso,
            "trip_type": trip_type,
            "source": {
                "source_name": "ClearTrip",
                "source_type": SourceType.OTA.value,
                "raw_price": price_val,
                "raw_currency": raw_currency,
                "raw_cabin_label": raw_cabin_label,
                "source_url": source_url,
                "raw_offer_id": raw_offer_id,
            },
            # Preserved flight metadata
            "flight_number": flight_number,
            "arrival_at": arr_info.get("datetime"),
            "duration": flight.get("duration"),
            "stops": flight.get("stops", 0),
            "flight_chain": flight.get("flight_chain", []),
            "aircraft_type": flight.get("aircraft_type"),
            "equipment_code": flight.get("equipment_code"),
            "terminal_departure": dep_info.get("terminal"),
            "terminal_arrival": arr_info.get("terminal"),
            "base_fare": fare.get("base_fare"),
            "tax": fare.get("tax"),
            "fare_family": fare.get("fare_family_subtype")
            or fare.get("fare_family_type"),
            "fare_class": first_ff.get("fare_class"),
            "fare_basis_code": first_ff.get("fare_basis_code"),
            "rbd": first_ff.get("rbd"),
            "available_seats": first_ff.get("available_seat_count"),
            "check_in_baggage_allowed": fare.get("check_in_baggage_allowed"),
        }
        records.append(record)

    return records


class ClearTripLiveScraper:
    """Live Cleartrip scraper adapter using Playwright and /flight/search/v2."""

    def __init__(self) -> None:
        self._name = "ClearTrip"
        self._source_type = SourceType.OTA

    @property
    def name(self) -> str:
        """Human-readable source name used in provenance."""
        return self._name

    @property
    def source_type(self) -> SourceType:
        """Where the data originates — OTA."""
        return self._source_type

    def extract_v2(
        self,
        v2_payload: Dict[str, Any],
        job: Optional[SearchJob] = None,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[str] = None,
        scraped_at: Optional[datetime] = None,
        source_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Parse a /flight/search/v2 JSON payload into common raw fare records.

        Deterministic parser entrypoint for testing without hitting network.
        """
        req_origin = (job.origin if job else (origin or "")).strip().upper()
        req_dest = (job.destination if job else (destination or "")).strip().upper()
        req_date = job.cleartrip_date if job else (departure_date or "")

        if not isinstance(v2_payload, dict) or not req_origin or not req_dest:
            return []

        parsed = parse_v2_response(v2_payload, req_origin, req_dest, req_date)
        flights = parsed.get("flights") or []

        all_records: List[Dict[str, Any]] = []
        for flight in flights:
            records = flight_to_raw_records(
                flight=flight,
                job=job,
                scraped_at=scraped_at,
                source_url=source_url,
            )
            all_records.extend(records)

        return all_records

    def search(
        self,
        job: SearchJob,
        *,
        save_raw: Optional[bool] = None,
        wait_seconds: int = 60,
        headless: bool = True,
    ) -> List[Dict[str, Any]]:
        """Execute a live Cleartrip acquisition search via Playwright.

        Flow:
        1. Construct results URL from SearchJob parameters.
        2. Launch headless Chromium with realistic Indian locale/timezone.
        3. Listen to network responses and capture /flight/search/v2.
        4. Detect and classify security challenges if presented.
        5. Optionally save raw JSON for debugging if save_raw=True.
        6. Parse v2 payload directly in memory into common raw fare records.
        """
        if save_raw is None:
            save_raw = os.environ.get("SAVE_RAW", "false").lower() in (
                "1",
                "true",
                "yes",
            )

        results_url = build_results_url(
            origin=job.origin,
            destination=job.destination,
            depart_date=job.cleartrip_date,
            adults=job.adults,
            children=job.children,
            infants=job.infants,
        )

        captured: Dict[str, Any] = {}
        network_log: List[Dict[str, Any]] = []
        challenge: Optional[str] = None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        logger.info(
            "Starting Cleartrip search: %s->%s on %s (headless=%s)",
            job.origin,
            job.destination,
            job.cleartrip_date,
            headless,
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            def handle_response(response) -> None:
                nonlocal captured
                url = response.url
                if not is_target_url(url):
                    return

                item: Dict[str, Any] = {
                    "url": url,
                    "status": response.status,
                    "method": response.request.method,
                }
                try:
                    body = response.json()
                    item["json"] = safe_json(body)
                    if "/flight/search/v2" in url and response.status == 200:
                        captured["flight_search_v2"] = body
                    elif (
                        "/flights/v1/calendar/tab/fares" in url
                        and response.status == 200
                    ):
                        captured["calendar_fares"] = body
                    elif "/places/airports/search/v3" in url and response.status == 200:
                        captured["airports"] = body
                except Exception as exc:
                    item["json_error"] = str(exc)

                network_log.append(item)

            page.on("response", handle_response)

            try:
                page.goto(results_url, wait_until="domcontentloaded", timeout=60_000)
            except PlaywrightTimeoutError:
                # Flight API calls may continue after document navigation timeout.
                pass

            deadline = time.monotonic() + max(1, wait_seconds)
            while time.monotonic() < deadline:
                if "flight_search_v2" in captured:
                    if time.monotonic() + 3 < deadline:
                        page.wait_for_timeout(3000)
                    break
                page.wait_for_timeout(1000)

            page.wait_for_timeout(1000)

            try:
                page_text = page.locator("body").inner_text(timeout=5000)
                challenge = classify_page(page_text)
            except Exception:
                challenge = None

            current_url = page.url
            current_title = ""
            try:
                current_title = page.title()
            except Exception:
                pass

            browser.close()

        # Handle security challenges safely without bypass
        if challenge and "flight_search_v2" not in captured:
            logger.warning(
                (
                    "Cleartrip challenge detected (%s) for %s->%s; returning empty "
                    "records."
                ),
                challenge,
                job.origin,
                job.destination,
            )
            return []

        # Save raw JSON for debugging only if explicitly requested
        if save_raw:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            raw_path = RAW_DIR / f"cleartrip_raw_{stamp}.json"
            raw_payload = {
                "source": "cleartrip",
                "captured_at_utc": stamp,
                "request": {
                    "origin": job.origin,
                    "destination": job.destination,
                    "depart_date": job.cleartrip_date,
                    "adults": job.adults,
                    "children": job.children,
                    "infants": job.infants,
                    "results_url": results_url,
                },
                "page": {
                    "url": current_url,
                    "title": current_title,
                    "challenge": challenge,
                },
                "responses": captured,
                "target_network_log": network_log,
            }
            raw_path.write_text(
                json.dumps(raw_payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            logger.info("Raw debug payload saved to %s", raw_path)

        v2 = captured.get("flight_search_v2")
        if not v2 or not isinstance(v2, dict):
            logger.warning("No /flight/search/v2 response received from Cleartrip")
            return []

        return self.extract_v2(
            v2_payload=v2,
            job=job,
            source_url=results_url,
        )
