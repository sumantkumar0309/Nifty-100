"""Celery app configuration for ETL refresh and health score scheduling."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

app = Celery("nifty100", broker=BROKER_URL, backend=RESULT_BACKEND)

app.conf.update(
    imports=("orchestration.tasks",),
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_default_queue="nifty100",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "daily-warehouse-refresh-1am": {
            "task": "orchestration.tasks.refresh_warehouse",
            "schedule": crontab(hour=1, minute=0),
        },
        "daily-health-score-2am": {
            "task": "orchestration.tasks.compute_health_scores",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
