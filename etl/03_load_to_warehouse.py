#!/usr/bin/env python3
"""Load cleaned Nifty 100 data into a PostgreSQL star-schema warehouse."""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-dir", default="data/clean", help="Directory containing cleaned CSV files.")
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL SQLAlchemy URL. Falls back to DATABASE_URL environment variable.",
    )
    return parser.parse_args()


def load_csv_if_exists(base_dir: Path, table_name: str) -> pd.DataFrame:
    path = base_dir / f"{table_name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def to_numeric(series: pd.Series) -> pd.Series:
    normalized = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("₹", "", regex=False)
        .str.replace("Rs.", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(normalized, errors="coerce")


def to_bool(series: pd.Series) -> pd.Series:
    bool_map = {
        "1": True,
        "0": False,
        "true": True,
        "false": False,
        "yes": True,
        "no": False,
    }
    return series.map(lambda v: bool_map.get(str(v).strip().lower(), np.nan))


def first_existing(df: pd.DataFrame, options: Sequence[str]) -> Optional[str]:
    for col in options:
        if col in df.columns:
            return col
    return None


def ensure_symbol(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    source = first_existing(out, ["symbol", "company_id", "ticker", "code"])
    if source and source != "symbol":
        out["symbol"] = out[source]
    if "symbol" in out.columns:
        out["symbol"] = out["symbol"].map(lambda v: v.upper().strip() if isinstance(v, str) else v)
    return out


def map_year_id(df: pd.DataFrame, year_lookup: Dict[str, int], fiscal_lookup: Dict[int, int]) -> pd.DataFrame:
    out = df.copy()

    if "year_id" in out.columns:
        out["year_id"] = pd.to_numeric(out["year_id"], errors="coerce")
    elif "year_label" in out.columns:
        out["year_id"] = out["year_label"].map(year_lookup)
    elif "fiscal_year" in out.columns:
        out["fiscal_year"] = pd.to_numeric(out["fiscal_year"], errors="coerce")
        out["year_id"] = out["fiscal_year"].map(fiscal_lookup)
    else:
        out["year_id"] = np.nan

    out["year_id"] = pd.to_numeric(out["year_id"], errors="coerce")
    return out


def assign_health_label_from_score(score: float) -> str:
    if pd.isna(score):
        return "POOR"
    if score >= 85:
        return "EXCELLENT"
    if score >= 70:
        return "GOOD"
    if score >= 50:
        return "AVERAGE"
    if score >= 35:
        return "WEAK"
    return "POOR"


def split_insights(raw_text: object) -> List[str]:
    if pd.isna(raw_text):
        return []
    text = str(raw_text).strip()
    if not text:
        return []
    chunks = re.split(r"\s*[;|]\s*|\s*\n\s*", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def table_count(conn: Connection, table: Table) -> int:
    return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def upsert_dataframe(conn: Connection, table: Table, df: pd.DataFrame, conflict_cols: Sequence[str]) -> None:
    if df.empty:
        before_count = table_count(conn, table)
        print(f"[{table.name}] incoming=0 before={before_count} after={before_count}")
        return

    work = df.copy()
    work = work.dropna(subset=[col for col in conflict_cols if col in work.columns])
    if work.empty:
        before_count = table_count(conn, table)
        print(f"[{table.name}] incoming=0 before={before_count} after={before_count}")
        return

    work = work.drop_duplicates(subset=list(conflict_cols), keep="last")
    work = work.where(pd.notnull(work), None)

    valid_columns = [col.name for col in table.columns if col.name in work.columns]
    payload = work[valid_columns].to_dict(orient="records")

    before_count = table_count(conn, table)

    stmt = pg_insert(table).values(payload)
    update_cols = [
        col.name
        for col in table.columns
        if col.name not in conflict_cols and not col.primary_key and col.name in work.columns
    ]
    update_mapping = {col: getattr(stmt.excluded, col) for col in update_cols}
    stmt = stmt.on_conflict_do_update(index_elements=list(conflict_cols), set_=update_mapping)

    conn.execute(stmt)

    after_count = table_count(conn, table)
    print(f"[{table.name}] incoming={len(payload)} before={before_count} after={after_count}")


def define_schema(metadata: MetaData) -> Dict[str, Table]:
    dim_sector = Table(
        "dim_sector",
        metadata,
        Column("sector_id", Integer, primary_key=True, autoincrement=True),
        Column("sector_name", String(100), unique=True, nullable=False),
        Column("sector_code", String(20), nullable=False),
        Column("description", Text),
    )

    dim_company = Table(
        "dim_company",
        metadata,
        Column("symbol", String(20), primary_key=True),
        Column("company_name", String(255)),
        Column("sector_id", Integer, ForeignKey("dim_sector.sector_id")),
        Column("sector", String(100)),
        Column("sub_sector", String(100)),
        Column("company_logo", Text),
        Column("website", Text),
        Column("nse_url", Text),
        Column("bse_url", Text),
        Column("face_value", Float),
        Column("book_value", Float),
        Column("about_company", Text),
    )

    dim_year = Table(
        "dim_year",
        metadata,
        Column("year_id", Integer, primary_key=True),
        Column("year_label", String(20), unique=True, nullable=False),
        Column("fiscal_year", Integer),
        Column("quarter", String(2)),
        Column("is_ttm", Boolean),
        Column("is_half_year", Boolean),
        Column("sort_order", Integer),
    )

    dim_health_label = Table(
        "dim_health_label",
        metadata,
        Column("label_id", Integer, primary_key=True),
        Column("label_name", String(20), unique=True, nullable=False),
        Column("min_score", Float),
        Column("max_score", Float),
        Column("color_hex", String(7)),
    )

    fact_profit_loss = Table(
        "fact_profit_loss",
        metadata,
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("year_id", Integer, ForeignKey("dim_year.year_id"), nullable=False),
        Column("sales", Float),
        Column("expenses", Float),
        Column("operating_profit", Float),
        Column("opm_pct", Float),
        Column("other_income", Float),
        Column("interest", Float),
        Column("depreciation", Float),
        Column("profit_before_tax", Float),
        Column("tax_pct", Float),
        Column("net_profit", Float),
        Column("eps", Float),
        Column("dividend_payout_pct", Float),
        Column("net_profit_margin_pct", Float),
        Column("expense_ratio_pct", Float),
        Column("interest_coverage", Float),
        Column("asset_turnover", Float),
        Column("return_on_assets", Float),
        PrimaryKeyConstraint("symbol", "year_id", name="pk_fact_profit_loss"),
    )

    fact_balance_sheet = Table(
        "fact_balance_sheet",
        metadata,
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("year_id", Integer, ForeignKey("dim_year.year_id"), nullable=False),
        Column("equity_capital", Float),
        Column("reserves", Float),
        Column("borrowings", Float),
        Column("other_liabilities", Float),
        Column("total_liabilities", Float),
        Column("fixed_assets", Float),
        Column("cwip", Float),
        Column("investments", Float),
        Column("other_assets", Float),
        Column("total_assets", Float),
        Column("debt_to_equity", Float),
        Column("equity_ratio", Float),
        Column("book_value_per_share", Float),
        PrimaryKeyConstraint("symbol", "year_id", name="pk_fact_balance_sheet"),
    )

    fact_cash_flow = Table(
        "fact_cash_flow",
        metadata,
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("year_id", Integer, ForeignKey("dim_year.year_id"), nullable=False),
        Column("operating_activity", Float),
        Column("investing_activity", Float),
        Column("financing_activity", Float),
        Column("net_cash_flow", Float),
        Column("free_cash_flow", Float),
        Column("cash_conversion_ratio", Float),
        PrimaryKeyConstraint("symbol", "year_id", name="pk_fact_cash_flow"),
    )

    fact_analysis = Table(
        "fact_analysis",
        metadata,
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("period_label", String(10), nullable=False),
        Column("compounded_sales_growth_pct", Float),
        Column("compounded_profit_growth_pct", Float),
        Column("stock_price_cagr_pct", Float),
        Column("roe_pct", Float),
        PrimaryKeyConstraint("symbol", "period_label", name="pk_fact_analysis"),
    )

    fact_ml_scores = Table(
        "fact_ml_scores",
        metadata,
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("computed_at", DateTime(timezone=True), nullable=False),
        Column("overall_score", Float),
        Column("profitability_score", Float),
        Column("growth_score", Float),
        Column("leverage_score", Float),
        Column("cashflow_score", Float),
        Column("dividend_score", Float),
        Column("trend_score", Float),
        Column("health_label", String(20)),
        PrimaryKeyConstraint("symbol", "computed_at", name="pk_fact_ml_scores"),
    )

    fact_pros_cons = Table(
        "fact_pros_cons",
        metadata,
        Column("insight_id", Integer, primary_key=True, autoincrement=True),
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("is_pro", Boolean, nullable=False),
        Column("category", String(100)),
        Column("text", Text, nullable=False),
        Column("source", String(20)),
        Column("confidence", Float),
        Column("generated_at", DateTime(timezone=True)),
        UniqueConstraint("symbol", "is_pro", "category", "text", name="uq_fact_pros_cons_key"),
    )

    fact_documents = Table(
        "fact_documents",
        metadata,
        Column("document_id", Integer, primary_key=True, autoincrement=True),
        Column("symbol", String(20), ForeignKey("dim_company.symbol"), nullable=False),
        Column("year_id", Integer, ForeignKey("dim_year.year_id")),
        Column("year_label", String(20)),
        Column("document_url", Text, nullable=False),
        Column("source", String(20)),
        UniqueConstraint("symbol", "year_label", "document_url", name="uq_fact_documents_key"),
    )

    return {
        "dim_sector": dim_sector,
        "dim_company": dim_company,
        "dim_year": dim_year,
        "dim_health_label": dim_health_label,
        "fact_profit_loss": fact_profit_loss,
        "fact_balance_sheet": fact_balance_sheet,
        "fact_cash_flow": fact_cash_flow,
        "fact_analysis": fact_analysis,
        "fact_ml_scores": fact_ml_scores,
        "fact_pros_cons": fact_pros_cons,
        "fact_documents": fact_documents,
    }


def prepare_dim_sector(companies: pd.DataFrame) -> pd.DataFrame:
    if companies.empty or "sector" not in companies.columns:
        return pd.DataFrame(columns=["sector_name", "sector_code", "description"])

    sectors = (
        companies[["sector"]]
        .dropna()
        .drop_duplicates()
        .rename(columns={"sector": "sector_name"})
        .sort_values("sector_name")
        .reset_index(drop=True)
    )

    sectors["sector_code"] = sectors["sector_name"].map(
        lambda name: re.sub(r"[^A-Za-z0-9]", "", str(name).upper())[:12] or "GEN"
    )
    sectors["description"] = sectors["sector_name"].map(lambda s: f"{s} sector")
    return sectors


def prepare_dim_company(companies: pd.DataFrame, sector_lookup: Dict[str, int]) -> pd.DataFrame:
    if companies.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "company_name",
                "sector_id",
                "sector",
                "sub_sector",
                "company_logo",
                "website",
                "nse_url",
                "bse_url",
                "face_value",
                "book_value",
                "about_company",
            ]
        )

    out = ensure_symbol(companies)

    for col in ["company_name", "sector", "sub_sector", "website", "about_company", "nse_url", "bse_url", "company_logo"]:
        if col not in out.columns:
            out[col] = np.nan

    if "company_logo" not in out.columns:
        logo_source = first_existing(out, ["logo", "logo_url"])
        if logo_source:
            out["company_logo"] = out[logo_source]

    if "nse_url" not in out.columns:
        nse_source = first_existing(out, ["nse_link", "nse"])
        if nse_source:
            out["nse_url"] = out[nse_source]

    if "bse_url" not in out.columns:
        bse_source = first_existing(out, ["bse_link", "bse"])
        if bse_source:
            out["bse_url"] = out[bse_source]

    for col in ["face_value", "book_value"]:
        if col in out.columns:
            out[col] = to_numeric(out[col])
        else:
            out[col] = np.nan

    out["sector_id"] = out["sector"].map(sector_lookup)

    selected = out[
        [
            "symbol",
            "company_name",
            "sector_id",
            "sector",
            "sub_sector",
            "company_logo",
            "website",
            "nse_url",
            "bse_url",
            "face_value",
            "book_value",
            "about_company",
        ]
    ].copy()

    selected = selected.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"], keep="last")
    return selected


def prepare_dim_year(dim_year_df: pd.DataFrame, tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    if dim_year_df.empty:
        year_frames: List[pd.DataFrame] = []
        for table_df in tables.values():
            required = {"year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"}
            if required.issubset(table_df.columns):
                year_frames.append(table_df[list(required)].copy())
        if year_frames:
            dim_year_df = pd.concat(year_frames, ignore_index=True)

    if dim_year_df.empty:
        return pd.DataFrame(columns=["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"])

    out = dim_year_df.copy()
    for col in ["year_label", "quarter"]:
        if col not in out.columns:
            out[col] = np.nan

    for col in ["fiscal_year", "sort_order", "year_id"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    for col in ["is_ttm", "is_half_year"]:
        if col in out.columns:
            out[col] = to_bool(out[col]).fillna(False)
        else:
            out[col] = False

    if "year_id" not in out.columns or out["year_id"].isna().all():
        out = out.sort_values(by=["sort_order", "year_label"], na_position="last").drop_duplicates(subset=["year_label"])
        out["year_id"] = np.arange(1, len(out) + 1)

    out["year_id"] = pd.to_numeric(out["year_id"], errors="coerce")
    out = out.dropna(subset=["year_id", "year_label"]).drop_duplicates(subset=["year_label"], keep="last")
    out["year_id"] = out["year_id"].astype(int)
    return out[["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]]


def prepare_fact_profit_loss(df: pd.DataFrame, year_lookup: Dict[str, int], fiscal_lookup: Dict[int, int]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = ensure_symbol(df)
    out = map_year_id(out, year_lookup, fiscal_lookup)

    for col in [
        "sales",
        "expenses",
        "operating_profit",
        "opm_pct",
        "other_income",
        "interest",
        "depreciation",
        "profit_before_tax",
        "tax_pct",
        "net_profit",
        "eps",
        "dividend_payout_pct",
        "net_profit_margin_pct",
        "expense_ratio_pct",
        "interest_coverage",
        "asset_turnover",
        "return_on_assets",
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = to_numeric(out[col])

    if out["opm_pct"].isna().all() and {"operating_profit", "sales"}.issubset(out.columns):
        out["opm_pct"] = (out["operating_profit"] / out["sales"].replace({0: np.nan})) * 100

    out = out[
        [
            "symbol",
            "year_id",
            "sales",
            "expenses",
            "operating_profit",
            "opm_pct",
            "other_income",
            "interest",
            "depreciation",
            "profit_before_tax",
            "tax_pct",
            "net_profit",
            "eps",
            "dividend_payout_pct",
            "net_profit_margin_pct",
            "expense_ratio_pct",
            "interest_coverage",
            "asset_turnover",
            "return_on_assets",
        ]
    ]

    out = out.dropna(subset=["symbol", "year_id"])
    out["year_id"] = out["year_id"].astype(int)
    return out


def prepare_fact_balance_sheet(df: pd.DataFrame, year_lookup: Dict[str, int], fiscal_lookup: Dict[int, int]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = ensure_symbol(df)
    out = map_year_id(out, year_lookup, fiscal_lookup)

    for col in [
        "equity_capital",
        "reserves",
        "borrowings",
        "other_liabilities",
        "total_liabilities",
        "fixed_assets",
        "cwip",
        "investments",
        "other_assets",
        "total_assets",
        "debt_to_equity",
        "equity_ratio",
        "book_value_per_share",
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = to_numeric(out[col])

    if out["debt_to_equity"].isna().all():
        equity_base = out["equity_capital"].fillna(0) + out["reserves"].fillna(0)
        out["debt_to_equity"] = out["borrowings"] / equity_base.replace({0: np.nan})

    out = out[
        [
            "symbol",
            "year_id",
            "equity_capital",
            "reserves",
            "borrowings",
            "other_liabilities",
            "total_liabilities",
            "fixed_assets",
            "cwip",
            "investments",
            "other_assets",
            "total_assets",
            "debt_to_equity",
            "equity_ratio",
            "book_value_per_share",
        ]
    ]

    out = out.dropna(subset=["symbol", "year_id"])
    out["year_id"] = out["year_id"].astype(int)
    return out


def prepare_fact_cash_flow(df: pd.DataFrame, year_lookup: Dict[str, int], fiscal_lookup: Dict[int, int]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = ensure_symbol(df)
    out = map_year_id(out, year_lookup, fiscal_lookup)

    for col in [
        "operating_activity",
        "investing_activity",
        "financing_activity",
        "net_cash_flow",
        "free_cash_flow",
        "cash_conversion_ratio",
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = to_numeric(out[col])

    if out["free_cash_flow"].isna().all():
        out["free_cash_flow"] = out["operating_activity"] + out["investing_activity"]

    out = out[
        [
            "symbol",
            "year_id",
            "operating_activity",
            "investing_activity",
            "financing_activity",
            "net_cash_flow",
            "free_cash_flow",
            "cash_conversion_ratio",
        ]
    ]

    out = out.dropna(subset=["symbol", "year_id"])
    out["year_id"] = out["year_id"].astype(int)
    return out


def prepare_fact_analysis(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = ensure_symbol(df)
    if "period_label" not in out.columns and "period" in out.columns:
        out["period_label"] = out["period"]

    for col in [
        "compounded_sales_growth_pct",
        "compounded_profit_growth_pct",
        "stock_price_cagr_pct",
        "roe_pct",
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = to_numeric(out[col])

    out = out[
        [
            "symbol",
            "period_label",
            "compounded_sales_growth_pct",
            "compounded_profit_growth_pct",
            "stock_price_cagr_pct",
            "roe_pct",
        ]
    ]
    out["period_label"] = out["period_label"].map(lambda v: str(v).upper().strip() if pd.notna(v) else v)

    out = out.dropna(subset=["symbol", "period_label"])
    return out


def prepare_fact_ml_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "computed_at",
                "overall_score",
                "profitability_score",
                "growth_score",
                "leverage_score",
                "cashflow_score",
                "dividend_score",
                "trend_score",
                "health_label",
            ]
        )

    out = ensure_symbol(df)

    if "computed_at" not in out.columns:
        out["computed_at"] = datetime.now(timezone.utc)
    else:
        out["computed_at"] = pd.to_datetime(out["computed_at"], utc=True, errors="coerce")
        out["computed_at"] = out["computed_at"].fillna(datetime.now(timezone.utc))

    for col in [
        "overall_score",
        "profitability_score",
        "growth_score",
        "leverage_score",
        "cashflow_score",
        "dividend_score",
        "trend_score",
    ]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = to_numeric(out[col])

    if "health_label" not in out.columns:
        out["health_label"] = out["overall_score"].map(assign_health_label_from_score)
    else:
        out["health_label"] = out["health_label"].fillna(out["overall_score"].map(assign_health_label_from_score))
        out["health_label"] = out["health_label"].map(lambda v: str(v).upper().strip() if pd.notna(v) else v)

    out = out[
        [
            "symbol",
            "computed_at",
            "overall_score",
            "profitability_score",
            "growth_score",
            "leverage_score",
            "cashflow_score",
            "dividend_score",
            "trend_score",
            "health_label",
        ]
    ]
    out = out.dropna(subset=["symbol", "computed_at"])
    return out


def prepare_fact_pros_cons(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "is_pro", "category", "text", "source", "confidence", "generated_at"])

    base = ensure_symbol(df)
    records: List[Dict[str, object]] = []

    has_flat_structure = {"text", "is_pro"}.issubset(base.columns)

    if has_flat_structure:
        work = base.copy()
        work["is_pro"] = to_bool(work["is_pro"]).fillna(False)
        if "generated_at" not in work.columns:
            work["generated_at"] = datetime.now(timezone.utc)
        else:
            work["generated_at"] = pd.to_datetime(work["generated_at"], utc=True, errors="coerce").fillna(
                datetime.now(timezone.utc)
            )
        if "source" not in work.columns:
            work["source"] = "MANUAL"
        if "confidence" not in work.columns:
            work["confidence"] = np.nan

        work = work[["symbol", "is_pro", "category", "text", "source", "confidence", "generated_at"]]
        work = work.dropna(subset=["symbol", "text"])
        return work

    for _, row in base.iterrows():
        symbol = row.get("symbol")
        if pd.isna(symbol):
            continue

        category = row.get("category") if pd.notna(row.get("category")) else "General"

        for text in split_insights(row.get("pros")):
            records.append(
                {
                    "symbol": symbol,
                    "is_pro": True,
                    "category": category,
                    "text": text,
                    "source": "MANUAL",
                    "confidence": np.nan,
                    "generated_at": datetime.now(timezone.utc),
                }
            )

        for text in split_insights(row.get("cons")):
            records.append(
                {
                    "symbol": symbol,
                    "is_pro": False,
                    "category": category,
                    "text": text,
                    "source": "MANUAL",
                    "confidence": np.nan,
                    "generated_at": datetime.now(timezone.utc),
                }
            )

    out = pd.DataFrame(records)
    if out.empty:
        return pd.DataFrame(columns=["symbol", "is_pro", "category", "text", "source", "confidence", "generated_at"])

    return out


def prepare_fact_documents(df: pd.DataFrame, year_lookup: Dict[str, int], fiscal_lookup: Dict[int, int]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "year_id", "year_label", "document_url", "source"])

    out = ensure_symbol(df)
    out = map_year_id(out, year_lookup, fiscal_lookup)

    url_col = first_existing(
        out,
        [
            "document_url",
            "url",
            "pdf_url",
            "annual_report_url",
            "report_link",
            "link",
            "document",
        ],
    )
    if not url_col:
        return pd.DataFrame(columns=["symbol", "year_id", "year_label", "document_url", "source"])

    if "year_label" not in out.columns:
        out["year_label"] = np.nan

    out["document_url"] = out[url_col]
    out["source"] = "BSE"
    out["year_id"] = pd.to_numeric(out.get("year_id"), errors="coerce")

    out["year_label"] = out["year_label"].where(out["year_label"].notna(), np.nan)
    out["year_label"] = out["year_label"].fillna(
        out["year_id"].map(lambda y: f"Y{int(y)}" if pd.notna(y) else np.nan)
    )

    out = out[["symbol", "year_id", "year_label", "document_url", "source"]]
    out = out.dropna(subset=["symbol", "document_url", "year_label"])
    out["year_id"] = out["year_id"].astype("Int64")
    out = out.drop_duplicates(subset=["symbol", "year_label", "document_url"], keep="last")
    return out


def run_data_quality_checks(conn: Connection, tables: Dict[str, Table]) -> None:
    dim_company = tables["dim_company"]
    dim_year = tables["dim_year"]
    fact_profit_loss = tables["fact_profit_loss"]
    fact_balance_sheet = tables["fact_balance_sheet"]
    fact_cash_flow = tables["fact_cash_flow"]

    dup_profit_subq = (
        select(fact_profit_loss.c.symbol, fact_profit_loss.c.year_id)
        .group_by(fact_profit_loss.c.symbol, fact_profit_loss.c.year_id)
        .having(func.count() > 1)
        .subquery()
    )

    # Exactly eight checks: row counts, nulls, duplicates, ranges, and FK integrity.
    checks = [
        (
            "dim_company row count > 0",
            select(func.count()).select_from(dim_company),
            lambda v: v > 0,
        ),
        (
            "dim_year row count > 0",
            select(func.count()).select_from(dim_year),
            lambda v: v > 0,
        ),
        (
            "fact_profit_loss null keys",
            select(func.count())
            .select_from(fact_profit_loss)
            .where(or_(fact_profit_loss.c.symbol.is_(None), fact_profit_loss.c.year_id.is_(None))),
            lambda v: v == 0,
        ),
        (
            "fact_balance_sheet null keys",
            select(func.count())
            .select_from(fact_balance_sheet)
            .where(or_(fact_balance_sheet.c.symbol.is_(None), fact_balance_sheet.c.year_id.is_(None))),
            lambda v: v == 0,
        ),
        (
            "fact_cash_flow null keys",
            select(func.count())
            .select_from(fact_cash_flow)
            .where(or_(fact_cash_flow.c.symbol.is_(None), fact_cash_flow.c.year_id.is_(None))),
            lambda v: v == 0,
        ),
        (
            "fact_profit_loss duplicate (symbol,year_id)",
            select(func.count()).select_from(dup_profit_subq),
            lambda v: v == 0,
        ),
        (
            "fact_profit_loss OPM% out of range",
            select(func.count())
            .select_from(fact_profit_loss)
            .where(or_(fact_profit_loss.c.opm_pct < -100, fact_profit_loss.c.opm_pct > 100)),
            lambda v: v == 0,
        ),
        (
            "fact_profit_loss orphan foreign keys",
            select(func.count())
            .select_from(
                fact_profit_loss.outerjoin(dim_company, fact_profit_loss.c.symbol == dim_company.c.symbol).outerjoin(
                    dim_year, fact_profit_loss.c.year_id == dim_year.c.year_id
                )
            )
            .where(or_(dim_company.c.symbol.is_(None), dim_year.c.year_id.is_(None))),
            lambda v: v == 0,
        ),
    ]

    failures: List[str] = []
    for label, query, validator in checks:
        measured = int(conn.execute(query).scalar_one())
        ok = validator(measured)
        status = "PASS" if ok else "FAIL"
        print(f"[DQ] {status} | {label}: {measured}")
        if not ok:
            failures.append(f"{label} -> {measured}")

    if failures:
        failure_text = "; ".join(failures)
        raise RuntimeError(f"Data quality checks failed: {failure_text}")


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise ValueError("PostgreSQL URL is required. Pass --db-url or set DATABASE_URL.")

    clean_dir = Path(args.clean_dir)

    tables_df = {
        "companies": load_csv_if_exists(clean_dir, "companies"),
        "analysis": load_csv_if_exists(clean_dir, "analysis"),
        "balancesheet": load_csv_if_exists(clean_dir, "balancesheet"),
        "profitandloss": load_csv_if_exists(clean_dir, "profitandloss"),
        "cashflow": load_csv_if_exists(clean_dir, "cashflow"),
        "prosandcons": load_csv_if_exists(clean_dir, "prosandcons"),
        "documents": load_csv_if_exists(clean_dir, "documents"),
        "dim_year": load_csv_if_exists(clean_dir, "dim_year"),
        "fact_ml_scores": load_csv_if_exists(clean_dir, "fact_ml_scores"),
    }

    metadata = MetaData()
    tables = define_schema(metadata)

    engine = create_engine(args.db_url, future=True)

    with engine.begin() as conn:
        metadata.create_all(conn)

        dim_sector_df = prepare_dim_sector(tables_df["companies"])
        upsert_dataframe(conn, tables["dim_sector"], dim_sector_df, conflict_cols=["sector_name"])

        sector_lookup = {
            row.sector_name: row.sector_id
            for row in conn.execute(select(tables["dim_sector"].c.sector_name, tables["dim_sector"].c.sector_id)).all()
        }

        dim_company_df = prepare_dim_company(tables_df["companies"], sector_lookup)
        upsert_dataframe(conn, tables["dim_company"], dim_company_df, conflict_cols=["symbol"])

        dim_year_df = prepare_dim_year(tables_df["dim_year"], tables_df)
        upsert_dataframe(conn, tables["dim_year"], dim_year_df, conflict_cols=["year_label"])

        health_labels = pd.DataFrame(
            [
                {"label_id": 1, "label_name": "EXCELLENT", "min_score": 85.0, "max_score": 100.0, "color_hex": "#1A9850"},
                {"label_id": 2, "label_name": "GOOD", "min_score": 70.0, "max_score": 84.99, "color_hex": "#66BD63"},
                {"label_id": 3, "label_name": "AVERAGE", "min_score": 50.0, "max_score": 69.99, "color_hex": "#FEE08B"},
                {"label_id": 4, "label_name": "WEAK", "min_score": 35.0, "max_score": 49.99, "color_hex": "#FDAE61"},
                {"label_id": 5, "label_name": "POOR", "min_score": 0.0, "max_score": 39.99, "color_hex": "#D73027"},
            ]
        )
        upsert_dataframe(conn, tables["dim_health_label"], health_labels, conflict_cols=["label_id"])

        year_lookup = {
            row.year_label: row.year_id
            for row in conn.execute(select(tables["dim_year"].c.year_label, tables["dim_year"].c.year_id)).all()
        }
        fiscal_lookup = {
            row.fiscal_year: row.year_id
            for row in conn.execute(select(tables["dim_year"].c.fiscal_year, tables["dim_year"].c.year_id)).all()
            if row.fiscal_year is not None
        }

        fact_profit_loss_df = prepare_fact_profit_loss(tables_df["profitandloss"], year_lookup, fiscal_lookup)
        upsert_dataframe(conn, tables["fact_profit_loss"], fact_profit_loss_df, conflict_cols=["symbol", "year_id"])

        fact_balance_sheet_df = prepare_fact_balance_sheet(tables_df["balancesheet"], year_lookup, fiscal_lookup)
        upsert_dataframe(conn, tables["fact_balance_sheet"], fact_balance_sheet_df, conflict_cols=["symbol", "year_id"])

        fact_cash_flow_df = prepare_fact_cash_flow(tables_df["cashflow"], year_lookup, fiscal_lookup)
        upsert_dataframe(conn, tables["fact_cash_flow"], fact_cash_flow_df, conflict_cols=["symbol", "year_id"])

        fact_analysis_df = prepare_fact_analysis(tables_df["analysis"])
        upsert_dataframe(conn, tables["fact_analysis"], fact_analysis_df, conflict_cols=["symbol", "period_label"])

        fact_ml_scores_df = prepare_fact_ml_scores(tables_df["fact_ml_scores"])
        upsert_dataframe(conn, tables["fact_ml_scores"], fact_ml_scores_df, conflict_cols=["symbol", "computed_at"])

        fact_pros_cons_df = prepare_fact_pros_cons(tables_df["prosandcons"])
        upsert_dataframe(conn, tables["fact_pros_cons"], fact_pros_cons_df, conflict_cols=["symbol", "is_pro", "category", "text"])

        fact_documents_df = prepare_fact_documents(tables_df["documents"], year_lookup, fiscal_lookup)
        upsert_dataframe(conn, tables["fact_documents"], fact_documents_df, conflict_cols=["symbol", "year_label", "document_url"])

        run_data_quality_checks(conn, tables)


if __name__ == "__main__":
    main()
