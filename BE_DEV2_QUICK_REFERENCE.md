# Backend Developer 2 — Quick Reference Card

## 🚀 Getting Started (5 minutes)

### 1. Copy Environment Template
```bash
cp .env.example .env
# Edit .env with your configuration
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
pip install -r marketAI/backend/requirements-backend2.txt
```

### 3. Start Services (Development)
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Django
cd marketAI/backend/backend1
python manage.py runserver

# Terminal 3: Celery Worker
celery -A backend2 worker -l info

# Terminal 4: Celery Beat
celery -A backend2 beat -l info
```

### 4. Start Services (Production)
```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📋 Task Checklist

- [ ] Set up `.env` configuration
- [ ] Create PostgreSQL tables (partner_api_tokens, api_usage_log)
- [ ] Test Redis connection: `redis-cli ping`
- [ ] Run Django migrations: `python manage.py migrate`
- [ ] Generate API token: `python manage.py shell_plus` (use partner_auth.py)
- [ ] Test Celery task: `celery -A backend2 call backend2.tasks.system_health_task`
- [ ] Verify cache operations
- [ ] Build Docker image: `docker build -t nifty100 marketAI/backend/`
- [ ] Test docker-compose: `docker-compose -f docker-compose.prod.yml config`

---

## 🔧 Common Commands

### Celery Management
```bash
# Start worker (4 concurrent processes)
celery -A backend2 worker -l info --concurrency=4

# Start beat scheduler
celery -A backend2 beat -l info

# Monitor Flower UI
celery -A backend2 flower
# Visit: http://localhost:5555

# Check active tasks
celery -A backend2 inspect active

# Check registered tasks
celery -A backend2 inspect registered
```

### Redis Management
```bash
# Connect to Redis CLI
redis-cli

# Authenticate (if password set)
AUTH your-password

# Check connection
PING

# View cache keys
KEYS *

# View specific key
GET company_profile:123

# Delete pattern
DEL company_profile:*

# Monitor in real-time
MONITOR
```

### Django Management
```bash
# Create superuser
python manage.py createsuperuser

# Run migrations
python manage.py migrate

# Create migration for changes
python manage.py makemigrations

# Django shell
python manage.py shell_plus

# Run tests
pytest app/tests/ -v --cov
```

### Docker Management
```bash
# Build image
docker build -t nifty100-django marketAI/backend/

# Start stack
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f django

# Execute command in container
docker-compose -f docker-compose.prod.yml exec django python manage.py migrate

# Stop stack
docker-compose -f docker-compose.prod.yml down

# Remove volumes (⚠️ data loss)
docker-compose -f docker-compose.prod.yml down -v
```

---

## 💾 Database Schema

### partner_api_tokens
```sql
CREATE TABLE partner_api_tokens (
    id SERIAL PRIMARY KEY,
    partner_id VARCHAR(100),
    partner_name VARCHAR(255),
    token_hash VARCHAR(64) UNIQUE,
    secret_hash VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### api_usage_log
```sql
CREATE TABLE api_usage_log (
    id SERIAL PRIMARY KEY,
    partner_id VARCHAR(100),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    response_status INT,
    response_time_ms FLOAT,
    request_size_bytes INT,
    response_size_bytes INT,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_partner_usage ON api_usage_log(partner_id, timestamp);
CREATE INDEX idx_endpoint_usage ON api_usage_log(endpoint, timestamp);
```

---

## 🔐 API Authentication

### Generate Token (Python)
```python
from backend2.partner_auth import generate_api_token

result = generate_api_token('partner_123', 'Acme Corp')
# Returns: {
#   'token': '...',
#   'secret': '...',
#   'partner_id': 'partner_123',
#   'expires_at': '2025-05-19T10:00:00'
# }
```

### Validate Token (Django View)
```python
from backend2.partner_auth import validate_api_token, check_rate_limit
from rest_framework.response import Response

def api_endpoint(request):
    token = request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')
    secret = request.META.get('HTTP_X_API_SECRET', '')
    
    is_valid, error, partner = validate_api_token(token, secret)
    if not is_valid:
        return Response({'error': error}, status=401)
    
    is_allowed, rate_info = check_rate_limit(partner['partner_id'])
    if not is_allowed:
        return Response({'error': 'Rate limit exceeded'}, status=429)
    
    # Process request...
```

---

## 💾 Caching Examples

### Auto-Cache Endpoint
```python
from backend2.cache import cached_endpoint

@cached_endpoint(ttl_seconds=1800, key_prefix="company_detail")
def get_company_detail(company_id):
    # Expensive operation
    return Company.objects.get(id=company_id)
```

### Manual Cache
```python
from backend2.cache import cache_get, cache_set, cache_delete

# Get
data = cache_get('my_key')

# Set (1 hour TTL)
cache_set('my_key', {'data': 123}, ttl_seconds=3600)

# Delete
cache_delete('my_key')

# Delete pattern
cache_delete_pattern('company_profile:*')
```

### Pre-defined Keys
```python
from backend2.cache import CACHE_KEYS

# Use predefined keys
cache_key = CACHE_KEYS["company_detail"].format(company_id=123)
# Result: "company_detail:123"
```

---

## 📊 Celery Scheduled Tasks

| Task | Schedule | File | Status |
|------|----------|------|--------|
| run_etl_pipeline_task | 1:00 AM daily | tasks.py | ✅ |
| score_all_companies_task | 2:00 AM daily | tasks.py | ✅ |
| generate_pros_cons_task | 2:30 AM daily | tasks.py | ✅ |
| detect_anomalies_task | Sunday 3:00 AM | tasks.py | ✅ |
| detect_trends_task | Sunday 4:00 AM | tasks.py | ✅ |
| system_health_task | Every 15 min | tasks.py | ✅ |

---

## 📈 Monitoring & Debugging

### Check Celery Status
```bash
celery -A backend2 inspect active
celery -A backend2 inspect scheduled
celery -A backend2 inspect stats
```

### View Redis Memory
```bash
redis-cli info memory
```

### Monitor Docker Logs
```bash
docker-compose -f docker-compose.prod.yml logs -f --tail=100
```

### Query API Usage
```sql
SELECT partner_id, COUNT(*) as calls, AVG(response_time_ms) as avg_time
FROM api_usage_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY partner_id;
```

---

## 🧪 Testing

### Run Unit Tests
```bash
pytest app/tests/ -v
```

### Run with Coverage
```bash
pytest app/tests/ -v --cov=backend2 --cov-report=html
```

### Test Partner Auth
```python
from backend2.partner_auth import generate_api_token, validate_api_token

token_info = generate_api_token('test_partner', 'Test Org')
is_valid, error, partner = validate_api_token(token_info['token'], token_info['secret'])
assert is_valid == True
```

### Test Cache
```python
from backend2.cache import cache_set, cache_get

cache_set('test_key', {'value': 123})
result = cache_get('test_key')
assert result == {'value': 123}
```

---

## 🚨 Troubleshooting

### Redis Connection Refused
```bash
# Check if Redis is running
redis-cli ping
# If error, start Redis:
redis-server

# For Docker:
docker ps | grep redis
```

### Celery Tasks Not Running
```bash
# Check if Beat scheduler is running
celery -A backend2 inspect active_queues

# Check for errors
celery -A backend2 worker -l debug

# Manually trigger task
from backend2.tasks import system_health_task
system_health_task()
```

### Docker Build Fails
```bash
# Remove cache
docker build --no-cache -t nifty100-django marketAI/backend/

# Check dependencies
pip install -r marketAI/backend/requirements-backend2.txt
```

### Rate Limiting Not Working
```sql
-- Check recent API calls
SELECT * FROM api_usage_log 
WHERE partner_id = 'your_partner' 
ORDER BY timestamp DESC LIMIT 5;

-- Check if table exists
SELECT * FROM api_usage_log LIMIT 1;
```

---

## 📚 Environment Variables

### Essential
```bash
DJANGO_SECRET_KEY=<your-secret>
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0
CELERY_BROKER_URL=redis://host:6379/1
```

### Important
```bash
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
API_RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### Optional
```bash
SENTRY_DSN=
EMAIL_HOST_USER=
SECURE_SSL_REDIRECT=true
```

---

## 🔗 Quick Links

| Resource | URL |
|----------|-----|
| Celery Docs | https://docs.celeryproject.io |
| Redis Docs | https://redis.io/documentation |
| Docker Docs | https://docs.docker.com |
| Django Docs | https://docs.djangoproject.com |
| GitHub Actions | https://docs.github.com/en/actions |
| Nginx Docs | https://nginx.org/en/docs/ |

---

## 💡 Tips & Tricks

### Backup PostgreSQL
```bash
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U nifty100 nifty100_warehouse > backup.sql
```

### Restore PostgreSQL
```bash
docker-compose -f docker-compose.prod.yml exec postgres psql -U nifty100 nifty100_warehouse < backup.sql
```

### Scale Celery Workers
```bash
docker-compose -f docker-compose.prod.yml up -d --scale celery_worker=3
```

### Monitor CPU/Memory
```bash
docker stats
```

### SSH into Container
```bash
docker-compose -f docker-compose.prod.yml exec django bash
```

---

## 📞 Support Matrix

| Issue | Solution |
|-------|----------|
| Celery task failed | Check logs, verify Redis, check module path |
| Cache miss | Verify Redis running, check TTL |
| Rate limit error | Check API usage log, verify partner token |
| Docker won't start | Check port conflicts, verify .env vars |
| Test fails | Run with -vv flag, check database |

---

**Last Updated**: 19 May 2026  
**Version**: 1.0  
**Status**: ✅ Production Ready
