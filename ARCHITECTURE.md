# Architecture & Design Document

## System Overview

The Nifty 100 Financial Intelligence Platform is a three-stream data intelligence system for analyzing 100 major Indian companies:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Data Sources & ETL                             │
│  (MySQL dump → Extract → Clean → Transform → Load → Warehouse)  │
│                                                                   │
│  etl/01_extract_from_mysql.py                                    │
│  etl/02_clean_and_transform.py                                   │
│  etl/03_load_to_warehouse.py                                     │
│  etl/04_schedule_refresh.py                                      │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              PostgreSQL Data Warehouse (Star Schema)              │
│                                                                   │
│  Dimensions: dim_company, dim_year, dim_sector, dim_health_label │
│  Facts: fact_profit_loss, fact_balance_sheet, fact_cash_flow    │
│         fact_analysis, fact_ml_scores, fact_pros_cons           │
│         fact_anomaly_flags, fact_trend_analysis                 │
│         fact_revenue_forecast                                    │
└─────────────────┬────────────────────┬───────────────────┬──────┘
                  │                    │                   │
        ┌─────────▼──────────┐  ┌──────▼────────────┐    │
        │  Stream B: Analytics │  │ Stream C: API    │    │
        │  (ML & Insights)     │  │ (Distribution)   │    │
        └─────────┬────────────┘  └──────┬───────────┘    │
                  │                      │                 │
        ┌─────────▼──────────┐  ┌──────▼────────────┐    │
        │ analytics/          │  │ django_app/       │    │
        │ health_scoring.py   │  │ config/           │    │
        │ (0-100 scores)      │  │ settings.py       │    │
        │                     │  │                   │    │
        │ notebooks/          │  │ apps/             │    │
        │ 01_eda              │  │ - partner_api/    │    │
        │ 02_health_scoring   │  │ - public/         │    │
        │ 03_anomaly          │  │ - warehouse/      │    │
        │ 04_clustering       │  │                   │    │
        │ 05_peer_comparison  │  │ REST API Routes:  │    │
        │ 06_trends           │  │ /api/v1/*         │    │
        │                     │  │ /api/partner/v1/* │    │
        │                     │  │ /api/docs/        │    │
        └─────────┬───────────┘  └──────┬────────────┘    │
                  │                     │                 │
                  │    ┌────────────────┴──────────────┐  │
                  │    │                               │  │
        ┌─────────▼────────────────────────────────────┼──┴────┐
        │         Celery Beat & Task Orchestration      │       │
        │                                                │       │
        │  orchestration/backend2/celery_app.py        │ Redis │
        │  orchestration/backend2/tasks.py             │ (v7)  │
        │                                                │       │
        │  Daily Tasks:                                │       │
        │  - 1:00 AM: ETL pipeline refresh            │       │
        │  - 2:00 AM: Health score recalculation      │       │
        │  - 2:30 AM: Pros/cons generation            │       │
        │                                                │       │
        │  Weekly Tasks:                               │       │
        │  - Sun 3:00 AM: Anomaly detection           │       │
        │  - Sun 4:00 AM: Trend analysis + forecast   │       │
        │                                                │       │
        │  Every 15 min: System health check           │       │
        └─────────────────────────────────────────────┼───────┘
                                                       │
                                                       ▼
                            ┌──────────────────────────────────┐
                            │   Redis Cache & Message Broker    │
                            │                                   │
                            │  DB 0: Cache Layer               │
                            │  DB 1: Celery Broker             │
                            │  DB 2: Celery Result Backend     │
                            │                                   │
                            │  Cached Keys:                    │
                            │  - company_list                  │
                            │  - company_detail:{id}           │
                            │  - sector_list                   │
                            │  - health_scores                 │
                            │  - financial_trend:{id}:{year}   │
                            └──────────────────────────────────┘
```

## Key Components

### 1. Data Pipeline (Stream B)

**ETL Scripts** (`etl/`):
- **01_extract_from_mysql.py** - Parses SQL dump, handles escaped quotes, produces CSVs
- **02_clean_and_transform.py** - Standardizes formats, computes derived metrics, builds mappings
- **03_load_to_warehouse.py** - Star schema creation, idempotent loading, data quality checks
- **04_schedule_refresh.py** - Manual/Celery/Subprocess execution modes

**Analytics Engines** (`analytics/`):
- **health_scoring.py** - ML-based company health (0-100 score, 5 labels)
  - Metrics: Profitability, Growth, Leverage, Cash Flow, Dividend, Trend
  - Assigns: EXCELLENT, GOOD, AVERAGE, WEAK, POOR

**ML Notebooks** (`notebooks/`):
- EDA, Financial Health Scoring, Anomaly Detection, Sector Clustering
- Peer Comparison Engine, Trend Analysis & Forecasting

### 2. Backend Services (Stream C - Backend 2)

**Core Orchestration** (`orchestration/backend2/`):

| Module | Purpose | Key Features |
|--------|---------|--------------|
| `celery_app.py` | Celery initialization | Redis broker, beat schedule, JSON serialization |
| `tasks.py` | Background job definitions | 14 tasks, retry logic, auto-chaining |
| `cache.py` | Redis caching layer | TTL, patterns, @cached_endpoint decorator |
| `partner_auth.py` | API authentication | Token gen, rate limiting, usage analytics |
| `webhook.py` | Event delivery | Exponential backoff, max 3 retries |
| `config.py` | Environment loader | Defaults for all Backend 2 settings |
| `logging_utils.py` | Structured logging | JSON format, async queue, rotating files |
| `module_runner.py` | ETL executor | Subprocess management, 1-hour timeout |

**REST API** (`django_app/`):

- **Public API** (`/api/v1/`) - Company data, charts, screeners, sectors
- **Partner API** (`/api/partner/v1/`) - Token auth, webhooks, bulk data, usage stats
- **Admin API** - Company insights, admin summaries
- **API Docs** - Swagger/ReDoc via drf-spectacular
- **OpenAPI Schema** - Auto-generated from serializers

**Authentication & Authorization**:
- Token-based (not OAuth, custom implementation)
- SHA-256 secret hashing
- Rate limiting: 60 req/min default, configurable per partner
- Tier-based throttling: BASIC/PRO/ENTERPRISE
- Usage logging for analytics

**Data Models**:
- `partner_api_tokens` - API keys, secret hashes, expiry
- `api_usage_log` - Request analytics per partner
- `django_app/partner_api/models.py` - Partner, subscription tiers

### 3. Production Deployment Stack (Docker Compose)

6 containerized services with health checks:

| Service | Image | Purpose | Ports |
|---------|-------|---------|-------|
| PostgreSQL | postgres:15-alpine | Data warehouse, 15GB+ schema | 5432 |
| Redis | redis:7-alpine | Cache + message broker | 6379 |
| Django | python:3.11 (built) | Gunicorn WSGI, 4 workers | 8000 |
| Celery Worker | python:3.11 (built) | Background tasks, 4 concurrent | - |
| Celery Beat | python:3.11 (built) | Task scheduler | - |
| Nginx | nginx:alpine | Reverse proxy, SSL, rate limiting | 80, 443 |

**Networking**:
- Bridge network: `nifty100_network`
- Service discovery via DNS (docker-compose DNS)
- Health checks: HTTP (Django), CLI (Redis, PostgreSQL), wget (Nginx)

**Volumes**:
- `postgres_data` - Database persistence
- `redis_data` - Redis snapshot
- `django_static` - Collected static files
- `django_media` - User uploads
- `celery_logs`, `nginx_logs` - Structured JSON logs

**Logging**:
- `json-file` driver, max 10MB per file, 3-5 backups
- Async queue handler prevents I/O blocking
- All timestamps in ISO 8601

### 4. CI/CD Pipeline (GitHub Actions)

Multi-stage workflow (`.github/workflows/ci-pipeline.yml`):

1. **Lint** (all branches)
   - Black formatting
   - isort import sorting
   - Flake8 style checks
   - Pylint warnings

2. **Test** (all branches)
   - pytest with PostgreSQL + Redis test containers
   - Coverage reporting
   - Codecov integration

3. **Security** (all branches)
   - Bandit vulnerability scanning
   - Artifact upload

4. **Build** (main branch only)
   - Docker image build
   - Push to Docker Hub
   - Layer caching

5. **Deploy** (main branch, after build succeeds)
   - SSH into production
   - git pull, docker-compose up
   - Run migrations
   - Collect static files

## Data Flow Examples

### Company Profile Request
```
User Request → Nginx (rate limit, cache check) 
  → Django (auth, serialize) 
  → Redis (cache hit → return cached JSON, 1800s TTL)
  ↓ (cache miss)
  → PostgreSQL (SELECT from dim_company JOIN fact_ml_scores)
  → Redis (cache_set with 1800s TTL)
  → Nginx (gzip, cache header) 
  → User Response
```

### Daily ETL Refresh (1:00 AM IST)
```
Celery Beat triggers run_etl_pipeline_task
  → etl_transform_task (01, 02 scripts)
  → etl_load_task (03 script)
  → invalidate_cache_task (flush company_*, financial_trend:*)
  → Done, logs to structured JSON file
```

### Partner API Request with Rate Limiting
```
GET /api/partner/v1/companies/{symbol}/full/
  Headers: X-API-Key: token, X-API-Secret: secret
  
  → Nginx (rate limit zone: 10 req/s, burst 20)
  → Django (partner_auth.validate_api_token)
  → Cache lookup (company_detail:{id})
  ↓ (cache miss)
  → PostgreSQL (full join query)
  → Redis (cache, 1800s TTL)
  → log_api_usage (async Celery task)
  → webhook_dispatch (if configured)
  → Response (JSON, gzip)
```

### Anomaly Detection (Sunday 3:00 AM)
```
Celery Beat triggers detect_anomalies_task
  → PostgreSQL (SELECT 5-year financial data)
  → Z-score detection (> 3σ = critical)
  → Isolation Forest (5% contamination)
  → INSERT fact_anomaly_flags
  → Logs severity (warning/critical)
  → Task completes
```

## Scaling Considerations

### Vertical Scaling (Single Machine)
- **Celery Concurrency**: Increase `--concurrency` (default 4)
- **Gunicorn Workers**: Increase workers (default 4)
- **PostgreSQL**: Tune shared_buffers, work_mem, max_connections
- **Redis**: Monitor memory usage, configure eviction policy

### Horizontal Scaling (Multiple Machines)
- **Celery Workers**: Run on separate machines, shared Redis broker
- **PostgreSQL**: Streaming replication (primary-replica)
- **Redis**: Redis Cluster (6 nodes minimum)
- **Django**: Load balancer (Nginx, HAProxy)
- **Kubernetes**: Migrate to K8s for auto-scaling

### Performance Optimization
- Database indexes on company_id, partner_id, timestamp
- Redis key expiration (TTL)
- Gzip compression (all text responses)
- Static file caching (30 days)
- Connection pooling (SQLAlchemy)

## Security Architecture

### Network Security
- SSL/TLS 1.2+ (Nginx)
- HTTP → HTTPS redirect
- Firewall: Only allow 80, 443, SSH (22)

### Application Security
- CSRF protection (Django default)
- XSS protection (Content-Security-Policy header)
- Clickjacking protection (X-Frame-Options: SAMEORIGIN)
- SQL injection: SQLAlchemy ORM (parameterized queries)
- API authentication: Custom tokens (SHA-256 hashing)
- Rate limiting: Nginx + Django layers

### Data Security
- Database password hashing (not stored in code)
- Redis password authentication
- Django SECRET_KEY (environment variable)
- API secret never transmitted twice (hashed on storage)
- Logs redacted (no sensitive data)

### Monitoring & Audit
- API usage logging (partner_id, endpoint, response_time)
- Structured JSON logs (searchable)
- Health checks on all services
- Error tracking (Sentry integration ready)

## Technology Stack Summary

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Frontend** | Django Templates + React | 4.2 / TBD | Web UI & SPA |
| **Backend** | Django + DRF | 4.2, 3.15 | REST API |
| **Task Queue** | Celery | 5.4 | Background jobs |
| **Message Broker** | Redis | 7.0 | Queue + Cache |
| **Data Warehouse** | PostgreSQL | 15 | Analytics DB |
| **Reverse Proxy** | Nginx | Alpine | Load balancer, SSL |
| **Containers** | Docker | 24.0 | Packaging |
| **Orchestration** | Docker Compose | 3.9 | Local orchestration |
| **CI/CD** | GitHub Actions | - | Automated testing |
| **ML Libraries** | scikit-learn, statsmodels | 1.2, 0.13 | Analytics |
| **Python** | CPython | 3.11 | Runtime |

## Monitoring & Observability

### Logging
- **Format**: Structured JSON with timestamp, level, event, extra_data
- **Rotation**: 2MB files, 5 backups per service
- **Destinations**: Files + stdout (Docker logs)
- **Query**: `docker-compose logs -f django` or log aggregation tool

### Metrics (Ready for Integration)
- Celery task count, duration, failure rate
- API request count, latency, error rate
- Database connection pool usage
- Redis memory usage, eviction rate
- Nginx request count, response times

### Health Checks
- Django: `GET /health/` (200 OK)
- PostgreSQL: `pg_isready`
- Redis: `redis-cli PING`
- Nginx: `wget http://localhost/health/`

### Alerting (Ready for Integration)
- Service down alerts
- High error rates (>5%)
- Slow API responses (>2s)
- Database replication lag
- Celery task failures

## Disaster Recovery

### Backups
```bash
# Database: Daily via `docker-compose exec postgres pg_dump`
# Redis: Snapshots (every 3600s by default)
# Code: Git repository with tags
# Configuration: .env file (secure storage)
```

### Recovery Procedures
1. **Database Restore**: `psql < backup.sql`
2. **Cache Rebuild**: Celery task flush + regenerate
3. **Code Rollback**: `git checkout` + restart containers
4. **Full Stack Recovery**: Stop, restore files, start, migrate

---

**Last Updated**: May 30, 2026  
**Version**: 1.0 (Backend 2 Implementation Complete)  
**Status**: ✅ Production-Ready
