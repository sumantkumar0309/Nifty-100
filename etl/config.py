from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
SQL_DIR = BASE_DIR / "sql"
SOURCE_DIR = DATA_DIR / "source"
MARKETAI_DATA_DIR = Path(os.getenv("MARKETAI_DATA_DIR", BASE_DIR / "marketAI" / "data")).resolve()

SQL_DUMP_PATH = Path(os.getenv("NIFTY_SQL_DUMP_PATH", SOURCE_DIR / "scriptticker.sql")).resolve()
WAREHOUSE_DB_URL = os.getenv(
    "WAREHOUSE_DB_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/nifty100",
)
ETL_BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "1000"))

RAW_TABLES = [
    "companies",
    "analysis",
    "balancesheet",
    "profitandloss",
    "cashflow",
    "prosandcons",
    "documents",
]


def ensure_data_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
