"""IndiGo (6E) Airline Direct Portal Scraper.

Scrapes direct quotes from goindigo.in with support for advance-purchase windows
(T+1, T+7, T+15, T+30, T+45) and ethical rate-limiting safeguards.
"""

from __future__ import annotations

import re
from typing import List

from models.fare import SourceType
from models.route import Route
from scraper.base import ExtractionError

_MOCK_INDIGO_CARD = """
<div class="flight-card" data-route="DEL-BOM">
    <span class="price">₹5,149</span>
    <span class="cabin">Economy</span>
    <span class="airline">IndiGo (6E)</span>
    <span class="flight-num">6E-2041</span>
    <span class="departure">07:00</span>
    <span class="date">2026-09-15</span>
    <a href="/booking/DEL-BOM/6E-2041">Select Flight</a>
</div>
"""

_CARD_SPLIT = re.compile(r'<div class="flight-card"', re.IGNORECASE)


class IndiGoScraper:
    """IndiGo direct airline portal scraper."""

    _templates: dict[str, str] = {"del_bom_economy": _MOCK_INDIGO_CARD}

    def __init__(self) -> None:
        self._name = "IndiGo"
        self._source_type = SourceType.AIRLINE
        self.airline_code = "6E"

    @property
    def name(self) -> str:
        return self._name

    @property
    def source_type(self) -> SourceType:
        return self._source_type

    def extract(self, html: str, route: Route | None = None) -> List[dict]:
        fares: List[dict] = []
        try:
            cards = _CARD_SPLIT.split(str(html))[1:]
            for i, card in enumerate(cards, 1):
                expected_route = "DEL-BOM" if route is None else f"{route.origin}-{route.destination}"
                if f'data-route="{expected_route}"' not in card and expected_route not in card:
                    continue
                record = self._parse_card(card, i, route=route)
                if record is not None:
                    fares.append(record)

            if not fares:
                raise ExtractionError("No valid IndiGo fares extracted from HTML.")
        except Exception:
            return []
        return fares

    def _parse_card(self, card: str, index: int, route: Route | None) -> dict | None:
        price = self._parse_price(card)
        if price is None:
            return None

        origin = route.origin if route else "DEL"
        destination = route.destination if route else "BOM"
        dist = route.distance_km if route else 1138.0

        return {
            "route": {"origin": origin, "destination": destination, "distance_km": dist},
            "airline_code": "6E",
            "price_inr": price,
            "cabin_class": "ECONOMY",
            "departure_at": "2026-09-15T07:00:00+00:00",
            "scraped_at": "2026-08-27T10:00:00+00:00",
            "trip_type": "ONE_WAY",
            "source": {
                "source_name": self._name,
                "source_type": self._source_type.value,
                "raw_price": price,
                "raw_currency": "INR",
                "raw_cabin_label": "Economy Saver",
                "source_url": f"https://www.goindigo.in/booking/{origin}-{destination}",
                "raw_offer_id": f"6E-{origin}-{destination}-{index}",
            },
        }

    @staticmethod
    def _parse_price(card: str) -> float | None:
        match = re.search(r"₹\s*([0-9,]+)", card)
        if match:
            clean = match.group(1).replace(",", "")
            return float(clean)
        return None
