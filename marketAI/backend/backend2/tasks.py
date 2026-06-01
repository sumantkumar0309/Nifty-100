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


@celery_app.task(
    bind=True,
    name="backend2.tasks.run_etl_pipeline_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_etl_pipeline_task(self) -> dict[str, Any]:
    """
    Daily 1:00 AM — Run ETL scripts 2 and 3 (clean, transform, and load to warehouse).
    """
    workflow = chain(
        etl_transform_task.s(),
        etl_load_task.s(),
        invalidate_cache_task.s(patterns=["company_profile:*", "financial_trend:*"]),
    )
    async_result = workflow.apply_async()

    payload = {
        "stage_name": "run_etl_pipeline",
        "workflow_id": async_result.id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    logger.info("ETL pipeline task started", extra={"event": "etl_pipeline_started", "extra_data": payload})
    return payload


@celery_app.task(
    bind=True,
    name="backend2.tasks.score_all_companies_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def score_all_companies_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    """
    Daily 2:00 AM — Recalculate health scores for all 100 companies.
    Runs ML scoring module to compute overall_score, profitability, growth, leverage, cashflow, dividend scores.
    """
    result = _run_etl_stage(ML_REFRESH_MODULE, "score_all_companies")
    
    payload = {
        "stage_name": "score_all_companies",
        "previous_result": previous_result,
        "ml_result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    logger.info("Company scoring completed", extra={"event": "companies_scored", "extra_data": payload})
    return payload


@celery_app.task(
    bind=True,
    name="backend2.tasks.generate_pros_cons_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_pros_cons_task(self, previous_result: dict | None = None) -> dict[str, Any]:
    """
    Daily 2:30 AM — Re-run pros/cons rule engine for all companies.
    Uses fact_ml_scores and fact tables to generate pro/con statements based on financial metrics.
    """
    try:
        from etl.proscons_generator import generate_all_pros_cons
        
        result = generate_all_pros_cons()
        
        payload = {
            "stage_name": "generate_pros_cons",
            "companies_processed": result.get("count", 0),
            "pros_generated": result.get("pros_count", 0),
            "cons_generated": result.get("cons_count", 0),
            "previous_result": previous_result,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        logger.info("Pros/cons generation completed", extra={"event": "pros_cons_generated", "extra_data": payload})
        return payload
    except Exception as e:
        logger.error(f"Pros/cons generation failed: {str(e)}", extra={"event": "pros_cons_failed"})
        raise


@celery_app.task(
    bind=True,
    name="backend2.tasks.detect_anomalies_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def detect_anomalies_task(self) -> dict[str, Any]:
    """
    Weekly Sunday 3:00 AM — Z-score anomaly detection across all fact tables.
    Detects unusual financial patterns in: sales, net_profit, borrowings, operating_profit across years per company.
    Also applies Isolation Forest for comparison.
    """
    try:
        from etl.anomaly_detector import detect_anomalies_zscore, detect_anomalies_isolation_forest
        
        zscore_results = detect_anomalies_zscore()
        isolation_results = detect_anomalies_isolation_forest()
        
        payload = {
            "stage_name": "detect_anomalies",
            "zscore_anomalies_found": zscore_results.get("count", 0),
            "isolation_anomalies_found": isolation_results.get("count", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        logger.info("Anomaly detection completed", extra={"event": "anomalies_detected", "extra_data": payload})
        return payload
    except Exception as e:
        logger.error(f"Anomaly detection failed: {str(e)}", extra={"event": "anomaly_detection_failed"})
        raise


@celery_app.task(
    bind=True,
    name="backend2.tasks.detect_trends_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def detect_trends_task(self) -> dict[str, Any]:
    """
    Weekly Sunday 4:00 AM — Linear regression trend analysis for all companies.
    Classifies trend as UP/FLAT/DOWN based on 5-year historical data.
    For top 20 companies, fits ARIMA/Holt-Winters for revenue forecasting.
    """
    try:
        from etl.trend_analyzer import analyze_trends, forecast_top_companies
        
        trends = analyze_trends()
        forecasts = forecast_top_companies()
        
        payload = {
            "stage_name": "detect_trends",
            "companies_analyzed": trends.get("count", 0),
            "up_trend": trends.get("up_count", 0),
            "flat_trend": trends.get("flat_count", 0),
            "down_trend": trends.get("down_count", 0),
            "top_20_forecasted": forecasts.get("count", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        logger.info("Trend detection completed", extra={"event": "trends_detected", "extra_data": payload})
        return payload
    except Exception as e:
        logger.error(f"Trend detection failed: {str(e)}", extra={"event": "trend_detection_failed"})
        raise
