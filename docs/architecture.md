# Airfare Price Index Architecture (SIH26056)

## System Overview & Data Pipeline

The objective of this system is to collect real-time airfare prices across Indian domestic routes and calculate a standardized, high-frequency Airfare Price Index to augment the Consumer Price Index (CPI).

### Pipeline Stages

1. **Scraper (`scraper/`)**
   - Playwright-based automated scrapers.
   - Extracts flight route, date, fare classes, airline, and timestamps.
2. **Raw Data (`data/raw/`)**
   - Immutable landing area for raw JSON/CSV records.
3. **Cleaning & Validation (`cleaning/`)**
   - Deduplication, outlier detection, missing field validation.
4. **Normalization (`normalization/`)**
   - Route code standardization (IATA/ICAO), fare structure mapping.
5. **Storage (`data/processed/` / DB)**
   - Structured time-series database.
6. **Airfare Index Calculation (`index/`)**
   - Laspeyres / Jevons index aggregation logic.
7. **Statistics & Backtesting (`statistics/`)**
   - Seasonality adjustments, trend analysis, volatility modeling.
8. **API (`api/`)**
   - FastAPI endpoints providing index feeds and route metrics.
9. **Dashboard (`dashboard/`)**
   - Real-time visual monitoring UI.
