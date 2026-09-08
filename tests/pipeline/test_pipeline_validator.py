"""Deterministic unit tests for pipeline.validator.

The validator enforces cross-record policies (duplicate keys, batch
integrity). No network.
"""

from pipeline.validator import validate_batch


def _raw_fare(offer_id="IG-DEL-BOM"):
    return {
        "route": {"origin": "DEL", "destination": "BOM"},
        "airline_code": "6E",
        "price_inr": 5000.0,
        "cabin_class": "ECONOMY",
        "departure_at": "2026-09-15T06:00:00+00:00",
        "scraped_at": "2026-08-27T10:00:00+00:00",
        "trip_type": "ONE_WAY",
        "source": {
            "source_name": "IndiGo",
            "source_type": "AIRLINE",
            "raw_price": 5000.0,
            "raw_currency": "INR",
            "raw_cabin_label": "Economy",
            "raw_offer_id": offer_id,
        },
    }


def test_validate_batch_accepts_clean_batch():
    records = [_raw_fare("A"), _raw_fare("B"), _raw_fare("C")]
    assert validate_batch(records) is None


def test_validate_batch_rejects_empty_batch():
    err = validate_batch([])
    assert err is not None
    assert "Empty batch" in str(err)


def test_validate_batch_rejects_duplicate_offer_id():
    records = [_raw_fare("SAME"), _raw_fare("SAME")]
    err = validate_batch(records)
    assert err is not None
    assert err.offending_keys == [("IndiGo", "SAME")]


def test_validate_batch_allows_different_offer_ids_same_source():
    records = [
        _raw_fare("A"),
        _raw_fare("B"),
        _raw_fare("C"),
    ]
    assert validate_batch(records) is None


def test_validate_batch_offers_no_offer_id_is_not_duplicated():
    """Records without an offer_id are not treated as duplicates."""
    records = [_raw_fare(None), _raw_fare(None)]
    assert validate_batch(records) is None


def test_validate_batch_does_not_validate_schema():
    """The validator does not check fare schema — that belongs to the model.

    A record missing required fields still passes the batch validator.
    """
    bad = {
        "airline_code": "6E",
        "source": {"source_name": "X"},
    }
    assert validate_batch([bad]) is None
