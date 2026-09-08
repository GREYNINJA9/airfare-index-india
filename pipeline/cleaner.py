"""Lightweight cleaning helpers for raw fare records.

The cleaner performs safe, deterministic coercions before normalization:
- reject non-dict records,
- recursively strip surrounding whitespace from string values,
- uppercase IATA/currency/code fields where those fields are known.

It deliberately does not enforce the Fare schema. Pydantic validation remains
owned by models.fare and models.route during normalization.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TypeAlias

CleanedFares: TypeAlias = list[dict[str, Any]]
CleanedBadFares: TypeAlias = list[dict[str, Any]]

_UPPERCASE_PATHS = {
    ("airline_code",),
    ("cabin_class",),
    ("trip_type",),
    ("route", "origin"),
    ("route", "destination"),
    ("source", "source_type"),
    ("source", "raw_currency"),
}


def clean(raw_records: list[dict[str, Any]]) -> tuple[CleanedFares, CleanedBadFares]:
    """Clean a batch of raw fare dictionaries.

    Returns a tuple of ``(cleaned_records, bad_records)``. Bad records are
    represented as ``{"record": original, "error": message}`` so callers can
    log or inspect them later.
    """
    cleaned: CleanedFares = []
    bad: CleanedBadFares = []

    for record in raw_records:
        if not isinstance(record, dict):
            bad.append({"record": record, "error": "record must be a dictionary"})
            continue
        cleaned.append(_clean_mapping(record))

    return cleaned, bad


def _clean_mapping(record: dict[str, Any]) -> dict[str, Any]:
    copy = deepcopy(record)
    return _clean_value(copy, ())


def _clean_value(value: Any, path: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {k: _clean_value(v, (*path, str(k))) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_value(v, path) for v in value]
    if isinstance(value, str):
        stripped = value.strip()
        if path in _UPPERCASE_PATHS:
            return stripped.upper()
        return stripped
    return value
