# Quick Reference Guide for Team Members

**Last Updated**: May 30, 2026  
**For Team Members**: Backend Dev 1, Frontend Dev, Data Analyst Teammate, DevOps

---

## 🚀 Getting Started

### Backend Dev 1: Building REST Endpoints

You have access to these utilities:

**1. API Authentication** (`orchestration/backend2/partner_auth.py`)
```python
from orchestration.backend2.partner_auth import (
    generate_api_token,      # Create token for new partner
    validate_api_token,      # Verify token in requests
    check_rate_limit,        # Enforce rate limiting
    log_api_usage,           # Track API calls
)

# In your Django view:
from rest_framework.decorators import api_view
from orchestration.backend2.partner_auth import validate_api_token

@api_view(['GET'])
def your_endpoint(request):
    token = request.headers.get('X-API-Key')
    secret = request.headers.get('X-API-Secret')
    
    is_valid, partner_id, partner_info = validate_api_token(token, secret)
    if not is_valid:
        return Response({'error': 'Invalid credentials'}, status=401)
    
    # Your endpoint logic here...
```

**2. Response Caching** (`orchestration/backend2/cache.py`)
```python
from orchestration.backend2.cache import cached_endpoint

@cached_endpoint(ttl_seconds=1800, key_prefix='company_detail')
@api_view(['GET'])
def get_company_detail(request, symbol):
    # This response will be cached for 30 minutes
    # No changes needed - decorator handles it!
    company = Company.objects.get(symbol=symbol)
    serializer = CompanySerializer(company)
    return Response(serializer.data)
```

**3. Webhook Delivery** (`orchestration/backend2/webhook.py`)
```python
from orchestration.backend2.webhook import send_webhook_with_retry

# Send event to partner webhooks
webhook_result = send_webhook_with_retry(
    url="https://partner.com/webhook",
    payload={"event": "company_updated", "data": {...}},
    headers={"Authorization": "Bearer token"},
    timeout_seconds=20,
    max_attempts=3,
    base_backoff_seconds=30
)
```

**4. Structured Logging** (`orchestration/backend2/logging_utils.py`)
```python
from orchestration.backend2.logging_utils import get_logger

logger = get_logger(__name__)

# Structured logging (JSON format)
logger.info("API call", extra={
    'event': 'api_call',
    'partner_id': partner_id,
    'endpoint': 'GET /api/v1/companies',
    'response_time_ms': 42
})

logger.error("API error", extra={
    'event': 'api_error',
    'error_code': 500,
    'message': str(e)
})
```

### Frontend Dev: Using API Endpoints

**Base URL**: `https://your-domain.com`

**Public API** (no authentication):
```javascript
// Get all companies
GET /api/v1/companies/?sector=IT&page=1
Response: { count: 100, next: ..., results: [...] }

// Get company detail
GET /api/v1/companies/INFY/
Response: { symbol: "INFY", name: "Infosys", ..., health_score: 85 }

// Compare companies
GET /api/v1/compare/?symbols=INFY,TCS,WIPRO
Response: { INFY: {...}, TCS: {...}, WIPRO: {...} }

// Get sector analysis
GET /api/v1/sectors/IT/
Response: { companies: 10, avg_pe: 25.3, sector_trend: "UP" }
```

**API Documentation**:
- Swagger UI: `https://your-domain.com/api/docs/`
- ReDoc: `https://your-domain.com/api/redoc/`
- OpenAPI schema: `https://your-domain.com/api/schema/`

**CORS**: Configured for `http://localhost:3000` (React dev server)

### Data Analyst: Accessing Warehouse Data

**Direct SQL Access**:
```python
from django.db import connections

with connections['default'].cursor() as cursor:
    # Query the warehouse
    cursor.execute("""
        SELECT c.symbol, c.company_name, f.sales, f.net_profit
        FROM dim_company c
        JOIN fact_profit_loss f ON c.company_id = f.company_id
        WHERE f.fiscal_year = 2024
        ORDER BY f.sales DESC
        LIMIT 10
    """)
    top_companies = cursor.fetchall()
```

**Celery Tasks for Automation**:
```python
from orchestration.backend2.tasks import (
    run_etl_pipeline_task,           # Full ETL refresh
    score_all_companies_task,        # Recalculate health scores
    detect_anomalies_task,           # Find financial anomalies
    detect_trends_task,              # Analyze trends & forecast
)

# Trigger manually (will run in background)
run_etl_pipeline_task.delay()

# Check status
from celery.result import AsyncResult
result = AsyncResult('task-id-here')
print(result.status)  # PENDING, STARTED, SUCCESS, FAILURE
print(result.result)  # Task output
```

**Pre-built Notebooks**:
- `notebooks/01_exploratory_data_analysis.ipynb` - Data exploration
- `notebooks/02_financial_health_scoring.ipynb` - Score methodology
- `notebooks/03_anomaly_detection.ipynb` - Anomaly examples
- `notebooks/04_sector_clustering.ipynb` - Sector groups
- `notebooks/05_peer_comparison_engine.ipynb` - Comparison logic
- `notebooks/06_trend_analysis_forecasting.ipynb` - Forecast demo

### DevOps: Deployment & Monitoring

**Start Production Stack**:
```bash
docker-compose -f docker-compose.prod.yml up -d
docker-compose ps                      # Check service status
docker-compose logs -f django          # View Django logs
docker-compose exec django python manage.py migrate  # Migrations
```

**View Logs**:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f celery_worker
docker-compose logs -f nginx

# Last 100 lines
docker-compose logs --tail 100 django
```

**Backup Database**:
```bash
docker-compose exec postgres pg_dump -U nifty100 nifty100_warehouse > backup.sql

# Restore
docker-compose exec -T postgres psql -U nifty100 nifty100_warehouse < backup.sql
```

**Monitor Celery Tasks**:
```bash
# Scheduled tasks
docker-compose exec celery_beat celery -A orchestration.backend2.celery_app inspect scheduled

# Active tasks
docker-compose exec celery_beat celery -A orchestration.backend2.celery_app inspect active

# Task stats
docker-compose exec celery_beat celery -A orchestration.backend2.celery_app inspect stats
```

---

## 📊 Database Schema Quick Reference

```sql
-- Dimensions
dim_company (company_id, symbol, name, sector)
dim_year (year_id, fiscal_year)
dim_sector (sector_id, sector_name)
dim_health_label (label_id, label_name, color)

-- Facts
fact_profit_loss (pl_id, company_id, year_id, sales, net_profit, operating_profit)
fact_balance_sheet (bs_id, company_id, year_id, total_assets, equity, borrowings)
fact_cash_flow (cf_id, company_id, year_id, operating_activity, investing_activity, financing_activity)
fact_analysis (analysis_id, company_id, year_id, pe_ratio, roe, debt_to_equity)
fact_ml_scores (score_id, company_id, score, health_label_id, created_at)

-- Backend 2
partner_api_tokens (id, partner_id, partner_name, token_hash, secret_hash, expires_at, is_active)
api_usage_log (id, partner_id, endpoint, method, response_status, response_time_ms, timestamp)

-- Analytics
fact_pros_cons (id, company_id, statement, type) -- 'pro' or 'con'
fact_anomaly_flags (id, company_id, fiscal_year, anomaly_type, severity, detected_at)
fact_trend_analysis (id, company_id, trend_class, slope, r_squared, detected_at)
fact_revenue_forecast (id, company_id, forecast_year, forecast_revenue, confidence_lower, confidence_upper, forecasted_at)
```

---

## 🔧 Common Tasks

### How to: Generate API Token for Partner
```python
from orchestration.backend2.partner_auth import generate_api_token

token_data = generate_api_token('partner_001', 'Partner Company Name')
print(f"Token: {token_data['token']}")
print(f"Secret: {token_data['secret']}")  # Show once, then hide!
print(f"Expires: {token_data['expires_at']}")
```

### How to: Check API Rate Limit Status
```python
from orchestration.backend2.partner_auth import check_rate_limit

is_allowed, rate_info = check_rate_limit('partner_001', requests_per_minute=60)
if is_allowed:
    print("Request allowed")
else:
    print(f"Rate limit exceeded. Reset in {rate_info['reset_in_seconds']}s")
```

### How to: Clear Cache for Company Profiles
```python
from orchestration.backend2.cache import cache_delete_pattern

# Clear all company profile caches
deleted_count = cache_delete_pattern('company_profile:*')
print(f"Cleared {deleted_count} cache entries")
```

### How to: Manually Trigger ETL
```bash
# Option 1: Via Celery task
docker-compose exec django python -c "
from orchestration.backend2.tasks import run_etl_pipeline_task
result = run_etl_pipeline_task.delay()
print(f'Task ID: {result.id}')
"

# Option 2: Direct script execution
docker-compose exec django python etl/01_extract_from_mysql.py --sql-file data/source/scriptticker.sql --output-dir data/raw
docker-compose exec django python etl/02_clean_and_transform.py --raw-dir data/raw --clean-dir data/clean
docker-compose exec django python etl/03_load_to_warehouse.py --clean-dir data/clean
```

### How to: Create Django Superuser
```bash
docker-compose exec django python manage.py createsuperuser
# Follow the prompts...
# Then access: https://your-domain.com/admin/
```

### How to: Scale Celery Workers
```bash
# Edit docker-compose.prod.yml, increase --concurrency value:
# command: celery -A orchestration.backend2.celery_app worker -l info --concurrency=8

# Then restart:
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d celery_worker
```

---

## 📞 Support & Troubleshooting

### API Endpoints Not Responding
```bash
# Check Django service
docker-compose ps django
docker-compose logs django  # View errors

# Restart Django
docker-compose restart django
```

### Celery Tasks Not Running
```bash
# Check worker status
docker-compose logs celery_worker

# Check beat schedule
docker-compose exec celery_beat celery -A orchestration.backend2.celery_app inspect scheduled

# Restart worker
docker-compose restart celery_worker
```

### Database Connection Issues
```bash
# Test database connection
docker-compose exec postgres pg_isready

# Check DATABASE_URL
docker-compose exec django echo $DATABASE_URL

# View PostgreSQL logs
docker-compose logs postgres
```

### Redis Connection Issues
```bash
# Test Redis connection
docker-compose exec redis redis-cli -a $REDIS_PASSWORD ping

# View Redis logs
docker-compose logs redis

# Check memory usage
docker-compose exec redis redis-cli -a $REDIS_PASSWORD INFO memory
```

### Rate Limiting Not Working
```bash
# Check Nginx rate limit zones are loaded
docker-compose exec nginx nginx -t

# View Nginx logs
docker-compose logs nginx

# Restart Nginx
docker-compose restart nginx
```

---

## 📚 Key Files by Role

### Backend Dev 1
- `django_app/config/settings.py` - Django configuration
- `django_app/apps/partner_api/` - API views & serializers
- `orchestration/backend2/cache.py` - Caching utilities
- `orchestration/backend2/partner_auth.py` - Authentication utilities

### Frontend Dev
- `README.md` - API endpoints overview
- `docker/nginx/conf.d/default.conf` - CORS & rate limiting config
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`

### Data Analyst
- `etl/` - ETL scripts
- `analytics/health_scoring.py` - Scoring engine
- `notebooks/` - Jupyter exploration
- `orchestration/backend2/tasks.py` - Scheduled tasks

### DevOps
- `docker-compose.prod.yml` - Service orchestration
- `Dockerfile` - Container image
- `DEPLOYMENT.md` - Deployment guide
- `.github/workflows/ci-pipeline.yml` - CI/CD pipeline

---

## 🎯 Next Steps

1. **Immediate** (Today):
   - Verify all services running: `docker-compose ps`
   - Check health endpoint: `curl http://localhost:8000/health/`
   - Access API docs: http://localhost:8000/api/docs/

2. **Short-term** (This Week):
   - Configure `.env` with production values
   - Create database schema from `sql/warehouse_schema.sql`
   - Generate SSL certificates
   - Configure GitHub Actions secrets

3. **Medium-term** (Next Week):
   - Load initial data via ETL
   - Backend Dev 1 builds REST endpoints
   - Frontend Dev connects to APIs
   - Test Celery scheduled tasks

4. **Long-term** (Next Month):
   - Deploy to production
   - Configure monitoring (Sentry, Datadog)
   - Set up automated backups
   - Train team on operations

---

## 📞 Contact & Questions

For questions about specific modules, refer to:
- **Celery/Tasks**: See `orchestration/backend2/tasks.py` docstrings
- **API Auth**: See `orchestration/backend2/partner_auth.py` docstrings
- **Caching**: See `orchestration/backend2/cache.py` docstrings
- **Deployment**: See `DEPLOYMENT.md` troubleshooting section
- **Architecture**: See `ARCHITECTURE.md` for detailed system design

---

**Happy coding! 🚀**

*For the most up-to-date information, always refer to the main documentation files:*
- *README.md*
- *ARCHITECTURE.md*
- *DEPLOYMENT.md*
