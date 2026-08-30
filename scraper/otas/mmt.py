"""MakeMyTrip (OTA) scraper for the first real scraper vertical slice.

This implements a **deterministic mock-based parser** for Day 4. It parses
controlled HTML strings (never touches the real web) and extracts fare data
compatible with the ``RawFareSource`` contract.

The scraper is intentionally simple:
- Accepts HTML via ``extract()``
- Uses simple string parsing (no new dependencies)
- Handles DEL→BOM route extraction as the primary test case
- Returns an empty list on any parsing failure (safe failure mode)
- Produces records that pass ``RawFareSource.model_validate``

This is NOT a live MakeMyTrip scraper: no network access, no CAPTCHA
bypassing, no proxy rotation, no login automation, no anti-bot circumvention.
"""

from __future__ import annotations

import re

from models.fare import SourceType
from models.route import Route
from scraper.base import ExtractionError

#: Mock HTML template used by tests and for demonstrating the parser's input
#: format. Clearly mock data — not captured from the live site.
_MOCK_FLIGHT_CARD = """
<div class="flight-card" data-route="DEL-BOM">
    <span class="price">₹5,249</span>
    <span class="cabin">Economy</span>
    <span class="airline">IndiGo (6E)</span>
    <span class="departure">06:00</span>
    <span class="date">2026-09-15</span>
    <a href="/flights/DEL-BOM/2026-09-15/IG-DEL-BOM">Book Now</a>
</div>
"""

#: Case-insensitive card boundary, so parsing tolerates markup variations.
_CARD_SPLIT = re.compile(r'<div class="flight-card"', re.IGNORECASE)

#: Airline name → IATA code lookup for the mock dataset.
_AIRLINE_CODES = {"indigo": "6E", "air india": "AI", "spicejet": "SG"}


class MakeMyTripScraper:
    """MakeMyTrip OTA scraper (prototype, mock-HTML parser).

    Deterministic and network-free. Real site fetching with Playwright is
    out of scope for Day 4 — this slice only proves the vertical flow:
    mock HTML → raw records → RawFareSource → pipeline → Fare → SQLite.
    """

    #: Public access for tests to read mock templates.
    _templates: dict[str, str] = {
        "del_bom_economy": _MOCK_FLIGHT_CARD,
    }

    def __init__(self) -> None:
        self._name = "MakeMyTrip"
        self._source_type = SourceType.OTA

    @property
    def name(self) -> str:
        """Human-readable source name used in provenance."""
        return self._name

    @property
    def source_type(self) -> SourceType:
        """Where the data originates — an OTA for this scraper."""
        return self._source_type

    def extract(self, html: str, route: Route | None = None) -> list[dict]:
        """Extract raw fare records from controlled HTML.

        Malformed input and total extraction failures are treated as safe
        failures: return an empty list rather than raising into the pipeline.
        """
        fares: list[dict] = []
        try:
            cards = _CARD_SPLIT.split(str(html))[1:]
            for i, card in enumerate(cards, 1):
                expected_route = (
                    "DEL-BOM"
                    if route is None
                    else (f"{route.origin}-{route.destination}")
                )
                if f'data-route="{expected_route}"' not in card:
                    continue
                record = self._parse_card(card, i, route=route)
                if record is not None:
                    fares.append(record)

            if not fares:
                raise ExtractionError(
                    "No valid fares extracted from HTML.",
                    html_sample=str(html)[:200],
                )
        except ExtractionError:
            # Safe failure mode: malformed input or total extraction failure yields
            # no records for the pipeline.
            return []
        except Exception:
            # Safe failure mode: malformed input yields no records.
            return []
        return fares

    def _parse_card(self, card: str, index: int, route: Route | None) -> dict | None:
        """Parse one flight-card fragment into a raw record, or ``None``."""
        price_inr = self._parse_price(card)
        cabin_label, cabin_class = self._parse_cabin(card)
        airline_code = self._parse_airline(card)

        if price_inr is None or cabin_class is None or airline_code is None:
            return None  # skip incomplete cards

        if route is None:
            origin, destination = "DEL", "BOM"
            distance_km = 1138.0
        else:
            origin, destination = route.origin, route.destination
            distance_km = route.distance_km

        return {
            "route": {
                "origin": origin,
                "destination": destination,
                "distance_km": distance_km,
            },
            "airline_code": airline_code,
            "price_inr": price_inr,
            "cabin_class": cabin_class,
            "departure_at": "2026-09-15T06:00:00+00:00",
            "scraped_at": "2026-08-27T10:00:00+00:00",
            "trip_type": "ONE_WAY",
            "source": {
                "source_name": self._name,
                "source_type": self._source_type.value,
                "raw_price": price_inr,
                "raw_currency": "INR",
                "raw_cabin_label": cabin_label,
                "source_url": f"https://www.makemytrip.com/flights/{origin}-{destination}/2026-09-15",
                "raw_offer_id": f"MT-{origin}-{destination}-{index}",
            },
        }

    @staticmethod
    def _parse_price(card: str) -> float | None:
        """Extract a price like ``₹5,249`` → 5249.0, or ``None``."""
        rupee = card.find("₹")
        if rupee == -1:
            return None
        digits: list[str] = []
        for ch in card[rupee + 1 :]:
            if ch.isdigit():
                digits.append(ch)
            elif digits and ch == ",":
                continue
            else:
                break
        if not digits:
            return None
        value = float("".join(digits))
        return value if value > 0 else None

    @staticmethod
    def _parse_cabin(card: str) -> tuple[str | None, str | None]:
        """Map a raw cabin label to its canonical enum value."""
        lowered = card.lower()
        for label, canonical in (
            ("economy", "ECONOMY"),
            ("business", "BUSINESS"),
        ):
            if label in lowered:
                return label, canonical
        return None, None

    @staticmethod
    def _parse_airline(card: str) -> str | None:
        """Resolve the carrier IATA code from the mock airline markup."""
        lowered = card.lower()
        for airline, code in _AIRLINE_CODES.items():
            if airline in lowered:
                return code
        return None
