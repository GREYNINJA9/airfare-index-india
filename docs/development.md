# Development & Architecture Guide

**System:** Real-time Airfare Price Index for India (APIx)  
**Problem Statement ID:** 26056 (SIH 2026)

---

## 1. Directory & File Structure

```
airfare-index-india/
├── README.md                     # Problem statement & challenge overview
├── compose.yaml                  # Root Docker Compose (PostgreSQL + API service)
├── config -> backend/config      # Compatibility symlink for root test runners
├── backend/
│   ├── pyproject.toml            # Python packaging & test configuration
│   ├── Dockerfile                # Production container spec with Patchright Chromium
│   ├── config/                   # System configurations
│   │   ├── routes.yaml           # Representative city-pair basket
│   │   ├── sources.yaml          # Registered scrapers (5 Airlines + 5 OTAs)
│   │   ├── settings.yaml         # Advance windows, frequencies & thresholds
│   │   └── loader.py             # Config validation & loader contract
│   ├── database/                 # Persistence layer
│   │   ├── schema.py             # PostgreSQL DDL for fares & index_results
│   │   ├── connection.py         # Connector singleton & lifecycle
│   │   ├── postgres.py           # Psycopg2 wrapper & connection adapter
│   │   ├── repository.py         # Type-safe persistence & querying helpers
│   │   └── seed_data.py          # 35+ days realistic data seeder
│   ├── models/                   # Pydantic v2 data contracts
│   │   ├── route.py              # Route (IATA origin != destination)
│   │   ├── fare.py               # Fare, RawFareSource, Enums
│   │   ├── index.py              # IndexResult, ItemIndex, ItemKey
│   │   ├── elasticity.py         # Lead-time elasticity & dynamic pricing models
│   │   └── dgca.py               # DGCA benchmarks & backtesting contracts
│   ├── index_engine/             # Econometric calculation engine
│   │   ├── aggregation.py        # Daily median prices & price relative calculation
│   │   ├── weights.py            # PSD Passenger Traffic & Uniform weighting
│   │   ├── api_index.py          # Laspeyres & weighted Jevons computation
│   │   ├── elasticity.py         # Econometric lead-time curve fitting (T+1..T+45)
│   │   └── backtesting.py        # 30+ day DGCA benchmark validation engine
│   ├── scraper/                  # Extraction engine
│   │   ├── base.py               # Scraper protocol, error handling
│   │   ├── airlines/             # IndiGo, Air India, AI Express, Akasa, SpiceJet
│   │   └── otas/                 # MakeMyTrip, ClearTrip, EaseMyTrip, Ixigo, Yatra
│   ├── pipeline/                 # Data cleaning & normalization
│   │   ├── validator.py          # Batch validation & structural checks
│   │   ├── cleaner.py            # Missing field & outlier sanitization
│   │   ├── normalizer.py         # Format mapping & currency standardization
│   │   └── deduplicator.py       # Exact & business key deduplication
│   ├── data/                     # Datasets
│   │   ├── sample/               # Synthetic sample fares for unit tests
│   │   └── dgca/                 # Official DGCA monthly tariff benchmark statistics
│   ├── api/                      # FastAPI application
│   │   ├── main.py               # App entrypoint, CORS, lifecycle
│   │   ├── routes.py             # Core /fares and /index endpoints
│   │   ├── fares.py              # Fares search, summary & sector metrics
│   │   ├── analytics.py          # Heatmaps, elasticity, airline comparison, RBI/NSO feed
│   │   └── dashboard/            # Interactive Web Dashboard UI
│   │       ├── app.py            # Dashboard view controller & endpoints
│   │       ├── charts.py         # Chart.js / ApexCharts serialization
│   │       ├── components.py     # Executive KPI scorecards
│   │       └── heatmap.py        # Sector matrix formatting
│   ├── docs/                     # Technical documentation
│   └── tests/                    # 298 automated tests (100% passing)
```

---

## 2. Quickstart Setup

### 2.1 Local Environment
```bash
# 1. Create and activate virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Install dependencies in editable mode
pip install -e ./backend[dev]

# 3. Install browser binaries for Patchright / Playwright
patchright install chromium

# 4. Start PostgreSQL database (via Podman or Docker)
podman run -d --name airfare-postgres -p 5432:5432 \
  -e POSTGRES_DB=airfare_index \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  postgres:16-alpine

# 5. Populate database with 35+ days of verified flight observations & APIx index
python backend/database/seed_data.py

# 6. Run the full automated test suite (298 tests)
PYTHONPATH=. pytest backend/tests

# 7. Start the FastAPI server & Interactive Dashboard
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2.2 Accessing the Platform
- **Interactive Web Dashboard:** `http://localhost:8000/dashboard` or `http://localhost:8000/`
- **Interactive OpenAPI / Swagger Documentation:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/health`
- **NSO & RBI Data Feed:** `http://localhost:8000/api/analytics/rbi-nso-feed?format=csv`
