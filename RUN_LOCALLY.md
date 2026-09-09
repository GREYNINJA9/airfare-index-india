# 🚀 Running Real-time Airfare Price Index (APIx) Locally

This guide provides simple, foolproof steps to reset previous Docker containers and run the entire platform with **a single command**.

---

## ⚡ Option A: Single-Command Launch via Docker (Recommended)

### Step 0: Reset Previous Docker / Podman Changes
If you previously had old containers or postgres instances running that might block port `5432` or `8000`, run this cleanup command:

```bash
# Stop and remove existing Compose containers & volumes
docker compose down -v --remove-orphans 2>/dev/null || true

# If you used standalone Podman / Docker containers:
podman stop airfare-postgres airfare-api 2>/dev/null || docker stop airfare-postgres airfare-api 2>/dev/null || true
podman rm airfare-postgres airfare-api 2>/dev/null || docker rm airfare-postgres airfare-api 2>/dev/null || true
```

---

### Step 1: Run Everything with One Command
Execute this single command in the repository root:

```bash
docker compose up --build -d
```

#### What this single command does automatically:
1. Provisions a **PostgreSQL 16** container (`airfare-postgres`) with health checks.
2. Builds the **FastAPI + Patchright Chromium** container (`airfare-api`).
3. Automatically triggers **`AUTO_SEED=true`**:
   - Creates database schema (`fares` and `index_results` tables).
   - Generates and inserts **13,650 verified flight quotes** across 35+ days and 14 domestic sectors.
   - Computes 39 daily Laspeyres & Jevons APIx index series.
4. Starts the live web server on port **8000**.

---

### Step 2: Open and Verify
Once the command finishes, open your browser:

- **Executive Web Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard) or [http://localhost:8000/](http://localhost:8000/)
- **Interactive API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Container Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **NSO / RBI CSV Live Feed:** [http://localhost:8000/api/analytics/rbi-nso-feed?format=csv](http://localhost:8000/api/analytics/rbi-nso-feed?format=csv)

---

### 🛑 How to Stop or Reset
To stop the services:
```bash
docker compose down
```

To stop and completely wipe all stored database data:
```bash
docker compose down -v
```

---

## 🐍 Option B: Run Locally Without Docker (Python Virtual Environment)

If you prefer running directly on your host machine with an existing PostgreSQL database:

### 1. Prerequisites
- Python 3.10+
- PostgreSQL running on `localhost:5432` with database `airfare_index` (user `postgres`, password `postgres`).

### 2. Setup Virtual Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
patchright install chromium
```

### 3. Seed Database & Compute Indices
```bash
python database/seed_data.py
```

### 4. Run Automated Test Suite (298 Tests)
```bash
pytest tests
```

### 5. Launch Server
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```
Open [http://localhost:8000/dashboard](http://localhost:8000/dashboard) in your browser.
