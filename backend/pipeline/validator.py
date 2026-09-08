"""Batch-level validation for raw fare records.

This module enforces *cross-record* policies that cannot be expressed
as single-record Pydantic validators. It does NOT re-validate schema
fields (those are already enforced by RawFareSource / Fare during
normalization).

Rules implemented here are intentionally conservative and prototype-scope:
- Duplicate-key detection within a single batch.
- Batch rejection if zero valid records remain after cleaning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class BatchValidationError(ValueError):
    """Raised when a batch fails a cross-record policy."""

    def __init__(self, message: str, offending_keys: list[tuple] | None = None):
        super().__init__(message)
        self.offending_keys = offending_keys or []


def validate_batch(raw_records: list[dict]) -> BatchValidationError | None:
    """Validate a batch of raw records before normalization.

    Checks:
      1. Batch is not empty.
      2. No duplicate (source_name, raw_offer_id) pairs within the batch
         — this catches a scraper re-emitting the same offer in one run.

    Returns:
        ``None`` if the batch passes, or a ``BatchValidationError`` with
        the offending duplicate keys attached.
    """
    if not raw_records:
        return BatchValidationError("Empty batch: zero records to process")

    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []

    for record in raw_records:
        # The (source_name, raw_offer_id) pair uniquely identifies a raw
        # observation from a given source. If the same pair appears twice
        # in one batch, it's a duplicate emission. Records without an
        # offer_id are not considered duplicates — they are too ambiguous
        # to key on (this field is optional in the provenance contract).
        source = record.get("source", {}) if isinstance(record, dict) else {}
        source_name = source.get("source_name", "")
        raw_offer_id = source.get("raw_offer_id", "")
        if not raw_offer_id:
            continue
        key = (source_name, raw_offer_id)
        if key in seen:
            duplicates.append(key)
        else:
            seen.add(key)

    if duplicates:
        return BatchValidationError(
            f"Duplicate raw_offer_id within batch: {duplicates}",
            offending_keys=duplicates,
        )

    return None
