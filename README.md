# Nifty 100 Financial Intelligence Platform

End-to-end financial intelligence system for Nifty 100 companies with three parallel streams:

- Stream A: Power BI dashboards (analytics consumption)
- Stream B: Data engineering + ML scoring (data backbone)
- Stream C: Django web + partner API (distribution layer)

## Current repository status

This repository now includes a runnable foundation for Streams B and C, plus structure for Stream A integration.

### Stream B implemented

- ETL Script 1: `etl/01_extract_from_mysql.py`
  - Parses SQL dump `INSERT INTO` blocks for all 7 source tables
  - Handles escaped quotes and NULL tokens
  - Writes `data/raw/*.csv`

- ETL Script 2: `etl/02_clean_and_transform.py`
  - Standardizes inconsistent year formats
  - Cleans symbols/text/nulls
  - Builds/updates sector mapping file
  - Computes derived financial metrics
  - Writes `data/clean/*.csv` and `data/clean/dim_year.csv`

- ETL Script 3: `etl/03_load_to_warehouse.py`
  - Creates star schema in PostgreSQL
  - Loads dimensions first, then fact tables
  - Uses idempotent upsert (`ON CONFLICT DO UPDATE`)
  - Runs 8 post-load data quality checks and fails transaction on violations

- ETL Script 4: `etl/04_schedule_refresh.py`
  - Manual refresh mode
  - Celery enqueue mode
  - Worker/beat process launcher mode

- ML scoring engine: `analytics/health_scoring.py`
  - Computes weighted score (0-100) from profitability, growth, leverage, cash flow, dividend, trend
  - Assigns health labels: EXCELLENT/GOOD/AVERAGE/WEAK/POOR
  - Upserts into `fact_ml_scores`
  - Exports `data/clean/fact_ml_scores.csv`
  - Invalidates Redis cache when score delta > 2

- Orchestration: `orchestration/celery_app.py`, `orchestration/tasks.py`
  - Daily 1:00 AM ETL refresh
  - Daily 2:00 AM health score computation

- Analytics notebooks (6):
  - `notebooks/01_exploratory_data_analysis.ipynb`
  - `notebooks/02_financial_health_scoring.ipynb`
  - `notebooks/03_anomaly_detection.ipynb`
  - `notebooks/04_sector_clustering.ipynb`
  - `notebooks/05_peer_comparison_engine.ipynb`
  - `notebooks/06_trend_analysis_forecasting.ipynb`

### Stream C implemented

**Backend 2 (Production Features)**

Core orchestration & infrastructure (`orchestration/backend2/`):
- **celery_app.py** - Celery broker + beat scheduler with 6 production tasks
- **tasks.py** - 14 background job definitions (ETL, scoring, anomaly detection, forecasting)
- **cache.py** - Redis caching layer with TTL, bulk invalidation, `@cached_endpoint` decorator
- **partner_auth.py** - Channel Partner API authentication with rate limiting (60 req/min) & usage analytics
- **webhook.py** - Webhook dispatcher with exponential backoff retry logic
- **config.py** - Environment configuration loader
- **logging_utils.py** - Structured JSON logging with async queue handler
- **module_runner.py** - ETL module executor with subprocess management

Analytics engines (`etl/`):
- **proscons_generator.py** - Auto-generates pros/cons for companies (7 pro rules, 4 con rules)
- **anomaly_detector.py** - Z-score + Isolation Forest anomaly detection
- **trend_analyzer.py** - Linear regression trend classification + Holt-Winters forecasting

Scheduled tasks (daily + weekly):
- 1:00 AM IST: ETL pipeline refresh
- 2:00 AM IST: Company health score recalculation
- 2:30 AM IST: Pros/cons statement generation
- Sunday 3:00 AM IST: Anomaly detection (Z-score + Isolation Forest)
- Sunday 4:00 AM IST: Trend analysis + revenue forecasting
- Every 15 minutes: System health check

**Django + REST API**

- Django project scaffold: `django_app/`
- Public routes:
  - `/`
  - `/companies/`
  - `/company/{symbol}/`
  - `/compare/`
  - `/screener/`
  - `/sector/{name}/`
  - `/admin-insights/`
- Public data API routes under `/api/v1/`:
  - `GET /home/`
  - `GET /companies/`
  - `GET /companies/{symbol}/charts/`
  - `GET /compare/`
  - `GET /screener/`
  - `GET /sectors/{name}/`
  - `GET /admin/summary/`
- Partner API routes under `/api/partner/v1/`:
  - `GET /companies/{symbol}/full/`
  - `GET /bulk-financials/`
  - `GET /screener/`
  - `GET /scores/`
  - `GET/POST /keys/` - Token management
  - `DELETE /keys/{key_id}/` - Token revocation
  - `GET/POST /webhooks/` - Webhook management
  - `DELETE /webhooks/{webhook_id}/`
- Token-based authentication (SHA-256 hashing)
- Tier-based rate limiting (BASIC/PRO/ENTERPRISE)
- Async usage logging + webhook delivery via Celery
- OpenAPI docs via drf-spectacular:
  - `/api/docs/` (Swagger UI)
  - `/api/redoc/`

**Docker & Production Deployment**

6-service containerized stack (`docker-compose.prod.yml`):
- PostgreSQL 15 (data warehouse)
- Redis 7 (cache + message broker)
- Django (Gunicorn WSGI, 4 workers)
- Celery Worker (4 concurrent, 3600s timeout)
- Celery Beat (scheduled task scheduler)
- Nginx (reverse proxy, SSL/TLS, rate limiting, security headers)

Production configuration:
- SSL/TLS 1.2+ with strong ciphers
- Security headers (HSTS, CSP, X-Frame-Options)
- Rate limiting zones (10 req/s API, 100 req/min auth)
- Gzip compression, caching (30d static, 7d media)
- Health checks on all services
- Structured JSON logging (10MB rotating files)

## Star schema

Warehouse tables include:

- Dimensions: `dim_company`, `dim_year`, `dim_sector`, `dim_health_label`
- Facts: `fact_profit_loss`, `fact_balance_sheet`, `fact_cash_flow`, `fact_analysis`, `fact_ml_scores`, `fact_pros_cons`, `fact_documents`

## Inputs required from you

To complete the remaining production-level pieces, these are the specific inputs needed from you:

1. Final source SQL dump file (`data/source/scriptticker.sql`) with latest Nifty 100 data.
2. Confirmed sector/sub-sector mapping overrides if you want any changes beyond the default mapping.
3. Real API partner onboarding rules (tier assignments, billing/quotas policy, partner naming conventions).
4. Final branding assets for web and Power BI (logos, color tokens, typography preferences).
5. Hosting/deployment targets (local only, VM, Azure, AWS, or on-prem) for production configuration.
6. Power BI workspace details for publishing and scheduled refresh wiring.

## Quick start

### Local Development Setup

**1) Python environment**

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

**2) Environment variables**

```bash
cp .env.example .env
# Edit .env with your configuration:
# - DJANGO_SECRET_KEY (generate new)
# - DB_PASSWORD
# - REDIS_PASSWORD
```

**3) Start PostgreSQL & Redis**

Option A - Docker:
```bash
docker run -d -e POSTGRES_PASSWORD=secure_password -p 5432:5432 postgres:15-alpine
docker run -d -p 6379:6379 redis:7-alpine
```

Option B - Local installation:
```bash
# PostgreSQL and Redis must be running and accessible
# Update DATABASE_URL and REDIS_URL in .env
```

**4) Run Django migrations**

```bash
cd django_app
python manage.py migrate
python manage.py createsuperuser
cd ..
```

**5) Run ETL pipeline (manual)**

```bash
python etl/01_extract_from_mysql.py --sql-file data/source/scriptticker.sql --output-dir data/raw
python etl/02_clean_and_transform.py --raw-dir data/raw --clean-dir data/clean --sector-mapping data/sector_mapping.csv
python etl/03_load_to_warehouse.py --clean-dir data/clean
python analytics/health_scoring.py
```

**6) Run Django + Celery locally**

Terminal 1 - Django development server:
```bash
cd django_app
python manage.py runserver
# http://localhost:8000
```

Terminal 2 - Celery worker:
```bash
celery -A orchestration.backend2.celery_app worker -l info
```

Terminal 3 - Celery beat (scheduler):
```bash
celery -A orchestration.backend2.celery_app beat -l info
```

**7) Verify setup**

- Django: http://localhost:8000
- Swagger API docs: http://localhost:8000/api/docs/
- Admin panel: http://localhost:8000/admin/

### Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for:
- Docker Compose production stack setup
- SSL/TLS certificate configuration
- GitHub Actions CI/CD pipeline
- Environment variable configuration
- Database schema initialization
- Nginx reverse proxy setup

### CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci-pipeline.yml`):
1. **Lint** - Black, isort, Flake8
2. **Test** - pytest with PostgreSQL + Redis services
3. **Security** - Bandit static analysis
4. **Build** - Docker image (main branch only)
5. **Deploy** - SSH deployment with migrations (main branch only)

## Docker

Use Docker Compose to run PostgreSQL, Redis, Django, Celery worker, and Celery beat:

```bash
docker compose up --build
```

## Stream A next steps (Power BI)

1. Connect Power BI to PostgreSQL warehouse.
2. Build 7 dashboards against star schema (no direct raw-table imports).
3. Create DAX measure library for KPIs, growth, ranking, and health distributions.
4. Publish to Power BI Service with scheduled refresh after ETL completion.

## Documentation

- Runbook: `docs/runbook.md`
- Parallel execution roadmap: `docs/stream_roadmap.md`
