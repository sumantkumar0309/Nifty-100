from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from backend2.config import CELERY_BEAT_CRON, CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_TIMEZONE
from backend2.logging_utils import configure_logging

configure_logging()

celery_app = Celery(
    "backend2",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=CELERY_TIMEZONE,
    enable_utc=False,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "etl-daily-refresh": {
        "task": "backend2.tasks.etl_full_refresh_task",
        "schedule": crontab(hour=CELERY_BEAT_CRON["etl_daily_hour"], minute=CELERY_BEAT_CRON["etl_daily_minute"]),
        "args": ("marketai",),
    },
    "etl-weekly-full-quality-run": {
        "task": "backend2.tasks.etl_full_refresh_task",
        "schedule": crontab(
            day_of_week=CELERY_BEAT_CRON["etl_weekly_day_of_week"],
            hour=CELERY_BEAT_CRON["etl_weekly_hour"],
            minute=CELERY_BEAT_CRON["etl_weekly_minute"],
        ),
        "args": ("marketai",),
    },
    "backend2-system-health-ping": {
        "task": "backend2.tasks.system_health_task",
        "schedule": crontab(minute="*/15"),
    },
}

celery_app.autodiscover_tasks(["backend2"])
