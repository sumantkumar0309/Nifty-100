# Nifty 100 Financial Intelligence - Data Analyst + ML Stream

This workspace contains the Data Engineering and Analytics foundation used by Backend 1, Backend 2, and Power BI.

## What is implemented

- SQL dump extractor for 7 source tables into `data/raw/`
- marketAI import bridge for pre-cleaned CSV inputs into `data/raw/`
- Cleaning + transformation pipeline into star-schema-ready CSVs in `data/clean/`
- PostgreSQL star schema DDL in `sql/warehouse_schema.sql`
- Idempotent warehouse loader (`ON CONFLICT DO UPDATE`) with data quality checks

## Folder structure

- `etl/01_extract_from_mysql.py`: parse MariaDB SQL dump and create raw CSVs
- `etl/00_import_marketai_data.py`: import `marketAI/data/*.csv` into ETL raw input names
- `etl/02_clean_and_transform.py`: standardize years, clean values, compute metrics, create dims/facts CSVs
- `etl/03_load_to_warehouse.py`: create schema and load/upsert clean CSVs to PostgreSQL
- `marketAI/frontend/project2/`: imported frontend Django project (Person 1 delivery)
- `docs/frontend_backend_handoff.md`: frontend + Backend 2 integration runbook
- `etl/utils/sql_dump_parser.py`: INSERT parser for SQL dump extraction
- `sql/warehouse_schema.sql`: dimensional schema and fact tables
- `data/raw/`: raw extracted CSVs
- `data/clean/`: transformed output CSVs
- `data/sector_mapping.csv`: sector map generated/updated during transform

## Setup

1. Create and activate Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and set values:
   - `NIFTY_SQL_DUMP_PATH`
   - `MARKETAI_DATA_DIR` (only if using marketAI cleaned data)
   - `WAREHOUSE_DB_URL`

4. Ensure PostgreSQL is reachable.

Optional local infra for Backend 2:

```bash
docker compose up -d postgres redis backend2-worker backend2-beat
```

Backend 2 package location:

- `marketAI/backend/backend2/`

## Run order

Option A (using completed marketAI repository dataset):

```bash
python -m etl.00_import_marketai_data
python -m etl.02_clean_and_transform
python -m etl.03_load_to_warehouse
```

Option B (using MariaDB SQL dump):

```bash
python -m etl.01_extract_from_mysql
python -m etl.02_clean_and_transform
python -m etl.03_load_to_warehouse
```

## Notes

- Year formats like `Mar-24`, `Mar 2024`, and `TTM` are normalized during transformation.
- Computed metrics include debt-to-equity, net profit margin, expense ratio, interest coverage, free cash flow, cash conversion ratio, asset turnover, return on assets, equity ratio, and book value per share.
- `data/sector_mapping.csv` is generated from companies and can be manually reviewed to enforce final sector quality.
- The load script is idempotent and safe to run on schedules.
