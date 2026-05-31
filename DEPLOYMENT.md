# Production Deployment Guide

This guide walks through deploying the Nifty 100 Financial Intelligence Platform to production using Docker Compose.

## Prerequisites

- Docker & Docker Compose (3.9+)
- Linux server (Ubuntu 20.04+ recommended)
- PostgreSQL 15, Redis 7 (included in Docker)
- SSL/TLS certificate (self-signed or Let's Encrypt)
- 2 GB RAM minimum, 4 GB recommended

## Step 1: Prepare Server

```bash
# SSH into your production server
ssh user@your-server.com

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

## Step 2: Clone Repository

```bash
# Clone your repository
git clone https://github.com/your-org/nifty-100.git
cd nifty-100

# Create necessary directories
mkdir -p docker/ssl logs/django logs/celery logs/nginx
```

## Step 3: Generate SSL Certificates

### Option A: Self-Signed (Development/Testing)

```bash
cd docker/ssl

# Generate self-signed certificate (valid 365 days)
openssl req -x509 -newkey rsa:4096 -nodes \
  -out cert.pem \
  -keyout key.pem \
  -days 365 \
  -subj "/C=IN/ST=State/L=City/O=Organization/CN=your-domain.com"

cd ../..
```

### Option B: Let's Encrypt (Production)

```bash
# Install Certbot
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Generate certificate (replace your-domain.com)
sudo certbot certonly \
  --standalone \
  -d your-domain.com \
  -d www.your-domain.com

# Copy certificates to docker/ssl
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem docker/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem docker/ssl/key.pem
sudo chown $USER:$USER docker/ssl/*

# Auto-renew (Certbot handles this automatically)
```

## Step 4: Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with production values
nano .env
```

**Critical environment variables** (CHANGE THESE):

```env
# Django
DEBUG=false
DJANGO_SECRET_KEY=your-very-long-random-secret-key-change-this
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Database
DB_PASSWORD=strong_postgres_password_change_this
DB_NAME=nifty100_warehouse

# Redis
REDIS_PASSWORD=strong_redis_password_change_this

# Celery
CELERY_TIMEZONE=Asia/Kolkata

# CORS
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com

# Nginx
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443
```

## Step 5: Initialize Database Schema

Create `sql/warehouse_schema.sql` with your star schema tables:

```sql
-- Dimension tables
CREATE TABLE IF NOT EXISTS dim_company (
  company_id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) UNIQUE NOT NULL,
  company_name VARCHAR(255) NOT NULL,
  sector VARCHAR(100),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_year (
  year_id SERIAL PRIMARY KEY,
  fiscal_year INT UNIQUE NOT NULL
);

-- Fact tables (example)
CREATE TABLE IF NOT EXISTS fact_profit_loss (
  pl_id SERIAL PRIMARY KEY,
  company_id INT REFERENCES dim_company(company_id),
  fiscal_year INT REFERENCES dim_year(year_id),
  revenue FLOAT,
  net_profit FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partner API tables
CREATE TABLE IF NOT EXISTS partner_api_tokens (
  id SERIAL PRIMARY KEY,
  partner_id VARCHAR(100),
  partner_name VARCHAR(255),
  token_hash VARCHAR(64) UNIQUE NOT NULL,
  secret_hash VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP,
  is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS api_usage_log (
  id SERIAL PRIMARY KEY,
  partner_id VARCHAR(100),
  endpoint VARCHAR(255),
  method VARCHAR(10),
  response_status INT,
  response_time_ms FLOAT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analytics tables
CREATE TABLE IF NOT EXISTS fact_pros_cons (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES dim_company(company_id),
  company_name VARCHAR(255),
  statement TEXT,
  type VARCHAR(10),  -- 'pro' or 'con'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_anomaly_flags (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES dim_company(company_id),
  company_name VARCHAR(255),
  fiscal_year INT,
  anomaly_type VARCHAR(50),
  metric VARCHAR(50),
  severity VARCHAR(20),
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_trend_analysis (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES dim_company(company_id),
  company_name VARCHAR(255),
  trend_class VARCHAR(10),  -- UP, FLAT, DOWN
  slope FLOAT,
  r_squared FLOAT,
  p_value FLOAT,
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_revenue_forecast (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES dim_company(company_id),
  company_name VARCHAR(255),
  forecast_year INT,
  forecast_revenue FLOAT,
  confidence_lower FLOAT,
  confidence_upper FLOAT,
  model VARCHAR(100),
  forecasted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_company_symbol ON dim_company(symbol);
CREATE INDEX idx_profit_loss_company_year ON fact_profit_loss(company_id, fiscal_year);
CREATE INDEX idx_api_usage_partner_timestamp ON api_usage_log(partner_id, timestamp);
CREATE INDEX idx_anomaly_flags_company_year ON fact_anomaly_flags(company_id, fiscal_year);
```

## Step 6: Build & Start Services

```bash
# Pull latest images and build
docker-compose -f docker-compose.prod.yml build

# Start all services in background
docker-compose -f docker-compose.prod.yml up -d

# Verify services are running
docker-compose -f docker-compose.prod.yml ps

# Expected output (all HEALTHY):
# nifty100_postgres    Up  (healthy)
# nifty100_redis       Up  (healthy)
# nifty100_django      Up  (healthy)
# nifty100_celery_worker  Up
# nifty100_celery_beat Up
# nifty100_nginx       Up  (healthy)
```

## Step 7: Initialize Django

```bash
# Run database migrations
docker-compose -f docker-compose.prod.yml exec -T django python manage.py migrate

# Collect static files
docker-compose -f docker-compose.prod.yml exec -T django python manage.py collectstatic --noinput

# Create superuser (follow prompts)
docker-compose -f docker-compose.prod.yml exec django python manage.py createsuperuser

# Test health endpoint
curl https://your-domain.com/health/
```

## Step 8: Verify Celery Tasks

```bash
# Check Celery worker logs
docker-compose -f docker-compose.prod.yml logs celery_worker

# Check Celery beat logs
docker-compose -f docker-compose.prod.yml logs celery_beat

# Verify beat schedule is active
docker-compose -f docker-compose.prod.yml exec celery_beat celery -A orchestration.backend2.celery_app inspect scheduled

# Expected output: 6 scheduled tasks
```

## Step 9: Load Initial Data

```bash
# Copy your SQL dump
cp /path/to/scriptticker.sql data/source/

# Run ETL inside Django container
docker-compose -f docker-compose.prod.yml exec django python -c "
import os
os.chdir('/app')
exec(open('etl/01_extract_from_mysql.py').read())
exec(open('etl/02_clean_and_transform.py').read())
exec(open('etl/03_load_to_warehouse.py').read())
"

# Or run ETL via Celery task
docker-compose -f docker-compose.prod.yml exec django python manage.py shell
>>> from orchestration.backend2.tasks import run_etl_pipeline_task
>>> run_etl_pipeline_task.delay()
```

## Monitoring & Maintenance

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f django
docker-compose -f docker-compose.prod.yml logs -f celery_worker
docker-compose -f docker-compose.prod.yml logs -f nginx

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail 100 django
```

### Database Backups

```bash
# Create backup
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U nifty100 nifty100_warehouse > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
docker-compose -f docker-compose.prod.yml exec -T postgres psql -U nifty100 nifty100_warehouse < backup_20260530_120000.sql
```

### Scale Celery Workers

```bash
# Edit docker-compose.prod.yml and increase --concurrency
# Then restart
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d celery_worker
```

### Update & Redeploy

```bash
# Pull latest code
git pull origin main

# Rebuild images
docker-compose -f docker-compose.prod.yml build

# Restart services with zero downtime
docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml exec -T django python manage.py migrate
```

### Health Checks

```bash
# Django
curl https://your-domain.com/health/

# API documentation
curl https://your-domain.com/api/docs/

# Check all containers
docker-compose -f docker-compose.prod.yml ps

# Check resource usage
docker stats
```

## Troubleshooting

### Services not starting
```bash
# Check error logs
docker-compose -f docker-compose.prod.yml logs django

# Rebuild images
docker-compose -f docker-compose.prod.yml build --no-cache

# Restart all services
docker-compose -f docker-compose.prod.yml restart
```

### PostgreSQL connection errors
```bash
# Verify PostgreSQL is healthy
docker-compose -f docker-compose.prod.yml exec postgres pg_isready

# Check credentials in .env
cat .env | grep DB_

# Verify DATABASE_URL in Django container
docker-compose -f docker-compose.prod.yml exec django python -c "import os; print(os.getenv('DATABASE_URL'))"
```

### Redis connection errors
```bash
# Test Redis connection
docker-compose -f docker-compose.prod.yml exec redis redis-cli -a $(grep REDIS_PASSWORD .env | cut -d= -f2) ping

# Clear Redis cache
docker-compose -f docker-compose.prod.yml exec redis redis-cli -a $(grep REDIS_PASSWORD .env | cut -d= -f2) FLUSHALL
```

### Celery tasks not running
```bash
# Check beat schedule
docker-compose -f docker-compose.prod.yml exec celery_beat celery -A orchestration.backend2.celery_app inspect scheduled

# Check active workers
docker-compose -f docker-compose.prod.yml exec celery_beat celery -A orchestration.backend2.celery_app inspect active

# Restart beat scheduler
docker-compose -f docker-compose.prod.yml restart celery_beat
```

## Performance Tuning

### Celery Worker Concurrency
Edit `docker-compose.prod.yml` and adjust:
```yaml
command: celery -A orchestration.backend2.celery_app worker -l info --concurrency=8 --max-tasks-per-child=500
```

### Gunicorn Workers
Edit `docker-compose.prod.yml` Django service:
```yaml
command: gunicorn django_app.config.wsgi:application --bind 0.0.0.0:8000 --workers 8 --worker-class sync --timeout 120
```

### PostgreSQL Connection Pool
Edit `orchestration/backend2/config.py`:
```python
SQLALCHEMY_POOL_SIZE = 20
SQLALCHEMY_MAX_OVERFLOW = 10
```

## Security Checklist

- [ ] Changed `DJANGO_SECRET_KEY` in .env
- [ ] Changed database password
- [ ] Changed Redis password
- [ ] SSL/TLS certificate installed
- [ ] ALLOWED_HOSTS configured correctly
- [ ] CORS_ALLOWED_ORIGINS set to your frontend domain
- [ ] DEBUG=false in production
- [ ] GitHub Actions secrets configured (DOCKER_USERNAME, DOCKER_PASSWORD, DEPLOY_KEY, etc.)
- [ ] Regular backups scheduled
- [ ] Rate limiting configured for APIs
- [ ] Security headers validated in Nginx
- [ ] Firewall rules configured (only allow 80, 443, SSH)

## Scaling for High Traffic

1. **Add more Celery workers**: Scale to multiple machines behind load balancer
2. **Database read replicas**: PostgreSQL streaming replication
3. **Redis cluster**: Multiple Redis instances for HA
4. **CDN**: CloudFlare or similar for static assets
5. **Kubernetes**: Migrate to K8s for auto-scaling

## Support & Documentation

- Docker Compose: https://docs.docker.com/compose/
- Celery: https://docs.celeryproject.io/
- Django: https://docs.djangoproject.com/
- PostgreSQL: https://www.postgresql.org/docs/
- Nginx: https://nginx.org/en/docs/
