"""Base protocol and utilities for all scrapers.

This module defines the contract that every scraper must implement. It does not
contain any scraping logic itself — that lives in individual scraper modules.

The scraper protocol:
- ``Scraper.extract(html: str) -> list[dict]`` — parse raw HTML and return a list of
  raw fare dictionaries matching the ``RawFareSource`` contract.
- ``Scraper.name: str`` — human-readable source name used in provenance.
- ``Scraper.source_type: SourceType`` — ``SourceType.OTA`` or ``SourceType.AIRLINE``.

All scrapers must be importable via ``scraper.<category>.<name>`` where ``<category>``
is ``"airlines"`` or ``"otas"``.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from models.fare import SourceType


@runtime_checkable
class Scraper(Protocol):
    """Protocol for all scrapers.

    The ``extract`` method receives raw HTML (or mock HTML in tests) and must
    return a list of raw fare dictionaries that can be validated by
    ``models.fare.RawFareSource.model_validate``.
    """

    def __init__(self, *args, **kwargs):
        """Scrappers may accept configuration (URLs, selectors, etc.)."""
        pass

    @property
    def name(self) -> str:
        """Human-readable source name (e.g., "MakeMyTrip", "IndiGo")."""
        raise NotImplementedError

    @property
    def source_type(self) -> SourceType:
        """Where the data originates — ``SourceType.OTA`` or ``SourceType.AIRLINE``."""
        raise NotImplementedError

    def extract(self, html: str) -> List[dict]:
        """Parse raw HTML and return a list of raw fare dictionaries.

        The return value must be directly compatible with ``RawFareSource``
        validation — any dict passed to ``RawFareSource.model_validate`` should
        succeed (or fail with a clear Pydantic error).

        For prototype safety, scrapers should never surface a total extraction
        failure to callers as an exception. Malformed input or a page that yields
        no valid records should result in an empty list rather than a raised
        error.
        """
        raise NotImplementedError


class ScraperError(RuntimeError):
    """Base exception for scraper failures."""

    pass


class ExtractionError(ScraperError):
    """Internal signal that a scraper could not extract any valid fares.

    The public ``Scraper.extract`` contract treats this as a safe-failure case:
    callers should receive ``[]`` instead of seeing this exception escape.
    """

    def __init__(self, message: str, html_sample: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.html_sample = html_sample
