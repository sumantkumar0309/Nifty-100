from __future__ import annotations

from pathlib import Path

import pandas as pd

from etl.config import RAW_DIR, RAW_TABLES, SQL_DUMP_PATH, ensure_data_dirs
from etl.utils.io_helpers import normalize_columns
from etl.utils.sql_dump_parser import parse_sql_dump


def coerce_rows_to_columns(rows: list[list[object]], column_count: int) -> list[list[object]]:
    adjusted_rows = []
    for row in rows:
        if len(row) < column_count:
            row = row + [None] * (column_count - len(row))
        elif len(row) > column_count:
            row = row[:column_count]
        adjusted_rows.append(row)
    return adjusted_rows


def write_table_csv(table_name: str, rows: list[list[object]], columns: list[str] | None) -> Path:
    if not rows:
        df = pd.DataFrame(columns=columns or [])
    else:
        if not columns:
            width = max(len(r) for r in rows)
            columns = [f"col_{i + 1}" for i in range(width)]

        adjusted_rows = coerce_rows_to_columns(rows, len(columns))
        df = pd.DataFrame(adjusted_rows, columns=columns)

    df = normalize_columns(df)
    output_path = RAW_DIR / f"{table_name}.csv"
    df.to_csv(output_path, index=False)
    return output_path


def main() -> None:
    ensure_data_dirs()

    if not SQL_DUMP_PATH.exists():
        raise FileNotFoundError(
            f"SQL dump not found at {SQL_DUMP_PATH}. "
            "Set NIFTY_SQL_DUMP_PATH or place the file at data/source/scriptticker.sql"
        )

    sql_text = SQL_DUMP_PATH.read_text(encoding="utf-8", errors="replace")
    parsed = parse_sql_dump(sql_text, target_tables=set(RAW_TABLES))

    print(f"Input SQL dump: {SQL_DUMP_PATH}")
    print(f"Target output directory: {RAW_DIR}")

    for table in RAW_TABLES:
        table_data = parsed.get(table)
        rows = table_data.rows if table_data else []
        columns = table_data.columns if table_data else None

        output_path = write_table_csv(table, rows, columns)

        if rows:
            col_list = columns if columns else [f"col_{i + 1}" for i in range(max(len(r) for r in rows))]
        else:
            col_list = columns or []

        print("-" * 90)
        print(f"table={table}")
        print(f"rows={len(rows)}")
        print(f"columns={col_list}")
        print(f"csv={output_path}")

    print("-" * 90)
    print("Extraction complete.")


if __name__ == "__main__":
    main()
