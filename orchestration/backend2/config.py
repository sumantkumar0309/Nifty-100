"""Backend2 Configuration - Load environment variables and set defaults"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND2_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BACKEND2_DIR.parent.parent
PROJECT_ROOT = BACKEND_DIR

PYTHON_EXECUTABLE = os.getenv("PYTHON_EXECUTABLE", "python")

# Redis & Celery Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", "Asia/Kolkata")

# ETL Module Configuration
ETL_IMPORT_MODULE = os.getenv("ETL_IMPORT_MODULE", "etl.00_import_marketai_data")
ETL_EXTRACT_SQL_MODULE = os.getenv("ETL_EXTRACT_SQL_MODULE", "etl.01_extract_from_mysql")
ETL_TRANSFORM_MODULE = os.getenv("ETL_TRANSFORM_MODULE", "etl.02_clean_and_transform")
ETL_LOAD_MODULE = os.getenv("ETL_LOAD_MODULE", "etl.03_load_to_warehouse")
ML_REFRESH_MODULE = os.getenv("ML_REFRESH_MODULE", "etl.04_generate_ml_scores")

# Webhook Configuration
WEBHOOK_TIMEOUT_SECONDS = int(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "20"))
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "3"))
WEBHOOK_BACKOFF_SECONDS = int(os.getenv("WEBHOOK_BACKOFF_SECONDS", "30"))

# Cache Configuration
CACHE_PATTERNS = [
    x.strip()
    for x in os.getenv(
        "CACHE_PATTERNS",
        "company_profile:*,financial_trend:*,dashboard_summary:*",
    ).split(",")
    if x.strip()
]

# Logging Configuration
DEFAULT_LOG_LEVEL = os.getenv("BACKEND2_LOG_LEVEL", "INFO")
LOG_FILE_PATH = Path(os.getenv("BACKEND2_LOG_FILE", BACKEND2_DIR / "logs" / "backend2.log"))

# Celery Beat Schedule Configuration
CELERY_BEAT_CRON = {
    "etl_daily_hour": int(os.getenv("ETL_DAILY_HOUR", "1")),
    "etl_daily_minute": int(os.getenv("ETL_DAILY_MINUTE", "0")),
    "etl_weekly_day_of_week": os.getenv("ETL_WEEKLY_DAY_OF_WEEK", "sun"),
    "etl_weekly_hour": int(os.getenv("ETL_WEEKLY_HOUR", "3")),
    "etl_weekly_minute": int(os.getenv("ETL_WEEKLY_MINUTE", "0")),
}
