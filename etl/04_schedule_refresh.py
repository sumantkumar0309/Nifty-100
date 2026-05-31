#!/usr/bin/env python3
"""Script 4: Trigger ETL refresh and scheduling flows via Celery."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestration.tasks import compute_health_scores, refresh_and_score, refresh_warehouse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["manual", "enqueue", "worker", "beat"],
        default="manual",
        help="manual: run tasks in-process, enqueue: send to Celery, worker/beat: start Celery services.",
    )
    parser.add_argument("--raw-dir", default="data/raw", help="Raw CSV directory.")
    parser.add_argument("--clean-dir", default="data/clean", help="Clean CSV directory.")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL SQLAlchemy URL.")
    parser.add_argument("--include-scores", action="store_true", help="Also compute ML health scores.")
    parser.add_argument("--loglevel", default="info", help="Celery log level for worker/beat modes.")
    return parser.parse_args()


def run_celery_process(process_type: str, loglevel: str) -> int:
    command = ["celery", "-A", "orchestration.celery_app", process_type, "-l", loglevel]
    process = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return process.returncode


def main() -> None:
    args = parse_args()

    if args.mode in {"manual", "enqueue"} and not args.db_url:
        raise ValueError("Database URL is required. Pass --db-url or set DATABASE_URL.")

    if args.mode == "manual":
        if args.include_scores:
            result = refresh_and_score.run(raw_dir=args.raw_dir, clean_dir=args.clean_dir, db_url=args.db_url)
        else:
            result = refresh_warehouse.run(raw_dir=args.raw_dir, clean_dir=args.clean_dir, db_url=args.db_url)
        print("[manual]", result)
        return

    if args.mode == "enqueue":
        if args.include_scores:
            task = refresh_and_score.delay(raw_dir=args.raw_dir, clean_dir=args.clean_dir, db_url=args.db_url)
        else:
            task = refresh_warehouse.delay(raw_dir=args.raw_dir, clean_dir=args.clean_dir, db_url=args.db_url)
        print("[enqueue] task_id=", task.id)
        return

    if args.mode == "worker":
        raise SystemExit(run_celery_process("worker", args.loglevel))

    if args.mode == "beat":
        raise SystemExit(run_celery_process("beat", args.loglevel))


if __name__ == "__main__":
    main()
