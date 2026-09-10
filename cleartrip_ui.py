#!/usr/bin/env python3
"""
Cleartrip UI/API capture adapter.

Purpose
-------
Use a real Chromium session to load Cleartrip, capture the JSON APIs that the
browser itself uses, and normalize the flight/fare data for the SIH pipeline.

Files generated
---------------
Only JSON files are written:
  raw/cleartrip_raw_<timestamp>.json
  normalized/cleartrip_flights_<timestamp>.json

No screenshots, HTML, or browser-evidence files are generated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

try:
    from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
    from patchright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = Exception  # type: ignore
    sync_playwright = None  # type: ignore

BASE_URL = "https://www.cleartrip.com"
RESULTS_URL = BASE_URL + "/flights/results"

RAW_DIR = Path("data/raw/cleartrip")
NORMALIZED_DIR = Path("data/normalized/cleartrip")

TARGET_ENDPOINTS = (
    "/flight/search/v2",
    "/flights/v1/calendar/tab/fares",
    "/places/airports/search/v3",
)

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?"
    r"(?:Z|[+-]\d{2}:\d{2})?$"
)
EPOCH_RE = re.compile(r"^\d{10,13}$")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_json(value: Any) -> Any:
    """Return a JSON-serializable copy, tolerating unusual browser payloads."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def normalize_iata(value: Any) -> str:
    return str(value or "").strip().upper()


def parse_user_date(value: str) -> str:
    """
    Accept DD/MM/YYYY or YYYY-MM-DD and return DD/MM/YYYY, which is what
    Cleartrip's observed results URL uses.
    """
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise ValueError("Date must be DD/MM/YYYY or YYYY-MM-DD")


def iso_from_epoch(value: Any) -> Optional[str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    # Cleartrip flight IDs commonly end in Unix seconds.
    if number >= 100_000_000_000:
        dt = datetime.fromtimestamp(number / 1000, tz=timezone.utc)
    elif number >= 1_000_000_000:
        dt = datetime.fromtimestamp(number, tz=timezone.utc)
    else:
        return None
    return dt.isoformat()


def extract_datetime(value: Any, preferred_keys: Iterable[str] = ()) -> Optional[str]:
    """
    Recursively find an ISO datetime or epoch timestamp.

    Cleartrip has used different representations in nested flight objects.
    We first inspect likely datetime keys, then recursively inspect the object.
    """
    if value is None:
        return None

    if isinstance(value, str):
        s = value.strip()
        if ISO_RE.match(s):
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt.isoformat()
            except ValueError:
                return s
        if EPOCH_RE.match(s):
            return iso_from_epoch(s)
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return iso_from_epoch(value)

    if isinstance(value, dict):
        priority = list(preferred_keys) + [
            "datetime",
            "dateTime",
            "date_time",
            "localDateTime",
            "scheduledDateTime",
            "scheduledTime",
            "departureDateTime",
            "arrivalDateTime",
            "departureTime",
            "arrivalTime",
            "time",
            "timestamp",
        ]

        seen = set()
        for key in priority:
            if key in seen or key not in value:
                continue
            seen.add(key)
            result = extract_datetime(value[key])
            if result:
                return result

        for child in value.values():
            result = extract_datetime(child)
            if result:
                return result
        return None

    if isinstance(value, list):
        for child in value:
            result = extract_datetime(child)
            if result:
                return result

    return None


def extract_timestamp_from_flight_id(flight_id: Any) -> Optional[str]:
    """Fallback only for departure: observed Cleartrip IDs end with epoch time."""
    match = re.search(r"-(\d{10,13})$", str(flight_id or ""))
    if not match:
        return None
    return iso_from_epoch(match.group(1))


def local_date_time(iso_value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not iso_value:
        return None, None

    try:
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        # If the source includes a timezone, convert to India time because this
        # project is indexing Indian flight schedules. If it is timezone-naive,
        # preserve its local clock representation.
        if dt.tzinfo is not None:
            from datetime import timezone as _timezone

            india = _timezone(timedelta(hours=5, minutes=30))
            dt = dt.astimezone(india)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")
    except ValueError:
        if len(iso_value) >= 16:
            return iso_value[:10], iso_value[11:16]
        return None, None


def duration_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        hh = value.get("hh", value.get("hours", value.get("hour")))
        mm = value.get("mm", value.get("minutes", value.get("minute")))
        if hh is not None or mm is not None:
            h = int(hh or 0)
            m = int(mm or 0)
            return f"{h}h {m}m"

    return None


def duration_minutes(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        try:
            return int(value.get("hh", value.get("hours", 0))) * 60 + int(
                value.get("mm", value.get("minutes", 0))
            )
        except (TypeError, ValueError):
            return None
    return None


def airport_code(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    for key in ("airportCode", "code", "iata", "airport"):
        value = obj.get(key)
        if isinstance(value, dict):
            value = value.get("code") or value.get("iata")
        if value:
            return normalize_iata(value)
    return None


def get_first_present(obj: Any, keys: Iterable[str]) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) is not None:
            return obj[key]
    return None


def extract_airline_code(flight: Dict[str, Any]) -> Optional[str]:
    return (
        normalize_iata(
            get_first_present(
                flight,
                (
                    "airlineCode",
                    "marketingAirlineCode",
                    "operatingAirlineCode",
                    "carrierCode",
                ),
            )
        )
        or None
    )


def extract_flight_number(flight: Dict[str, Any]) -> Optional[str]:
    value = get_first_present(flight, ("fltNo", "flightNumber", "flightNo", "number"))
    if value is None:
        return None
    return str(value).strip()


def flight_identity(flight: Dict[str, Any]) -> str:
    fid = flight.get("id") or flight.get("flightId")
    if fid:
        return str(fid)
    airline = extract_airline_code(flight) or ""
    number = extract_flight_number(flight) or ""
    dep = airport_code(flight.get("departure")) or ""
    arr = airport_code(flight.get("arrival")) or ""
    return f"{airline}-{number}-{dep}-{arr}"


def iter_nested_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_nested_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nested_dicts(child)


def collect_candidate_ids(value: Any, key_names: Iterable[str]) -> List[str]:
    wanted = {k.lower() for k in key_names}
    found: List[str] = []

    for obj in iter_nested_dicts(value):
        for key, child in obj.items():
            if key.lower() not in wanted:
                continue

            if isinstance(child, str):
                found.append(child)
            elif isinstance(child, list):
                found.extend(str(x) for x in child if isinstance(x, (str, int)))
            elif isinstance(child, dict):
                for k in ("id", "flightId", "key", "value"):
                    if child.get(k) is not None:
                        found.append(str(child[k]))

    return list(dict.fromkeys(found))


def resolve_flight_objects(
    card: Dict[str, Any],
    flights: Dict[str, Any],
    sub_travel_options: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Resolve the actual flight objects without assuming that
    subTravelOptionIds are flight IDs.

    Resolution order:
      1. IDs explicitly present as flight IDs in the card.
      2. IDs found inside referenced sub-travel-options.
      3. Card summary flight objects.
      4. Matching flight objects by route/number.
    """
    resolved: List[Dict[str, Any]] = []
    used = set()

    def add_flight(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        fid = str(obj.get("id") or obj.get("flightId") or flight_identity(obj))
        if fid in used:
            return
        used.add(fid)
        resolved.append(obj)

    # Cleartrip's observed payload has the authoritative mapping here:
    #
    # subTravelOptions[<id>].sequenceToFlightIdMap
    #
    # A travelOptionId can also contain multiple sub-options separated by
    # "__" for connecting itineraries. Resolve those IDs directly first.
    travel_option_id = card.get("travelOptionId")
    travel_option_parts = str(travel_option_id).split("__") if travel_option_id else []

    for fid in travel_option_parts:
        if fid in flights and isinstance(flights[fid], dict):
            add_flight(flights[fid])

    # Direct flight references in the card, if a future payload exposes them.
    direct_ids = collect_candidate_ids(
        card,
        ("flightId", "flightIds", "flightID", "flightIDs"),
    )
    for fid in direct_ids:
        if fid in flights and isinstance(flights[fid], dict):
            add_flight(flights[fid])

    # Follow sub-travel-option references.
    sub_ids = card.get("subTravelOptionIds") or card.get("subTravelOptionId") or []
    if isinstance(sub_ids, str):
        sub_ids = [sub_ids]

    for sid in sub_ids:
        # A connecting subTravelOptionId itself may contain the complete
        # "__"-separated sequence of flight IDs.
        for fid in str(sid).split("__"):
            if fid in flights and isinstance(flights[fid], dict):
                add_flight(flights[fid])

        option = sub_travel_options.get(str(sid))
        if not isinstance(option, dict):
            continue

        sequence_map = option.get("sequenceToFlightIdMap") or {}
        if isinstance(sequence_map, dict):
            for fid in sequence_map.values():
                if str(fid) in flights and isinstance(flights[str(fid)], dict):
                    add_flight(flights[str(fid)])

        nested_flight_ids = collect_candidate_ids(
            option,
            ("flightId", "flightIds", "flightID", "flightIDs"),
        )
        for fid in nested_flight_ids:
            if fid in flights and isinstance(flights[fid], dict):
                add_flight(flights[fid])

        # Some payloads may embed the flight objects themselves.
        for obj in iter_nested_dicts(option):
            if any(k in obj for k in ("fltNo", "flightNumber")) and (
                "departure" in obj and "arrival" in obj
            ):
                add_flight(obj)

    # Card summary can contain the actual flight objects.
    for key in ("flights", "flightDetails", "segments", "legs", "journey"):
        value = card.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    fid = item.get("id") or item.get("flightId")
                    if fid and str(fid) in flights:
                        add_flight(flights[str(fid)])
                    else:
                        add_flight(item)
        elif isinstance(value, dict):
            for item in value.values():
                if isinstance(item, dict):
                    fid = item.get("id") or item.get("flightId")
                    if fid and str(fid) in flights:
                        add_flight(flights[str(fid)])
                    else:
                        add_flight(item)

    # Last-resort matching against the flight index using card-level route.
    card_from = normalize_iata(
        get_first_present(card, ("from", "origin", "source", "originCode"))
    )
    card_to = normalize_iata(
        get_first_present(card, ("to", "destination", "dest", "destinationCode"))
    )

    if card_from or card_to:
        for obj in flights.values():
            if not isinstance(obj, dict):
                continue
            dep = airport_code(obj.get("departure"))
            arr = airport_code(obj.get("arrival"))
            if card_from and dep != card_from:
                continue
            if card_to and arr != card_to:
                continue
            add_flight(obj)

    return resolved


def parse_fare(fare_id: str, fare: Dict[str, Any]) -> Dict[str, Any]:
    pricing = fare.get("pricing") or {}
    total_pricing = pricing.get("totalPricing") or {}

    total = total_pricing.get("totalPrice")
    tax = total_pricing.get("totalTax")
    base = total_pricing.get("totalBaseFare")

    if total is None:
        adult = next(
            (p for p in fare.get("paxFare", []) if p.get("paxType") == "ADT"),
            None,
        )
        if isinstance(adult, dict):
            components = adult.get("priceComponents") or []
            base = (
                base
                if base is not None
                else sum(
                    float(x.get("amount", 0) or 0)
                    for x in components
                    if x.get("code") == "BF"
                )
            )
            tax = (
                tax
                if tax is not None
                else sum(
                    float(x.get("amount", 0) or 0)
                    for x in components
                    if x.get("code") == "TAX"
                )
            )
            total = (
                adult.get("totalFare")
                or adult.get("totalPrice")
                or ((base or 0) + (tax or 0))
            )

    identifiers = []
    for item in fare.get("flightFare", []) or []:
        if not isinstance(item, dict):
            continue
        identifiers.append(
            {
                "flight_id": item.get("flightId"),
                "cabin_type": item.get("cabinType"),
                "fare_class": item.get("fareClass"),
                "fare_basis_code": item.get("fareBasisCode"),
                "available_seat_count": item.get("availableSeatCount"),
                "brand_name": item.get("brandName"),
                "brand": item.get("brand"),
                "rbd": item.get("rbd"),
            }
        )

    coupon_details = fare.get("couponDetails") or []
    if isinstance(coupon_details, dict):
        coupon_details = [coupon_details]

    coupons = []
    for coupon in coupon_details:
        if not isinstance(coupon, dict):
            continue
        coupons.append(
            {
                "coupon_code": coupon.get("couponCode"),
                "discount_amount": coupon.get("discountAmount"),
                "discounted_price": coupon.get("discountedPrice"),
                "message": coupon.get("message"),
            }
        )

    return {
        "fare_id": fare_id,
        "display_title": (fare.get("displayText") or {}).get("displayTitle"),
        "display_subtitle": (fare.get("displayText") or {}).get("displaySubTitle"),
        "fare_group": fare.get("fareGroup"),
        "fare_category": fare.get("fareCategory"),
        "fare_family_type": fare.get("fareFamilyType"),
        "fare_family_subtype": fare.get("fareFamilySubType"),
        "brand": fare.get("brand"),
        "currency": "INR",
        "total_price": total,
        "base_fare": base,
        "tax": tax,
        "coupons": coupons,
        "benefit_tags": fare.get("benefitTags") or [],
        "benefits": fare.get("benefits") or [],
        "check_in_baggage_allowed": fare.get("checkInBaggageAllowed"),
        "flight_fare": identifiers,
    }


def resolve_fare_ids(
    card: Dict[str, Any],
    sub_travel_options: Dict[str, Any],
) -> List[str]:
    ids: List[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            ids.append(value)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            for key in ("fareId", "fareID", "id", "key"):
                if value.get(key) is not None:
                    add(value[key])

    add(card.get("fareIds"))
    add(card.get("fareId"))
    add(card.get("cheapestFareId"))

    sub_ids = card.get("subTravelOptionIds") or card.get("subTravelOptionId") or []
    if isinstance(sub_ids, str):
        sub_ids = [sub_ids]

    for sid in sub_ids:
        option = sub_travel_options.get(str(sid))
        if not isinstance(option, dict):
            continue
        for key in ("fareIds", "fareId", "cheapestFareId"):
            add(option.get(key))

    return list(dict.fromkeys(str(x) for x in ids))


def _extract_terminal(obj: Dict[str, Any]) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    term = obj.get("terminalName") or obj.get("terminal")
    if isinstance(term, dict):
        term = term.get("name")
    if not term and isinstance(obj.get("airport"), dict):
        apt = obj["airport"]
        term = apt.get("terminalName") or apt.get("terminal")
        if isinstance(term, dict):
            term = term.get("name")
    return str(term).strip() if term else None


def _extract_gate(obj: Dict[str, Any]) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    gate = obj.get("gate")
    if not gate and isinstance(obj.get("terminal"), dict):
        gate = obj["terminal"].get("gate")
    if not gate and isinstance(obj.get("airport"), dict):
        apt = obj["airport"]
        gate = apt.get("gate")
        if not gate and isinstance(apt.get("terminal"), dict):
            gate = apt["terminal"].get("gate")
    return str(gate).strip() if gate else None


def _extract_timezone(obj: Dict[str, Any]) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    tz = obj.get("timeZone") or obj.get("timezone") or obj.get("zoneId")
    if not tz and isinstance(obj.get("airport"), dict):
        apt = obj["airport"]
        tz = apt.get("zoneId") or apt.get("timeZone") or apt.get("timezone")
    return str(tz).strip() if tz else None


def parse_flight(
    flight: Dict[str, Any],
    requested_origin: str,
    requested_destination: str,
) -> Dict[str, Any]:
    fid = flight.get("id") or flight.get("flightId")
    departure = flight.get("departure") or {}
    arrival = flight.get("arrival") or {}

    dep_dt = extract_datetime(
        departure,
        ("departureDateTime", "scheduledDateTime", "departureTime", "time"),
    )
    if not dep_dt:
        dep_dt = extract_timestamp_from_flight_id(fid)

    arr_dt = extract_datetime(
        arrival,
        ("arrivalDateTime", "scheduledDateTime", "arrivalTime", "time"),
    )

    dep_code = airport_code(departure)
    arr_code = airport_code(arrival)
    dep_date, dep_time = local_date_time(dep_dt)
    arr_date, arr_time = local_date_time(arr_dt)

    return {
        "flight_id": fid,
        "airline_code": extract_airline_code(flight),
        "flight_number": extract_flight_number(flight),
        "origin": dep_code,
        "destination": arr_code,
        "departure": {
            "datetime": dep_dt,
            "date": dep_date,
            "time": dep_time,
            "airport": dep_code,
            "terminal": _extract_terminal(departure),
            "gate": _extract_gate(departure),
            "timezone": _extract_timezone(departure),
        },
        "arrival": {
            "datetime": arr_dt,
            "date": arr_date,
            "time": arr_time,
            "airport": arr_code,
            "terminal": _extract_terminal(arrival),
            "gate": _extract_gate(arrival),
            "timezone": _extract_timezone(arrival),
        },
        "duration": duration_text(flight.get("duration")),
        "equipment_code": flight.get("equipmentCode"),
        "aircraft_type": flight.get("aircraftType"),
        "stops": flight.get("stops") or [],
        "requested_route_match": (
            dep_code == requested_origin and arr_code == requested_destination
        ),
    }


def calculate_elapsed(first_dt: Optional[str], last_dt: Optional[str]) -> Optional[str]:
    if not first_dt or not last_dt:
        return None
    try:
        start = datetime.fromisoformat(first_dt.replace("Z", "+00:00"))
        end = datetime.fromisoformat(last_dt.replace("Z", "+00:00"))
        if start.tzinfo is None and end.tzinfo is not None:
            start = start.replace(tzinfo=end.tzinfo)
        if end.tzinfo is None and start.tzinfo is not None:
            end = end.replace(tzinfo=start.tzinfo)
        minutes = int((end - start).total_seconds() // 60)
        if minutes < 0:
            return None
        return f"{minutes // 60}h {minutes % 60}m"
    except (ValueError, TypeError):
        return None


def parse_v2_response(
    payload: Dict[str, Any],
    requested_origin: str,
    requested_destination: str,
    requested_date: str,
) -> Dict[str, Any]:
    """
    Convert Cleartrip V2 response into the SIH-normalized flight records.
    Only itineraries whose first airport is the requested origin and whose
    final airport is the requested destination are retained.
    """
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    cards_root = root.get("cards") or {}
    cards = cards_root.get("J1") if isinstance(cards_root, dict) else []
    if isinstance(cards, dict):
        cards = list(cards.values())
    if not isinstance(cards, list):
        cards = []

    flights = root.get("flights") or {}
    fares = root.get("fares") or {}
    sub_options = root.get("subTravelOptions") or {}

    if not isinstance(flights, dict):
        flights = {}
    if not isinstance(fares, dict):
        fares = {}
    if not isinstance(sub_options, dict):
        sub_options = {}

    normalized: List[Dict[str, Any]] = []

    for card in cards:
        if not isinstance(card, dict):
            continue

        flight_objects = resolve_flight_objects(card, flights, sub_options)

        # The summary is authoritative for the itinerary's first/last airport
        # and schedule, and is also a useful fallback when a flight object is
        # temporarily absent from the index.
        summary = card.get("summary") or {}
        summary_flights = summary.get("flights") or []
        if not isinstance(summary_flights, list):
            summary_flights = []

        chain = [
            parse_flight(f, requested_origin, requested_destination)
            for f in flight_objects
            if isinstance(f, dict)
        ]

        # If actual flight objects were resolved, use them. Otherwise construct
        # a minimal chain from the summary. We intentionally do not fabricate
        # arrival times from duration.
        if not chain and summary_flights:
            first_dep = summary.get("firstDeparture") or {}
            last_arr = summary.get("lastArrival") or {}

            first_airport = airport_code(first_dep.get("airport"))
            last_airport = airport_code(last_arr.get("airport"))
            first_time = extract_datetime(first_dep, ("time",))
            last_time = extract_datetime(last_arr, ("time",))

            for sf in summary_flights:
                if not isinstance(sf, dict):
                    continue
                chain.append(
                    {
                        "flight_id": None,
                        "airline_code": normalize_iata(sf.get("airlineCode")) or None,
                        "flight_number": str(
                            sf.get("flightNumber") or sf.get("fltNo") or ""
                        ).strip()
                        or None,
                        "origin": first_airport,
                        "destination": last_airport,
                        "departure": {
                            "datetime": first_time,
                            "date": local_date_time(first_time)[0],
                            "time": local_date_time(first_time)[1],
                            "airport": first_airport,
                            "terminal": (first_dep.get("airport") or {})
                            .get("terminal", {})
                            .get("name")
                            if isinstance(first_dep.get("airport"), dict)
                            else None,
                            "gate": (first_dep.get("airport") or {})
                            .get("terminal", {})
                            .get("gate")
                            if isinstance(first_dep.get("airport"), dict)
                            else None,
                            "timezone": (first_dep.get("airport") or {}).get("zoneId")
                            if isinstance(first_dep.get("airport"), dict)
                            else None,
                        },
                        "arrival": {
                            "datetime": last_time,
                            "date": local_date_time(last_time)[0],
                            "time": local_date_time(last_time)[1],
                            "airport": last_airport,
                            "terminal": (last_arr.get("airport") or {})
                            .get("terminal", {})
                            .get("name")
                            if isinstance(last_arr.get("airport"), dict)
                            else None,
                            "gate": (last_arr.get("airport") or {})
                            .get("terminal", {})
                            .get("gate")
                            if isinstance(last_arr.get("airport"), dict)
                            else None,
                            "timezone": (last_arr.get("airport") or {}).get("zoneId")
                            if isinstance(last_arr.get("airport"), dict)
                            else None,
                        },
                        "duration": duration_text(summary.get("totalDuration")),
                        "equipment_code": None,
                        "aircraft_type": None,
                        "stops": [],
                        "requested_route_match": (
                            first_airport == requested_origin
                            and last_airport == requested_destination
                        ),
                    }
                )
        chain = [x for x in chain if x.get("origin") or x.get("destination")]
        if not chain:
            continue

        first_origin = chain[0].get("origin")
        final_destination = chain[-1].get("destination")

        # Critical route filter: Cleartrip's payload can contain additional
        # itineraries, so never trust the page URL alone.
        if (
            first_origin != requested_origin
            or final_destination != requested_destination
        ):
            continue

        first_dep_dt = chain[0]["departure"]["datetime"]
        last_arr_dt = chain[-1]["arrival"]["datetime"]

        total_duration = duration_text(
            card.get("duration") or card.get("totalDuration")
        )
        if not total_duration:
            total_duration = calculate_elapsed(first_dep_dt, last_arr_dt)

        fare_ids = resolve_fare_ids(card, sub_options)
        parsed_fares = []
        for fare_id in fare_ids:
            fare = fares.get(str(fare_id))
            if isinstance(fare, dict):
                parsed_fares.append(parse_fare(str(fare_id), fare))

        parsed_fares.sort(
            key=lambda x: (
                float(x["total_price"])
                if isinstance(x.get("total_price"), (int, float))
                else float("inf")
            )
        )

        first = chain[0]
        last = chain[-1]

        record = {
            "source": "cleartrip",
            "airline_code": first.get("airline_code"),
            "flight_number": first.get("flight_number"),
            "route": {
                "origin": requested_origin,
                "destination": requested_destination,
            },
            "departure": first["departure"],
            "arrival": last["arrival"],
            "duration": total_duration,
            "stops": max(0, len(chain) - 1),
            "flight_chain": chain,
            "aircraft_type": first.get("aircraft_type"),
            "equipment_code": first.get("equipment_code"),
            "fares": parsed_fares,
            "cheapest_fare": parsed_fares[0] if parsed_fares else None,
            "card_id": card.get("id") or card.get("cardId"),
            "travel_option_id": card.get("travelOptionId"),
            "requested_departure_date": requested_date,
        }

        # Use a stable deduplication key. Do not dedupe different fare choices.
        dedupe_key = (
            record["airline_code"],
            record["flight_number"],
            first_dep_dt,
            requested_origin,
            requested_destination,
            tuple(x.get("flight_id") for x in chain),
        )
        record["_dedupe_key"] = dedupe_key
        normalized.append(record)

    unique: List[Dict[str, Any]] = []
    seen = set()
    for record in normalized:
        key = record.pop("_dedupe_key")
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)

    return {
        "source": "cleartrip",
        "route": {
            "origin": requested_origin,
            "destination": requested_destination,
        },
        "departure_date": requested_date,
        "flight_count": len(unique),
        "flights": unique,
    }


def classify_page(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    patterns = {
        "CAPTCHA": (
            "captcha",
            "recaptcha",
            "hcaptcha",
        ),
        "TURNSTILE": (
            "turnstile",
            "verify you are human",
        ),
        "ACCESS_DENIED": (
            "access denied",
            "request blocked",
            "forbidden",
        ),
        "SECURITY_CHECK": (
            "security check",
            "checking your browser",
            "unusual traffic",
        ),
    }
    for label, terms in patterns.items():
        if any(term in lowered for term in terms):
            return label
    return None


def build_results_url(
    origin: str,
    destination: str,
    depart_date: str,
    adults: int,
    children: int,
    infants: int,
) -> str:
    params = {
        "adults": adults,
        "childs": children,
        "infants": infants,
        "class": "Economy",
        "depart_date": depart_date,
        "from": origin,
        "to": destination,
        "intl": "n",
        "origin": f"{origin}",
        "destination": f"{destination}",
        "sft": "",
        "sd": "",
        "rnd_one": "O",
        "isCfw": "false",
        "nonStop": "",
        "isFF": "false",
    }
    return RESULTS_URL + "?" + urlencode(params)


def is_target_url(url: str) -> bool:
    return any(endpoint in url for endpoint in TARGET_ENDPOINTS)


def capture_cleartrip(
    origin: str,
    destination: str,
    depart_date: str,
    adults: int,
    children: int,
    infants: int,
    wait_seconds: int = 60,
    headless: bool = True,
) -> Tuple[Path, Path]:
    origin = normalize_iata(origin)
    destination = normalize_iata(destination)
    depart_date = parse_user_date(depart_date)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)

    stamp = utc_stamp()
    raw_path = RAW_DIR / f"cleartrip_raw_{stamp}.json"
    normalized_path = NORMALIZED_DIR / f"cleartrip_flights_{stamp}.json"

    results_url = build_results_url(
        origin, destination, depart_date, adults, children, infants
    )

    captured: Dict[str, Any] = {}
    network_log: List[Dict[str, Any]] = []
    challenge: Optional[str] = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1440, "height": 900},
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

                # Keep the response keyed by endpoint so parsing does not
                # depend on request ordering.
                if "/flight/search/v2" in url and response.status == 200:
                    captured["flight_search_v2"] = body
                elif "/flights/v1/calendar/tab/fares" in url and response.status == 200:
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
            # The page may continue making the flight API calls after the
            # document-level navigation timeout. Continue waiting for them.
            pass

        # Cleartrip can initialize its search APIs with a noticeable delay.
        deadline = time.monotonic() + max(1, wait_seconds)
        while time.monotonic() < deadline:
            if "flight_search_v2" in captured:
                # Give the page a little extra time for fares/secondary data.
                if time.monotonic() + 3 < deadline:
                    page.wait_for_timeout(3000)
                break
            page.wait_for_timeout(1000)

        # One final short wait lets late fare/network responses arrive.
        page.wait_for_timeout(1000)

        try:
            page_text = page.locator("body").inner_text(timeout=5000)
            challenge = classify_page(page_text)
        except Exception:
            page_text = ""

        raw_payload = {
            "source": "cleartrip",
            "captured_at_utc": stamp,
            "request": {
                "origin": origin,
                "destination": destination,
                "depart_date": depart_date,
                "adults": adults,
                "children": children,
                "infants": infants,
                "results_url": results_url,
            },
            "page": {
                "url": page.url,
                "title": page.title(),
                "challenge": challenge,
            },
            "responses": {
                "flight_search_v2": captured.get("flight_search_v2"),
                "calendar_fares": captured.get("calendar_fares"),
                "airports": captured.get("airports"),
            },
            "target_network_log": network_log,
        }

        raw_path.write_text(
            json.dumps(raw_payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        if challenge and "flight_search_v2" not in captured:
            normalized_payload = {
                "source": "cleartrip",
                "route": {"origin": origin, "destination": destination},
                "departure_date": depart_date,
                "status": "blocked_or_challenged",
                "challenge": challenge,
                "flight_count": 0,
                "flights": [],
            }
        elif "flight_search_v2" not in captured:
            normalized_payload = {
                "source": "cleartrip",
                "route": {"origin": origin, "destination": destination},
                "departure_date": depart_date,
                "status": "no_v2_response",
                "flight_count": 0,
                "flights": [],
            }
        else:
            normalized_payload = parse_v2_response(
                captured["flight_search_v2"],
                origin,
                destination,
                depart_date,
            )
            normalized_payload["status"] = (
                "success_with_challenge" if challenge else "success"
            )
            if challenge:
                normalized_payload["challenge"] = challenge

        normalized_payload["captured_at_utc"] = stamp

        normalized_path.write_text(
            json.dumps(
                normalized_payload,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

        browser.close()

    print(f"Raw JSON:        {raw_path}")
    print(f"Normalized JSON: {normalized_path}")

    return raw_path, normalized_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and normalize Cleartrip flight data using Playwright."
    )
    parser.add_argument("--from", dest="origin", required=True, help="Origin IATA code")
    parser.add_argument(
        "--to", dest="destination", required=True, help="Destination IATA code"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Departure date: DD/MM/YYYY or YYYY-MM-DD",
    )
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--infants", type=int, default=0)
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=60,
        help="Maximum time to wait for the V2 search response",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium instead of running headless",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Immediately ingest normalized output through the pipeline into PostgreSQL and update dashboard",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    try:
        _raw_path, normalized_path = capture_cleartrip(
            origin=args.origin,
            destination=args.destination,
            depart_date=args.date,
            adults=args.adults,
            children=args.children,
            infants=args.infants,
            wait_seconds=args.wait_seconds,
            headless=not args.headed,
        )

        if getattr(args, "ingest", False):
            print("\n--- Ingesting into Pipeline & Database ---")
            from pipeline.ingest import ingest_normalized_file
            res = ingest_normalized_file(normalized_path)
            print(
                f"✓ Pipeline ingested {res.get('valid_fares', 0)} valid fares into database "
                f"({res.get('new_fares_inserted', 0)} new rows)."
            )

        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Cleartrip capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
