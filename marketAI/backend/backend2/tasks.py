from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from celery import chain

from backend2.cache import invalidate_cache, ping_redis
from backend2.celery_app import celery_app
from backend2.config import (
    ETL_EXTRACT_SQL_MODULE,
    ETL_IMPORT_MODULE,
    ETL_LOAD_MODULE,
    ETL_TRANSFORM_MODULE,
    ML_REFRESH_MODULE,
)
from backend2.logging_utils import get_logger
from backend2.module_runner import ensure_success, run_python_module, summarize_result
from backend2.webhook import send_webhook_with_retry

logger = get_logger(__name__)


def _run_etl_stage(module_name: str, stage_name: str) -> dict[str, Any]:
    result = run_python_module(module_name)
    summary = summarize_result(result)
    summary["stage_name"] = stage_name

    ensure_success(result)
    logger.info(
        "ETL stage completed",
        extra={
            "event": "etl_stage_success",
            "extra_data": summary,
        },
    )
    return summary


@celery_app.task(
    bind=True,
    name="backend2.tasks.etl_import_marketai_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def etl_import_marketai_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    return _run_etl_stage(ETL_IMPORT_MODULE, "etl_import_marketai")


@celery_app.task(
    bind=True,
    name="backend2.tasks.etl_extract_from_sql_dump_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def etl_extract_from_sql_dump_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    return _run_etl_stage(ETL_EXTRACT_SQL_MODULE, "etl_extract_sql")


@celery_app.task(
    bind=True,
    name="backend2.tasks.etl_transform_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def etl_transform_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    return _run_etl_stage(ETL_TRANSFORM_MODULE, "etl_transform")


@celery_app.task(
    bind=True,
    name="backend2.tasks.etl_load_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def etl_load_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    return _run_etl_stage(ETL_LOAD_MODULE, "etl_load")


@celery_app.task(bind=True, name="backend2.tasks.invalidate_cache_task")
def invalidate_cache_task(
    self,
    previous_result: dict | None = None,
    patterns: list[str] | None = None,
) -> dict[str, Any]:
    summary = invalidate_cache(patterns=patterns)
    payload = {
        "stage_name": "cache_invalidation",
        "cache": summary,
        "previous_stage": previous_result,
    }
    return payload


@celery_app.task(bind=True, name="backend2.tasks.ml_refresh_task")
def ml_refresh_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    if not ML_REFRESH_MODULE:
        payload = {
            "stage_name": "ml_refresh",
            "status": "skipped",
            "reason": "ML_REFRESH_MODULE is not configured",
        }
        logger.info("ML refresh skipped", extra={"event": "ml_refresh_skipped", "extra_data": payload})
        return payload

    return _run_etl_stage(ML_REFRESH_MODULE, "ml_refresh")


@celery_app.task(bind=True, name="backend2.tasks.dispatch_webhook_task")
def dispatch_webhook_task(
    self,
    url: str,
    payload: dict,
    headers: dict | None = None,
) -> dict[str, Any]:
    result = send_webhook_with_retry(url=url, payload=payload, headers=headers)
    if not result.get("success"):
        raise RuntimeError(f"Webhook dispatch failed for {url}: {result}")
    return result


@celery_app.task(bind=True, name="backend2.tasks.system_health_task")
def system_health_task(self) -> dict[str, Any]:
    health = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "redis": ping_redis(),
    }
    logger.info("System health snapshot", extra={"event": "system_health", "extra_data": health})
    return health


@celery_app.task(bind=True, name="backend2.tasks.etl_full_refresh_task")
def etl_full_refresh_task(self, source_mode: str = "marketai") -> dict[str, Any]:
    first = etl_import_marketai_task.s() if source_mode == "marketai" else etl_extract_from_sql_dump_task.s()

    workflow = chain(
        first,
        etl_transform_task.s(),
        etl_load_task.s(),
        invalidate_cache_task.s(),
    )
    async_result = workflow.apply_async()

    payload = {
        "source_mode": source_mode,
        "workflow_id": async_result.id,
    }
    logger.info("ETL workflow started", extra={"event": "etl_workflow_started", "extra_data": payload})
    return payload
