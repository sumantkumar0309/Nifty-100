from __future__ import annotations

import argparse

from backend2.tasks import etl_full_refresh_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger Backend2 ETL workflow")
    parser.add_argument(
        "--source-mode",
        choices=["marketai", "sql_dump"],
        default="marketai",
        help="Input source mode for ETL extraction stage.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = etl_full_refresh_task.delay(args.source_mode)
    print({"queued": True, "task_id": result.id, "source_mode": args.source_mode})


if __name__ == "__main__":
    main()
