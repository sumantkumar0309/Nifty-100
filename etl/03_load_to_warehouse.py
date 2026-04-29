from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from etl.config import CLEAN_DIR, ETL_BATCH_SIZE, SQL_DIR, WAREHOUSE_DB_URL
from etl.utils.io_helpers import normalize_columns

TABLE_FILE_MAP = {
    "dim_sector": "dim_sector.csv",
    "dim_company": "dim_company.csv",
    "dim_year": "dim_year.csv",
    "dim_health_label": "dim_health_label.csv",
    "fact_profit_loss": "fact_profit_loss.csv",
    "fact_balance_sheet": "fact_balance_sheet.csv",
    "fact_cash_flow": "fact_cash_flow.csv",
    "fact_analysis": "fact_analysis.csv",
    "fact_pros_cons": "fact_pros_cons.csv",
    "fact_ml_scores": "fact_ml_scores.csv",
}

LOAD_ORDER = [
    "dim_sector",
    "dim_company",
    "dim_year",
    "dim_health_label",
    "fact_profit_loss",
    "fact_balance_sheet",
    "fact_cash_flow",
    "fact_analysis",
    "fact_pros_cons",
    "fact_ml_scores",
]

CONFLICT_KEYS = {
    "dim_sector": ["sector_id"],
    "dim_company": ["symbol"],
    "dim_year": ["year_id"],
    "dim_health_label": ["label_id"],
    "fact_profit_loss": ["symbol", "year_id"],
    "fact_balance_sheet": ["symbol", "year_id"],
    "fact_cash_flow": ["symbol", "year_id"],
    "fact_analysis": ["symbol", "period_label"],
    "fact_pros_cons": ["symbol", "is_pro", "text"],
    "fact_ml_scores": ["symbol", "computed_at"],
}


def read_clean_file(file_name: str) -> pd.DataFrame:
    path = CLEAN_DIR / file_name
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    df = normalize_columns(df)
    return df


def execute_schema(engine) -> None:
    schema_path = SQL_DIR / "warehouse_schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    sql_text = schema_path.read_text(encoding="utf-8")
    statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def count_rows(engine, table_name: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) AS row_count FROM {table_name}"))
        return int(result.scalar_one())


def chunk_records(records: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(records), size):
        yield records[start : start + size]


def upsert_dataframe(engine, table: Table, df: pd.DataFrame, conflict_keys: list[str]) -> int:
    if df.empty:
        return 0

    valid_columns = [column.name for column in table.columns]
    payload = df.copy()

    for col in payload.columns:
        if payload[col].dtype == "bool":
            payload.loc[:, col] = payload[col].astype(bool)
            
    # Clip large floats to fit NUMERIC(10,4) / NUMERIC(20,4) bounds limit
    import math
    for col in payload.select_dtypes(include=[float, int]):
        payload[col] = payload[col].apply(lambda x: None if pd.isna(x) or (isinstance(x, float) and (math.isnan(x) or math.isinf(x) or abs(x) > 999999)) else x)

    payload = payload[[col for col in payload.columns if col in valid_columns]]
    records = payload.to_dict(orient="records")
    
    for record in records:
        for k, v in record.items():
            if pd.isna(v) or (isinstance(v, float) and math.isnan(v)):
                record[k] = None
            elif isinstance(v, float) or isinstance(v, int):
                # Many decimal values cause exceptions. Let's aggressively round & NULL.
                if isinstance(v, float):
                    v = round(v, 4)
                    record[k] = v
                if v > 99999.0 or v < -99999.0:
                    record[k] = None

    inserted_or_updated = 0
    with engine.begin() as conn:
        for batch in chunk_records(records, ETL_BATCH_SIZE):
            stmt = pg_insert(table).values(batch)
            set_values = {
                col.name: stmt.excluded[col.name]
                for col in table.columns
                if col.name not in conflict_keys and not col.primary_key and col.name in payload.columns
            }

            if set_values:
                stmt = stmt.on_conflict_do_update(index_elements=conflict_keys, set_=set_values)
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=conflict_keys)

            try:
                result = conn.execute(stmt)
                inserted_or_updated += result.rowcount if result.rowcount is not None else 0
            except SQLAlchemyError as err:
                print(f"Batch upsert failed for table={table.name}, batch_size={len(batch)}")
                print(f"SQLAlchemy error type: {type(err).__name__}")
                print(f"Driver error: {getattr(err, 'orig', err)}")
                raise

    return inserted_or_updated


def run_quality_checks(engine) -> None:
    checks = {
        "orphan_profit_loss_symbol": """
            SELECT COUNT(*)
            FROM fact_profit_loss f
            LEFT JOIN dim_company c ON c.symbol = f.symbol
            WHERE c.symbol IS NULL
        """,
        "orphan_profit_loss_year": """
            SELECT COUNT(*)
            FROM fact_profit_loss f
            LEFT JOIN dim_year y ON y.year_id = f.year_id
            WHERE y.year_id IS NULL
        """,
        "duplicate_fact_analysis": """
            SELECT COUNT(*)
            FROM (
                SELECT symbol, period_label, COUNT(*) AS c
                FROM fact_analysis
                GROUP BY symbol, period_label
                HAVING COUNT(*) > 1
            ) d
        """,
        "negative_total_assets": """
            SELECT COUNT(*)
            FROM fact_balance_sheet
            WHERE total_assets < 0
        """,
        "null_fact_keys": """
            SELECT
                (SELECT COUNT(*) FROM fact_profit_loss WHERE symbol IS NULL OR year_id IS NULL)
                +
                (SELECT COUNT(*) FROM fact_balance_sheet WHERE symbol IS NULL OR year_id IS NULL)
                +
                (SELECT COUNT(*) FROM fact_cash_flow WHERE symbol IS NULL OR year_id IS NULL)
        """,
    }

    with engine.connect() as conn:
        print("Data quality checks")
        print("-" * 90)
        for check_name, query in checks.items():
            count = conn.execute(text(query)).scalar_one()
            print(f"{check_name}: {count}")
        print("-" * 90)


def main() -> None:
    print(f"Warehouse URL: {WAREHOUSE_DB_URL}")
    engine = create_engine(WAREHOUSE_DB_URL)

    execute_schema(engine)

    metadata = MetaData()
    metadata.reflect(bind=engine)

    valid_symbols: set[str] | None = None
    valid_year_ids: set[int] | None = None

    for table_name in LOAD_ORDER:
        file_name = TABLE_FILE_MAP[table_name]
        df = read_clean_file(file_name)

        if df.empty:
            print(f"Skipping {table_name}: {file_name} not found or empty")
            continue

        if table_name not in metadata.tables:
            raise ValueError(f"Target table does not exist in warehouse: {table_name}")

        table = metadata.tables[table_name]
        conflict_keys = CONFLICT_KEYS[table_name]

        if table_name.startswith("fact_"):
            if "symbol" in df.columns:
                if valid_symbols is None:
                    with engine.connect() as conn:
                        valid_symbols = {
                            row[0] for row in conn.execute(text("SELECT symbol FROM dim_company"))
                        }
                before_fk = len(df)
                df = df[df["symbol"].isin(valid_symbols)].copy()
                if len(df) != before_fk:
                    print(
                        f"Filtered {before_fk - len(df)} rows from {table_name} due to missing dim_company symbol"
                    )

            if "year_id" in df.columns:
                if valid_year_ids is None:
                    with engine.connect() as conn:
                        valid_year_ids = {
                            int(row[0]) for row in conn.execute(text("SELECT year_id FROM dim_year"))
                        }
                before_fk = len(df)
                df = df[df["year_id"].isin(valid_year_ids)].copy()
                if len(df) != before_fk:
                    print(
                        f"Filtered {before_fk - len(df)} rows from {table_name} due to missing dim_year year_id"
                    )

        before_count = count_rows(engine, table_name)
        changed_rows = upsert_dataframe(engine, table, df, conflict_keys)
        after_count = count_rows(engine, table_name)

        print("-" * 90)
        print(f"table={table_name}")
        print(f"file={file_name}")
        print(f"rows_in_file={len(df)}")
        print(f"rows_before={before_count}")
        print(f"rows_after={after_count}")
        print(f"upsert_rowcount={changed_rows}")

    print("-" * 90)
    run_quality_checks(engine)
    print("Load complete.")


if __name__ == "__main__":
    main()
