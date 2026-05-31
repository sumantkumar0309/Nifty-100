# Runbook

## 1. Prepare environment

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy environment file and update variables:

```bash
copy .env.example .env
```

3. Start PostgreSQL and Redis (local or Docker).

## 2. Full ETL load

1. Extract raw CSVs from SQL dump:

```bash
python etl/01_extract_from_mysql.py --sql-file data/source/scriptticker.sql --output-dir data/raw
```

2. Clean and transform:

```bash
python etl/02_clean_and_transform.py --raw-dir data/raw --clean-dir data/clean --sector-mapping data/sector_mapping.csv
```

3. Load star schema warehouse:

```bash
python etl/03_load_to_warehouse.py --clean-dir data/clean --db-url %DATABASE_URL%
```

4. Compute latest health scores:

```bash
python analytics/health_scoring.py --db-url %DATABASE_URL% --redis-url %REDIS_URL%
```

## 3. Script 4 scheduler usage

1. Run in-process refresh:

```bash
python etl/04_schedule_refresh.py --mode manual --include-scores --db-url %DATABASE_URL%
```

2. Enqueue refresh task (requires worker):

```bash
python etl/04_schedule_refresh.py --mode enqueue --include-scores --db-url %DATABASE_URL%
```

3. Start Celery worker:

```bash
python etl/04_schedule_refresh.py --mode worker
```

4. Start Celery beat scheduler:

```bash
python etl/04_schedule_refresh.py --mode beat
```

## 4. Django web and partner API

1. Apply migrations:

```bash
python django_app/manage.py migrate
```

2. Create admin user:

```bash
python django_app/manage.py createsuperuser
```

3. Run server:

```bash
python django_app/manage.py runserver
```

4. Open API docs:

- Swagger: http://127.0.0.1:8000/api/docs/
- ReDoc: http://127.0.0.1:8000/api/redoc/

## 5. Docker path

```bash
docker compose up --build
```

## 6. Daily schedule reference

- 01:00 AM IST: warehouse refresh (`orchestration.tasks.refresh_warehouse`)
- 02:00 AM IST: health scoring (`orchestration.tasks.compute_health_scores`)
