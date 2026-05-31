"""Celery integration for Django and ETL orchestration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("b100")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "daily-warehouse-refresh-1am": {
        "task": "orchestration.tasks.refresh_warehouse",
        "schedule": crontab(hour=1, minute=0),
    },
    "daily-health-score-2am": {
        "task": "orchestration.tasks.compute_health_scores",
        "schedule": crontab(hour=2, minute=0),
    },
}
