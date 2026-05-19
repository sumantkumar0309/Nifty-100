# Backend Developer 2 — Stream C Setup Guide

## Overview

As Backend Developer 2 (BE Dev 2), you are responsible for:

1. **Celery + Redis Integration** — Background job scheduling for ETL, ML scoring, pros/cons generation, anomaly detection, and trend analysis
2. **Channel Partner API** — Token-based authentication with rate limiting and usage logging
3. **Redis Caching Layer** — High-performance caching for frequently accessed endpoints
4. **BSE Annual Report API** — REST endpoint for document retrieval
5. **Docker Compose Production Config** — Full stack containerization (Django, Gunicorn, Nginx, Celery, Redis, PostgreSQL)
6. **GitHub CI/CD Pipeline** — Automated testing, linting, and deployment

---

## Project Structure

```
marketAI/backend/backend2/
├── tasks.py                  # Celery scheduled tasks
├── celery_app.py            # Celery app & beat scheduler configuration
├── cache.py                 # Redis caching utilities
├── partner_auth.py          # Channel partner authentication
├── logging_utils.py         # Logging configuration
├── config.py                # Environment configuration
├── module_runner.py         # ETL module execution wrapper
├── webhook.py               # Webhook delivery system
└── Dockerfile               # Production Django container image

etl/
├── proscons_generator.py    # Pro/con rule engine
├── anomaly_detector.py      # Anomaly detection (Z-score, Isolation Forest)
└── trend_analyzer.py        # Trend analysis & forecasting

docker/
├── docker-compose.prod.yml  # Production orchestration
├── nginx/
│   ├── nginx.conf           # Reverse proxy config
│   └── conf.d/default.conf  # Site-specific configuration
└── ssl/                     # SSL certificates (locally managed or Let's Encrypt)

.github/workflows/
└── ci-pipeline.yml          # GitHub Actions CI/CD pipeline
```

---

## Task 1: Celery + Redis Integration

### Overview

Celery is a distributed task queue for executing background jobs. It uses Redis as the message broker and result backend.

### Files Modified: `tasks.py` and `celery_app.py`

**Scheduled Tasks Created:**

1. **`run_etl_pipeline_task`** — Daily 1:00 AM
   - Runs ETL scripts 2 & 3 (transform, load)
   - Invalidates related cache patterns

2. **`score_all_companies_task`** — Daily 2:00 AM
   - Recalculates health scores for all 100 companies
   - Calls ML refresh module

3. **`generate_pros_cons_task`** — Daily 2:30 AM
   - Runs the pros/cons rule engine
   - Generates financial statement pairs for each company

4. **`detect_anomalies_task`** — Weekly Sunday 3:00 AM
   - Z-score anomaly detection
   - Isolation Forest ML-based detection

5. **`detect_trends_task`** — Weekly Sunday 4:00 AM
   - Linear regression trend analysis (UP/FLAT/DOWN)
   - Revenue forecasting for top 20 companies

6. **`system_health_task`** — Every 15 minutes
   - Health check: Redis connectivity, system status

### Configuration (in `config.py`)

```python
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", "Asia/Kolkata")
```

### Running Celery

**Start Celery Worker:**
```bash
celery -A backend2 worker -l info --concurrency=4
```

**Start Celery Beat Scheduler:**
```bash
celery -A backend2 beat -l info
```

---

## Task 2: Channel Partner API Authentication

### Overview

Secure REST API access for external channel partners using token-based authentication with rate limiting.

### File: `partner_auth.py`

**Key Functions:**

1. **`generate_api_token(partner_id, partner_name)`**
   - Generates a unique API token and secret
   - Stores hash in database (tokens never exposed again)
   - Returns 365-day validity token

2. **`validate_api_token(token, secret)`**
   - Validates token/secret combination
   - Checks expiry and active status
   - Returns partner information if valid

3. **`check_rate_limit(partner_id, requests_per_minute=60)`**
   - Enforces per-minute rate limits
   - Returns remaining quota and reset time

4. **`log_api_usage(...)`**
   - Logs every API call for analytics
   - Tracks response time, status codes, payload sizes

5. **`get_partner_usage_stats(partner_id, days=30)`**
   - Retrieves usage statistics over a period
   - Success rate, average response times, error counts

### Database Tables Required

```sql
CREATE TABLE partner_api_tokens (
    id SERIAL PRIMARY KEY,
    partner_id VARCHAR(100),
    partner_name VARCHAR(255),
    token_hash VARCHAR(64),
    secret_hash VARCHAR(64),
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    is_active BOOLEAN,
    UNIQUE(token_hash)
);

CREATE TABLE api_usage_log (
    id SERIAL PRIMARY KEY,
    partner_id VARCHAR(100),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    response_status INT,
    response_time_ms FLOAT,
    request_size_bytes INT,
    response_size_bytes INT,
    timestamp TIMESTAMP
);

CREATE INDEX idx_partner_api_usage ON api_usage_log(partner_id, timestamp);
CREATE INDEX idx_endpoint_usage ON api_usage_log(endpoint, timestamp);
```

### Django REST Framework Integration

In your Django views:

```python
from backend2.partner_auth import validate_api_token, check_rate_limit, log_api_usage

def api_company_list(request):
    # Extract token from Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token = auth_header.replace('Bearer ', '')
    secret = request.META.get('HTTP_X_API_SECRET', '')
    
    # Validate token
    is_valid, error, partner_info = validate_api_token(token, secret)
    if not is_valid:
        return Response({'error': error}, status=401)
    
    # Check rate limit
    is_allowed, rate_info = check_rate_limit(partner_info['partner_id'])
    if not is_allowed:
        return Response({'error': 'Rate limit exceeded'}, status=429)
    
    # ... Process request ...
    
    # Log usage
    log_api_usage(
        partner_id=partner_info['partner_id'],
        endpoint='/api/v1/companies/',
        method='GET',
        response_status=200,
        response_time_ms=45.2
    )
```

---

## Task 3: Redis Caching Layer

### File: `cache.py`

**High-Performance Caching Functions:**

1. **`cache_get(key)`** — Retrieve cached value
2. **`cache_set(key, value, ttl_seconds=3600)`** — Store value with TTL
3. **`cache_delete(key)`** — Delete specific key
4. **`cache_delete_pattern(pattern)`** — Bulk delete by pattern
5. **`@cached_endpoint(ttl_seconds=3600, key_prefix="")`** — Decorator for endpoint caching

### Usage Example

```python
from backend2.cache import cache_get, cache_set, cached_endpoint, CACHE_KEYS

# Manual caching
@cached_endpoint(ttl_seconds=1800, key_prefix="company_detail")
def get_company_detail(company_id):
    # Expensive database query
    return Company.objects.get(id=company_id)

# Or manually:
def get_sector_list(request):
    cache_key = CACHE_KEYS["sector_list"]
    cached_data = cache_get(cache_key)
    if cached_data:
        return Response(cached_data)
    
    # Fetch data
    sectors = Sector.objects.all().values()
    
    # Cache for 2 hours
    cache_set(cache_key, list(sectors), ttl_seconds=7200)
    return Response(sectors)
```

### Cache Invalidation Strategy

```python
from backend2.cache import cache_delete_pattern

# After ETL completes, invalidate affected caches:
cache_delete_pattern("company_profile:*")
cache_delete_pattern("financial_trend:*")
cache_delete_pattern("dashboard_summary:*")
```

---

## Task 4: BSE Annual Report PDF Endpoint

### Django View Example

```python
from django.http import FileResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def get_bse_annual_report(request, company_id, year):
    """
    Retrieve BSE annual report PDF for a company.
    
    Endpoint: GET /api/v1/companies/{company_id}/reports/{year}/
    
    Returns:
        - PDF file download
        - 404 if document not found
    """
    try:
        document = Document.objects.get(
            company_id=company_id,
            year=year,
            document_type='annual_report'
        )
        
        # Log usage
        log_api_usage(
            partner_id=request.user.partner_id,
            endpoint=f'/api/v1/companies/{company_id}/reports/{year}/',
            method='GET',
            response_status=200,
            response_time_ms=12.5
        )
        
        return FileResponse(
            open(document.file_path, 'rb'),
            as_attachment=True,
            filename=f"{document.company_name}_{year}_report.pdf"
        )
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=404)
```

---

## Task 5: Docker Compose Production Configuration

### File: `docker-compose.prod.yml`

**Services Included:**

1. **PostgreSQL** — Data warehouse with persistent volumes
2. **Redis** — Cache & message broker with persistence
3. **Django** — Gunicorn WSGI application server
4. **Celery Worker** — Background task processing
5. **Celery Beat** — Scheduled task scheduler
6. **Nginx** — Reverse proxy, load balancer, SSL termination

### Running Production Stack

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f django

# Run migrations
docker-compose -f docker-compose.prod.yml exec django python manage.py migrate

# Create superuser
docker-compose -f docker-compose.prod.yml exec django python manage.py createsuperuser
```

### Health Checks

All services have built-in health checks:
- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`
- Django: HTTP GET `/health/`
- Nginx: HTTP check to health endpoint

### Volumes

- `postgres_data` — Database persistence
- `redis_data` — Redis persistence
- `django_static` — Static files for Nginx
- `django_media` — User-uploaded media
- `celery_logs` — Task execution logs

---

## Task 6: GitHub Actions CI/CD Pipeline

### File: `.github/workflows/ci-pipeline.yml`

**Pipeline Stages:**

1. **Lint** (Black, isort, Flake8)
   - Code formatting checks
   - Import sorting
   - Style violations

2. **Test** (pytest + coverage)
   - Unit tests
   - Integration tests
   - Coverage report to Codecov

3. **Security** (Bandit)
   - Static security analysis
   - Vulnerability detection

4. **Build** (Docker)
   - Builds Docker image on main branch only
   - Pushes to Docker Hub if credentials configured

5. **Deploy** (Production)
   - SSH into production server
   - Pulls latest code
   - Restarts services

### GitHub Secrets Required

```
DOCKER_USERNAME = your-docker-hub-username
DOCKER_PASSWORD = your-docker-hub-password
DEPLOY_KEY = SSH private key for production server
DEPLOY_HOST = Production server IP/hostname
DEPLOY_USER = SSH user (usually ubuntu or ec2-user)
GITHUB_TOKEN = GitHub personal access token (auto-provided)
```

### Branching Strategy

- **main** — Production. Merges trigger deployment.
- **dev/develop** — Staging. Runs CI tests only.
- **feature/*** — Feature branches. Run CI tests.

### Running Locally

```bash
# Lint
black marketAI/backend etl
isort marketAI/backend etl
flake8 marketAI/backend etl

# Test
pytest marketAI/backend/app/tests/ -v --cov

# Security scan
bandit -r marketAI/backend etl
```

---

## Environment Configuration

### `.env` File (Update `.env.example`)

Key variables for BE Dev 2:

```bash
# Django & Security
DJANGO_SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
DEBUG=false

# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/nifty100_warehouse

# Redis & Celery
REDIS_URL=redis://:password@redis:6379/0
CELERY_BROKER_URL=redis://:password@redis:6379/1
CELERY_RESULT_BACKEND=redis://:password@redis:6379/2

# API Rate Limiting
API_RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Logging
BACKEND2_LOG_LEVEL=INFO
```

---

## Quick Start Checklist

- [ ] Configure environment variables in `.env`
- [ ] Create PostgreSQL tables for authentication & usage logging
- [ ] Start Redis: `redis-server` or Docker
- [ ] Start Celery: `celery -A backend2 worker -l info`
- [ ] Start Celery Beat: `celery -A backend2 beat -l info`
- [ ] Test token generation & API authentication
- [ ] Verify cache operations are working
- [ ] Test Docker Compose stack locally
- [ ] Set up GitHub secrets for CI/CD
- [ ] Configure SSL certificates for production

---

## Monitoring & Debugging

### Monitor Celery Tasks

```bash
# Flower (Web UI for Celery)
pip install flower
celery -A backend2 flower

# Visit: http://localhost:5555
```

### Check Redis Cache

```bash
redis-cli
> SELECT 0
> KEYS *
> GET company_profile:123
```

### View API Usage Logs

```sql
SELECT 
    partner_id, 
    endpoint, 
    COUNT(*) as calls, 
    AVG(response_time_ms) as avg_response_time
FROM api_usage_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY partner_id, endpoint;
```

### Docker Logs

```bash
docker-compose -f docker-compose.prod.yml logs -f <service_name>
```

---

## Support & Documentation

- **Celery**: https://docs.celeryproject.io
- **Redis**: https://redis.io/documentation
- **Docker Compose**: https://docs.docker.com/compose/
- **Django**: https://docs.djangoproject.com
- **GitHub Actions**: https://docs.github.com/en/actions

---

**Start with Task 1: Set up Celery scheduled tasks and verify they execute correctly.**
