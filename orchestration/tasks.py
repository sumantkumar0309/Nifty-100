"""Celery tasks for scheduled ETL refresh and health scoring."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

from celery import shared_task

from analytics.health_scoring import run_scoring_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_python_script(script_relative_path: str, args: list[str]) -> str:
    script_path = REPO_ROOT / script_relative_path
    command = [sys.executable, str(script_path), *args]

    process = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if process.returncode != 0:
        output = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(f"{script_relative_path} failed: {output}")

    return process.stdout.strip()


@shared_task(name="orchestration.tasks.refresh_warehouse")
def refresh_warehouse(raw_dir: str = "data/raw", clean_dir: str = "data/clean", db_url: str | None = None) -> Dict[str, object]:
    effective_db_url = db_url or os.getenv("DATABASE_URL")
    if not effective_db_url:
        raise ValueError("DATABASE_URL is required for warehouse load.")

    transform_output = _run_python_script(
        "etl/02_clean_and_transform.py",
        ["--raw-dir", raw_dir, "--clean-dir", clean_dir, "--sector-mapping", "data/sector_mapping.csv"],
    )

    load_output = _run_python_script(
        "etl/03_load_to_warehouse.py",
        ["--clean-dir", clean_dir, "--db-url", effective_db_url],
    )

    return {
        "status": "success",
        "raw_dir": raw_dir,
        "clean_dir": clean_dir,
        "transform_log_tail": transform_output.splitlines()[-5:],
        "load_log_tail": load_output.splitlines()[-5:],
    }


@shared_task(name="orchestration.tasks.compute_health_scores")
def compute_health_scores(
    db_url: str | None = None,
    redis_url: str | None = None,
    output_csv: str = "data/clean/fact_ml_scores.csv",
) -> Dict[str, object]:
    effective_db_url = db_url or os.getenv("DATABASE_URL")
    if not effective_db_url:
        raise ValueError("DATABASE_URL is required for score computation.")

    effective_redis = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return run_scoring_pipeline(
        db_url=effective_db_url,
        redis_url=effective_redis,
        output_csv=output_csv,
    )


@shared_task(name="orchestration.tasks.refresh_and_score")
def refresh_and_score(raw_dir: str = "data/raw", clean_dir: str = "data/clean", db_url: str | None = None) -> Dict[str, object]:
    refresh_result = refresh_warehouse(raw_dir=raw_dir, clean_dir=clean_dir, db_url=db_url)
    score_result = compute_health_scores(db_url=db_url)
    return {
        "refresh": refresh_result,
        "scores": score_result,
    }
