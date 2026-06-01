# Backend 2 Orchestration Package

This package provides Celery-based orchestration for ETL runs, cache invalidation, webhook retries, and health monitoring.

## Files

- `celery_app.py`: Celery app and beat schedule
- `tasks.py`: ETL, cache, webhook, health tasks
- `module_runner.py`: Runs ETL python modules as subprocesses
- `cache.py`: Redis cache invalidation helpers
- `webhook.py`: Retry-aware webhook sender
- `scripts/trigger_etl.py`: Manual ETL workflow trigger

## Frontend handoff

Imported frontend project is available at:

- `marketAI/frontend/project2/`

Integration notes are documented in:

- `docs/frontend_backend_handoff.md`

## Local run

From project root (`Nifty 100`):

```bash
docker compose up -d postgres redis backend2-worker backend2-beat
```

To trigger manually:

```bash
PYTHONPATH=.\marketAI\backend;. & .venv/Scripts/python.exe -m backend2.scripts.trigger_etl --source-mode marketai
```

## Source modes

- `marketai`: uses completed `marketAI/data` CSV source
- `sql_dump`: uses SQL dump extraction module
