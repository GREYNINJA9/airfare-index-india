# Development Setup Guide

## Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/GREYNINJA9/airfare-index-india.git
   cd airfare-index-india

2. Create a Python virtual environment:
python3.11 -m venv .venv
source .venv/bin/activate
3. Install dependencies:
pip install -e .[dev]
playwright install chromium
4. Run Tests:
pytest -v
5. Start FastAPI Application:
uvicorn api.main:app --reload --port 8000
   Check status at http://localhost:8000/health.

Docker Usage

1. Build and start service via Compose:
docker compose up --build
2. Verify container health:
curl http://localhost:8000/health
