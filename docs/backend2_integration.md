# Backend 2 Integration Contract

This document defines how Backend Developer 2 (Celery, Redis, Docker) should call the Data Analyst + ML pipeline.

## Backend 2 package delivered

- `marketAI/backend/backend2/celery_app.py`
- `marketAI/backend/backend2/tasks.py`
- `marketAI/backend/backend2/cache.py`
- `marketAI/backend/backend2/webhook.py`
- `marketAI/backend/backend2/module_runner.py`
- `marketAI/backend/backend2/scripts/trigger_etl.py`

## Command contract

Run ETL end-to-end in this order:

```bash
python -m etl.00_import_marketai_data
python -m etl.02_clean_and_transform
python -m etl.03_load_to_warehouse
```

Fallback (if using SQL dump source instead of marketAI data):

```bash
python -m etl.01_extract_from_mysql
python -m etl.02_clean_and_transform
python -m etl.03_load_to_warehouse
```

## Suggested Celery tasks

- `etl_extract_task`
  - Calls `etl.00_import_marketai_data` (primary)
- `etl_extract_from_sql_dump_task`
  - Calls `etl.01_extract_from_mysql` (fallback)
- `etl_transform_task`
  - Calls `etl.02_clean_and_transform`
- `etl_load_task`
  - Calls `etl.03_load_to_warehouse`
- `etl_full_refresh_task`
  - Chains extract -> transform -> load
- `invalidate_cache_task`
  - Clears Redis keys by configured patterns after ETL load
- `ml_refresh_task`
  - Optional ML refresh hook (runs only when ML_REFRESH_MODULE is configured)
- `dispatch_webhook_task`
  - Retries outgoing webhooks with backoff
- `system_health_task`
  - Emits health snapshot every 15 minutes

## Suggested schedules

- Daily incremental refresh: 05:30 IST
- Weekly full refresh and data quality report: Sunday 06:00 IST

## Retry and failure policy

- Retry each stage up to 3 times with exponential backoff (e.g., 30s, 120s, 300s).
- On final failure, send alert (email/Slack) with stage name and traceback.
- Do not run transform if extract fails.
- Do not run load if transform fails.

## Cache invalidation policy

After successful `etl_load_task`:

- Invalidate API cache keys for:
  - company profile endpoints
  - financial trend endpoints
  - dashboard summary endpoints

## Monitoring and logging

Track per-run metadata in your app logs:

- start_time
- end_time
- duration_seconds
- stage_name
- status
- rows_processed_per_table
- failed_table_name (if any)

## Environment variables required

- `WAREHOUSE_DB_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CACHE_PATTERNS`
- `ML_REFRESH_MODULE` (optional)

Use template: `marketAI/backend/.env.backend2.example`

## Docker notes

- Start local dependencies:

```bash
docker compose up -d postgres redis backend2-worker backend2-beat
```

- Mount dump file location into app container.
- Keep PostgreSQL and Redis healthy before launching ETL tasks.
- Ensure timezone set to `Asia/Kolkata` for scheduler containers.

Manual trigger from shell:

```bash
python -m backend2.scripts.trigger_etl --source-mode marketai
```
