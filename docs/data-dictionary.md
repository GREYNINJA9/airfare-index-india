# Airfare Data Dictionary (SIH26056)

Canonical reference for the domain data contract implemented in `models/`.
The contract is the single source of truth for a fare observation as it flows
**scraper → validation → cleaning → normalization → deduplication → database → index engine → API**.

All models use **Pydantic v2**. No scraping, pipeline, persistence, or index
logic lives in these models — they are pure data contracts.

---

## Route (`models/route.Route`)

An origin/destination pair of IATA airport codes for an Indian domestic flight.
The spatial dimension of a fare observation.

| Field          | Type            | Required | Validation                                                        | Meaning                                        |
| -------------- | --------------- | :------: | ----------------------------------------------------------------- | ---------------------------------------------- |
| `origin`       | `str`           | yes      | IATA format `^[A-Z]{3}$`, uppercased and whitespace-stripped      | Departure airport IATA code, e.g. `"DEL"`       |
| `destination`  | `str`           | yes      | IATA format `^[A-Z]{3}$`, uppercased and whitespace-stripped      | Arrival airport IATA code, e.g. `"BOM"`         |
| `distance_km`  | `float \| None` | no       | `>= 0.0` when present                                             | Great-circle distance in kilometres (optional) |

Model-level rules:

- `origin` and `destination` **must differ** (checked after case/whitespace normalization).
- Instances are **immutable** (`frozen=True`): once built, a route cannot be edited.
- Unknown fields are rejected (`extra="forbid"`).
- Trip type is **not** part of a route — it is a property of the fare observation (see `Fare.trip_type`).

---

## Enums

### CabinClass (`models/fare.CabinClass`)
`str`-backed enum. Canonical cabin classes:

| Value              | Meaning                       |
| ------------------ | ----------------------------- |
| `ECONOMY`          | Economy class                |
| `PREMIUM_ECONOMY`  | Premium economy class        |
| `BUSINESS`         | Business class               |
| `FIRST`            | First class                  |

### SourceType (`models/fare.SourceType`)
Where the observation was captured:

| Value     | Meaning                        |
| --------- | ------------------------------ |
| `AIRLINE` | Collected from an airline site |
| `OTA`     | Collected from an OTA          |

### TripType (`models/fare.TripType`)

| Value       | Meaning                                   |
| ----------- | ----------------------------------------- |
| `ONE_WAY`   | One-way fare                              |
| `ROUND_TRIP`| Round-trip fare                           |

---

## RawFareSource (`models/fare.RawFareSource`)

**Raw provenance** — the observation *exactly as captured* from the source,
before any normalization. These fields exist for traceability, audit, and
re-normalization. They are **never** used as business fields by the index engine.

| Field             | Type            | Required | Validation                                          | Meaning                                                     |
| ----------------- | --------------- | :------: | --------------------------------------------------- | ----------------------------------------------------------- |
| `source_name`     | `str`           | yes      | `1 <= len <= 120`, non-empty                         | Source display name, e.g. `"MakeMyTrip"`, `"IndiGo"`        |
| `source_type`     | `SourceType`    | yes      | enum                                                | `AIRLINE` or `OTA`                                          |
| `raw_price`       | `float`         | yes      | `> 0.0`                                             | Price as captured, in `raw_currency`                        |
| `raw_currency`    | `str`           | yes      | ISO-4217 `^[A-Z]{3}$`, uppercased                   | Currency as captured, e.g. `"INR"`                          |
| `raw_cabin_label` | `str`           | yes      | `1 <= len <= 120`, non-empty                         | Cabin/fare label verbatim, e.g. `"Economy Saver"`           |
| `source_url`      | `HttpUrl \| None` | no    | valid HTTP(S) URL when present                       | Page URL where the fare was observed                        |
| `raw_offer_id`    | `str \| None`   | no       | `len <= 200` when present                            | Source-specific offer/booking identifier, verbatim          |

---

## Fare (`models/fare.Fare`)

The canonical **normalized** fare observation — the central contract consumed
by cleaning, normalization, deduplication, the index engine, and the API.

### Normalized business fields (top level)

| Field           | Type            | Required | Validation                                    | Meaning                                          |
| --------------- | --------------- | :------: | --------------------------------------------- | ------------------------------------------------ |
| `route`         | `Route`         | yes      | Route contract (origin ≠ destination)         | Origin/destination IATA pair                     |
| `airline_code`  | `str`           | yes      | `^[A-Z0-9]{2}$`, uppercased                   | IATA carrier code, e.g. `"6E"`, `"I5"`, `"SG"`   |
| `price_inr`     | `float`         | yes      | `> 0.0`                                       | Normalized fare price in INR                     |
| `cabin_class`   | `CabinClass`    | yes      | enum                                          | Canonical cabin class                            |
| `departure_at`  | `datetime`      | yes      | **timezone-aware** (naive rejected)           | Scheduled departure time                         |
| `scraped_at`    | `datetime`      | yes      | **timezone-aware** (naive rejected)           | Time the observation was captured                |
| `trip_type`     | `TripType`      | yes      | enum                                          | One-way or round-trip                            |

### Provenance field

| Field    | Type             | Required | Validation | Meaning                                                         |
| -------- | ---------------- | :------: | ---------- | --------------------------------------------------------------- |
| `source` | `RawFareSource`  | yes      | as above   | Raw provenance, kept separate from normalized business fields   |

### Important semantic rules

- **Prices are strictly positive** (`price_inr > 0`, `raw_price > 0`).
- **Airline codes are generic two-character uppercase alphanumeric** IATA-style
  codes (`^[A-Z0-9]{2}$`). Digits are allowed (`6E`, `I5`, `SG`). The model does
  **not** hardcode any particular airline.
- **Datetimes must be timezone-aware.** Naive datetimes are rejected to avoid
  ambiguous local-time interpretation.
- **No cross-field ordering is enforced between `scraped_at` and `departure_at`.**
  Both orderings are legitimate:
  1. `scraped_at < departure_at` — the normal case for advance airfare collection
     (e.g. collected Aug 27 for a departure Sep 15).
  2. `scraped_at > departure_at` — a historical / post-departure observation.
  A "not in the future" rule is deliberately **not** implemented because it
  would require a wall clock and introduce nondeterminism.

### Raw vs normalized distinction

```
RawFareSource (as captured)          Fare (normalized, business-ready)
----------------------------         ----------------------------------
source_name / source_type            route / airline_code / trip_type
raw_price / raw_currency             price_inr      (INR)
raw_cabin_label                      cabin_class    (canonical enum)
source_url / raw_offer_id            departure_at / scraped_at (tz-aware)
```

Raw fields are preserved verbatim for audit; the index engine reads only the
normalized business fields.

---

## Constants

| Constant          | Value   | Meaning                                    |
| ----------------- | ------- | ------------------------------------------ |
| `INDIAN_CURRENCY` | `"INR"` | Canonical business currency for the index  |

---

## Synthetic data

`data/sample/synthetic_fares.json` contains deterministic, **hand-authored
synthetic** fare observations for development and testing only. It is clearly
labeled non-real (`_meta.is_real_data == false`) and **must not** be presented
as real scraped data. Every record validates against `models.fare.Fare`.
