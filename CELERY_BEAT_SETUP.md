# Local Celery Beat Setup Guide

## Overview
Run Celery Beat locally on your machine to schedule background tasks while your Django API runs on Render's free tier (which doesn't support background workers).

---

## Architecture
```
Your Local Machine          →        Render Cloud
┌─────────────────┐                ┌──────────────┐
│ Celery Beat     │─ connects to → │ Redis        │
│ (scheduler)     │                │ (broker)     │
└─────────────────┘                └──────────────┘
                                        ↓
                                   ┌──────────────┐
                                   │ PostgreSQL   │
                                   │ (data)       │
                                   └──────────────┘
```

Celery Beat runs locally and schedules tasks to your **Redis instance on Render**. The tasks execute asynchronously via background processes.

---

## Prerequisites

1. **Render deployment is live** with PostgreSQL, Redis, and Django running
2. **Environment variables** for connecting to Render:
   - `REDIS_URL` (from Render)
   - `DATABASE_URL` (from Render)

---

## Step 1: Install Celery Beat

Your `requirements.txt` should already have `celery` and `redis`. Verify by running:

```bash
pip list | grep celery
pip list | grep redis
```

If missing, install:
```bash
pip install celery redis
```

---

## Step 2: Configure Environment Variables

Create a `.env.celery` file in your project root with Render's credentials:

```bash
# .env.celery
# Get these from Render dashboard → services → PostgreSQL/Redis → Internal Connection String

REDIS_URL=redis://:your_redis_password@your-redis-service.render.com:6379/1
DATABASE_URL=postgresql://user:password@your-postgres-service.render.com:5432/nifty100_warehouse
DJANGO_SETTINGS_MODULE=backend1.settings
DEBUG=false
SECRET_KEY=your-django-secret-key
```

---

## Step 3: Create Celery Beat Schedule Configuration

Edit `marketAI/backend/backend2/celery_app.py`:

```python
from celery import Celery
from celery.schedules import crontab
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend1.settings')

app = Celery('backend2')
app.config_from_object('backend2.config:CeleryConfig')

# Define scheduled tasks
app.conf.beat_schedule = {
    'etl-daily': {
        'task': 'backend2.tasks.run_etl_pipeline',
        'schedule': crontab(hour=1, minute=0),  # 1:00 AM IST
        'options': {'queue': 'default'}
    },
    'ml-scoring-daily': {
        'task': 'backend2.tasks.run_ml_scoring',
        'schedule': crontab(hour=2, minute=0),  # 2:00 AM IST
        'options': {'queue': 'default'}
    },
    'proscons-daily': {
        'task': 'backend2.tasks.run_proscons_generator',
        'schedule': crontab(hour=2, minute=30),  # 2:30 AM IST
        'options': {'queue': 'default'}
    },
    'anomaly-detection-weekly': {
        'task': 'backend2.tasks.run_anomaly_detector',
        'schedule': crontab(day_of_week=6, hour=3, minute=0),  # Sunday 3:00 AM IST
        'options': {'queue': 'default'}
    },
    'trend-analysis-weekly': {
        'task': 'backend2.tasks.run_trend_analyzer',
        'schedule': crontab(day_of_week=6, hour=4, minute=0),  # Sunday 4:00 AM IST
        'options': {'queue': 'default'}
    },
}

app.conf.timezone = 'UTC'  # Or 'Asia/Kolkata' for IST
```

---

## Step 4: Run Celery Beat Locally

Open a terminal in your project root and run:

```bash
# Activate your virtual environment
.venv\Scripts\Activate.ps1

# Set environment variables from .env.celery
# On Windows PowerShell:
Get-Content .env.celery | ForEach-Object {
    if ($_ -match '(.+)=(.+)') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
}

# Run Celery Beat
celery -A backend2 beat --loglevel=info
```

Expected output:
```
celery beat v5.3.1 (opalescence) is starting.
__    ____  _ _
/ /   / __ \/ (_)___/  /
/ /___/ /_/ / / / __  /
\____/\____/_/_/\__,_/

[2026-06-01 10:30:00,123: INFO/MainProcess] celery@HOSTNAME ready.
[2026-06-01 10:30:00,150: INFO/MainProcess] beat: Starting scheduler: scheduler.Scheduler
```

---

## Step 5: Run Worker (Optional - For Local Testing)

If you want to test task execution locally, open **another terminal** and run:

```bash
celery -A backend2 worker --loglevel=info
```

This will consume tasks from Redis and execute them.

---

## Step 6: Monitor Scheduled Tasks

Once Celery Beat is running, check that tasks are scheduled:

```bash
# View Celery tasks (in another terminal)
celery -A backend2 inspect active
celery -A backend2 inspect scheduled
```

Or monitor via Flower (web dashboard):

```bash
pip install flower
celery -A backend2 flower
```

Then visit: `http://localhost:5555`

---

## Troubleshooting

### "Connection refused" error
- **Problem:** Celery can't connect to Render's Redis
- **Solution:** Verify `REDIS_URL` is correct. Test with:
  ```bash
  redis-cli -u your_redis_url ping
  ```

### Tasks not running at scheduled time
- **Problem:** Celery Beat is running but tasks aren't executing
- **Solution:** Start a Celery Worker in another terminal (Step 5)

### "Module not found" error
- **Problem:** Python environment not set up correctly
- **Solution:** Ensure you're in the right directory and virtual environment is activated

---

## Production Considerations

Once you upgrade to a **paid Render plan**, you can:
1. Deploy Celery Beat as a separate service in the Blueprint
2. Remove local Celery Beat
3. No longer need to keep your machine running

For now, keep Celery Beat running locally whenever you need scheduled tasks to execute.

---

## Stopping Celery Beat

Press `Ctrl+C` in the Celery Beat terminal to stop it gracefully.
