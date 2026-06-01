# Frontend + Backend 2 Handoff

## Frontend import status

Frontend archive has been extracted at:

- `marketAI/frontend/project2/`

Key frontend pages available:

- Home, About, Reports, Dashboard, Companies, Profile, Settings
- Templates path: `marketAI/frontend/project2/app/templates/app/`

## Run frontend locally

From project root (`Nifty 100`):

```bash
.venv/Scripts/python.exe -m pip install django==5.2.13
.venv/Scripts/python.exe marketAI/frontend/project2/manage.py runserver 8000
```

Frontend URL:

- http://127.0.0.1:8000/

## Run Backend 2 workers

```bash
docker compose up -d postgres redis backend2-worker backend2-beat
```

## Manual ETL trigger

```bash
$env:PYTHONPATH = "$PWD;$PWD/marketAI/backend"
.venv/Scripts/python.exe -m backend2.scripts.trigger_etl --source-mode marketai
```

## Integration contract with Backend Dev 1 APIs

Frontend should consume Backend Dev 1 APIs once available (example route prefixes):

- `/api/v1/companies/`
- `/api/v1/dashboard/summary/`
- `/api/v1/financials/trends/`
- `/api/v1/health-scores/`

Until API completion, frontend can continue with placeholder datasets in Django views.

## Recommended next merge step

Move frontend app from `marketAI/frontend/project2/app/` into the final backend repository app tree after Backend Dev 1 finalizes Django project structure to avoid URL and settings conflicts.
