"""Deterministic unit tests for pipeline.cleaner.

The cleaner performs safe coercions before normalization. No network.
"""

from pipeline.cleaner import clean


def _raw_fare(**overrides):
    base = {
        "route": {"origin": " del ", "destination": " bom "},
        "airline_code": " 6e ",
        "price_inr": 5000.0,
        "cabin_class": "ECONOMY",
        "departure_at": "2026-09-15T06:00:00+00:00",
        "scraped_at": "2026-08-27T10:00:00+00:00",
        "trip_type": "ONE_WAY",
        "source": {
            "source_name": " IndiGo ",
            "source_type": " AIRLINE ",
            "raw_price": 5000.0,
            "raw_currency": "inr",
            "raw_cabin_label": " Economy Saver ",
            "raw_offer_id": "IG-DEL-BOM",
        },
    }
    base.update(overrides)
    return base


def test_clean_strips_whitespace_from_strings():
    cleaned, bad = clean([_raw_fare()])
    assert not bad
    assert cleaned[0]["airline_code"] == "6E"
    assert cleaned[0]["source"]["source_name"] == "IndiGo"
    assert cleaned[0]["source"]["raw_cabin_label"] == "Economy Saver"


def test_clean_uppercases_known_code_fields():
    """IATA, enum and currency fields are uppercased by the cleaner."""
    cleaned, _ = clean([_raw_fare()])
    assert cleaned[0]["route"]["origin"] == "DEL"
    assert cleaned[0]["route"]["destination"] == "BOM"
    assert cleaned[0]["cabin_class"] == "ECONOMY"
    assert cleaned[0]["trip_type"] == "ONE_WAY"
    assert cleaned[0]["source"]["source_type"] == "AIRLINE"
    assert cleaned[0]["source"]["raw_currency"] == "INR"


def test_clean_does_not_alter_unknown_fields():
    """Unknown keys are preserved verbatim (not uppercased or dropped)."""
    record = _raw_fare()
    record["unknown_field"] = "  hello  "
    cleaned, _ = clean([record])
    # Unknown string fields are still stripped of surrounding whitespace,
    # but they are NOT uppercased (only known code paths are).
    assert cleaned[0]["unknown_field"] == "hello"


def test_clean_rejects_non_dict_records():
    cleaned, bad = clean(["not a dict", 42, None, _raw_fare()])
    assert len(cleaned) == 1
    assert len(bad) == 3
    assert all("record" in b and "error" in b for b in bad)


def test_clean_handles_empty_batch():
    cleaned, bad = clean([])
    assert cleaned == []
    assert bad == []


def test_clean_does_not_mutate_input():
    """The cleaner returns a deep copy, leaving input untouched."""
    record = _raw_fare()
    original = record["airline_code"]
    cleaned, _ = clean([record])
    assert record["airline_code"] == original
    assert cleaned[0]["airline_code"] == "6E"
