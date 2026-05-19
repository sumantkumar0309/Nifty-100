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
    "run-etl-pipeline-daily": {
        "task": "backend2.tasks.run_etl_pipeline_task",
        "schedule": crontab(hour=1, minute=0),
    },
    "score-all-companies-daily": {
        "task": "backend2.tasks.score_all_companies_task",
        "schedule": crontab(hour=2, minute=0),
    },
    "generate-pros-cons-daily": {
        "task": "backend2.tasks.generate_pros_cons_task",
        "schedule": crontab(hour=2, minute=30),
    },
    "detect-anomalies-weekly": {
        "task": "backend2.tasks.detect_anomalies_task",
        "schedule": crontab(day_of_week="sun", hour=3, minute=0),
    },
    "detect-trends-weekly": {
        "task": "backend2.tasks.detect_trends_task",
        "schedule": crontab(day_of_week="sun", hour=4, minute=0),
    },
    "backend2-system-health-ping": {
        "task": "backend2.tasks.system_health_task",
        "schedule": crontab(minute="*/15"),
    },
}

celery_app.autodiscover_tasks(["backend2"])
