"""Pipeline package: cleaning, normalization, and deduplication.

This package transforms raw fare observations (from scrapers) into
validated, dedupd `models.fare.Fare` instances ready for storage
and indexing.

The entry point is :func:`process_raw_fares` — a pipeline function that
chains validator → cleaner → normalizer → deduplicator.

All modules are deliberately lightweight and stateless beyond in-memory
lists/dicts. Persistent state (e.g., which records have been seen) is
implemented in the database layer, not here.
"""

from models.fare import Fare
from pipeline.cleaner import CleanedBadFares, CleanedFares, clean
from pipeline.deduplicator import dedup
from pipeline.normalizer import FareNormalizationError, normalize
from pipeline.validator import BatchValidationError, validate_batch

__all__ = [
    "CleanedFares",
    "CleanedBadFares",
    "FareNormalizationError",
    "BatchValidationError",
    "clean",
    "dedup",
    "normalize",
    "process_raw_fares",
]


def process_raw_fares(
    raw_records: list[dict],
) -> tuple[list["Fare"], "CleanedBadFares", "BatchValidationError | None"]:
    """Run the full pipeline: validate → clean → normalize → dedup.

    Returns a tuple of (valid fares, bad records, batch validation error).
    Batch validation error is ``None`` unless the batch itself is rejected
    (e.g., zero valid records, or a batch-level business rule violation).
    """
    from models.fare import Fare

    errors = validate_batch(raw_records)
    if errors is not None:
        return [], [{"record": r, "error": str(errors)} for r in raw_records], errors

    cleaned, bad = clean(raw_records)
    normalized: list[Fare] = []
    for record in cleaned:
        try:
            fare = normalize(record)
            normalized.append(fare)
        except FareNormalizationError as e:
            bad.append({"record": record, "error": str(e)})

    return dedup(normalized), bad, None
