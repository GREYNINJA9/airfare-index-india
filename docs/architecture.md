# Airfare Price Index Architecture (SIH26056)

## System Overview & Data Pipeline

The objective of this system is to collect real-time airfare prices across Indian domestic routes and calculate a standardized, high-frequency Airfare Price Index to augment the Consumer Price Index (CPI).

### Domain Data Contract

The canonical fare observation contract lives in **`models/`** and is the
single source of truth as data flows through every stage:

```
scraper ──▶ (RawFareSource) ──▶ validation/cleaning/normalization
   ──▶ (Fare) ──▶ database ──▶ index_engine ──▶ API
```

- **`models.route.Route`** — origin/destination IATA pair (the spatial dimension).
- **`models.fare.Fare`** — the normalized business contract: route, airline,
  INR price, cabin class, departure/scrape time, trip type.
- **`models.fare.RawFareSource`** — raw provenance (source name/type, price,
  currency, cabin label, URL, offer ID) kept **separate** from normalized fields.

Scrapers produce raw provenance; the pipeline validates, cleans, normalizes,
and deduplicates; the index engine reads only the normalized `Fare`. See
`docs/data-dictionary.md` for the full field reference.

### Pipeline Stages

1. **Scraper (`scraper/`)**
   - Playwright-based automated scrapers.
   - Extracts flight route, date, fare classes, airline, and timestamps.
2. **Raw Data (`data/raw/`)**
   - Immutable landing area for raw JSON/CSV records.
3. **Cleaning & Validation (`pipeline/`)**
   - Deduplication (`deduplicator.py`), outlier detection, missing field validation (`validator.py`, `cleaner.py`).
4. **Normalization (`pipeline/normalizer.py`)**
   - Route code standardization (IATA/ICAO), fare structure mapping.
5. **Storage (`data/processed/` / `database/`)**
   - Structured time-series database (`schema.py`, `repository.py`).
6. **Airfare Index Calculation (`index_engine/`)**
   - Laspeyres / Jevons index aggregation logic (`aggregation.py`, `weights.py`).
7. **Statistics & Backtesting**
   - Seasonality adjustments, trend analysis, volatility modeling.
8. **API (`api/`)**
   - FastAPI endpoints providing index feeds and route metrics.
9. **Dashboard (`dashboard/`)**
   - Real-time visual monitoring UI.
