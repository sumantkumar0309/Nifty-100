from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from etl.config import CLEAN_DIR, DATA_DIR, RAW_DIR, ensure_data_dirs
from etl.utils.io_helpers import (
    clean_symbol,
    find_symbol_column,
    find_year_like_column,
    first_matching_column,
    normalize_columns,
    normalize_nulls,
    safe_to_numeric,
)

pd.options.mode.copy_on_write = False
warnings.filterwarnings("ignore", category=FutureWarning, message=".*ChainedAssignmentError.*")

SECTOR_VALUES = [
    "IT",
    "Banking",
    "NBFC",
    "Insurance",
    "Energy",
    "Power",
    "Ports",
    "Cement",
    "Healthcare",
    "Auto",
    "Paint",
    "Consumer Goods",
    "Holding Company",
]

DEFAULT_HEALTH_LABELS = [
    {"label_id": 1, "label_name": "EXCELLENT", "min_score": 85, "max_score": 100, "color_hex": "#1E8449"},
    {"label_id": 2, "label_name": "GOOD", "min_score": 70, "max_score": 84.99, "color_hex": "#27AE60"},
    {"label_id": 3, "label_name": "AVERAGE", "min_score": 55, "max_score": 69.99, "color_hex": "#F1C40F"},
    {"label_id": 4, "label_name": "WEAK", "min_score": 40, "max_score": 54.99, "color_hex": "#E67E22"},
    {"label_id": 5, "label_name": "POOR", "min_score": 0, "max_score": 39.99, "color_hex": "#C0392B"},
]

CURATED_SECTOR_MAP = {
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HDFCBANK": "Banking",
    "AXISBANK": "Banking",
    "BANKBARODA": "Banking",
    "ADANIGREEN": "Energy",
    "ADANIPOWER": "Power",
    "ADANIENSOL": "Energy",
    "ATGL": "Energy",
    "AMBUJACEM": "Cement",
    "APOLLOHOSP": "Healthcare",
    "ASIANPAINT": "Paint",
    "SBILIFE": "Insurance",
    "BAJAJ_AUTO": "Auto",
    "BAJAJ-AUTO": "Auto",
    "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "Holding Company",
}

SOURCE_SECTOR_CANONICAL_MAP = {
    "it": "IT",
    "information technology": "IT",
    "software": "IT",
    "software services": "IT",
    "bank": "Banking",
    "banks": "Banking",
    "banking": "Banking",
    "financial services": "NBFC",
    "finance": "NBFC",
    "nbfc": "NBFC",
    "insurance": "Insurance",
    "life insurance": "Insurance",
    "energy": "Energy",
    "oil": "Energy",
    "oil and gas": "Energy",
    "gas": "Energy",
    "power": "Power",
    "utilities": "Power",
    "ports": "Ports",
    "logistics": "Ports",
    "cement": "Cement",
    "healthcare": "Healthcare",
    "pharmaceuticals": "Healthcare",
    "pharma": "Healthcare",
    "hospital": "Healthcare",
    "auto": "Auto",
    "automobiles": "Auto",
    "auto ancillaries": "Auto",
    "paint": "Paint",
    "paints": "Paint",
    "consumer goods": "Consumer Goods",
    "fmcg": "Consumer Goods",
    "consumer": "Consumer Goods",
    "retail": "Consumer Goods",
    "holding company": "Holding Company",
    "holding": "Holding Company",
    "capital goods": "Consumer Goods",
}


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace({0: np.nan})
    return numerator / denom


def read_raw_table(table_name: str) -> pd.DataFrame:
    path = RAW_DIR / f"{table_name}.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    df = normalize_columns(df)
    df = normalize_nulls(df)
    return df


def canonical_symbol(value: object) -> str:
    text = str(value).strip().upper()
    return text.replace(" ", "").replace(".", "").replace("_", "-")


def period_from_text(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip().upper()
    if "TTM" in text:
        return "TTM"
    if re.search(r"10\s*Y|10\s*YEAR", text):
        return "10Y"
    if re.search(r"5\s*Y|5\s*YEAR", text):
        return "5Y"
    if re.search(r"3\s*Y|3\s*YEAR", text):
        return "3Y"
    return None


def percent_value_from_text(value: object) -> float | None:
    if pd.isna(value):
        return None
    text = str(value)
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%?", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_period_label(value: object) -> str | None:
    if pd.isna(value):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper().replace("/", " ").replace("-", " ")
    upper = re.sub(r"\s+", " ", upper).strip()

    if upper == "TTM":
        return "TTM"

    month_match = re.search(r"(MAR|JUN|SEP|DEC)\s*(\d{2,4})", upper)
    if month_match:
        month = month_match.group(1).title()
        year = int(month_match.group(2))
        if year < 100:
            year = 2000 + year if year <= 69 else 1900 + year
        return f"{month} {year}"

    fy_match = re.search(r"(?:FY|FISCAL)\s*(\d{2,4})", upper)
    if fy_match:
        year = int(fy_match.group(1))
        if year < 100:
            year = 2000 + year if year <= 69 else 1900 + year
        return f"Mar {year}"

    bare_year = re.fullmatch(r"(\d{2,4})", upper)
    if bare_year:
        year = int(bare_year.group(1))
        if year < 100:
            year = 2000 + year if year <= 69 else 1900 + year
        return f"Mar {year}"

    return raw


def enrich_period_columns(df: pd.DataFrame, year_col: str | None) -> pd.DataFrame:
    out = df.copy()
    if not year_col or year_col not in out.columns:
        out["year_label"] = np.nan
        out["fiscal_year"] = np.nan
        out["quarter"] = np.nan
        out["is_ttm"] = False
        out["is_half_year"] = False
        out["sort_order"] = np.nan
        return out

    out["year_label"] = out[year_col].apply(normalize_period_label)

    def fiscal_year_from_label(label: object) -> float:
        if pd.isna(label):
            return np.nan
        if str(label).upper() == "TTM":
            return np.nan
        m = re.search(r"(\d{4})", str(label))
        return float(m.group(1)) if m else np.nan

    def quarter_from_label(label: object) -> str | float:
        if pd.isna(label):
            return np.nan
        text = str(label)
        if text.upper() == "TTM":
            return "TTM"
        if text.startswith("Mar"):
            return "Q4"
        if text.startswith("Jun"):
            return "Q1"
        if text.startswith("Sep"):
            return "Q2"
        if text.startswith("Dec"):
            return "Q3"
        return np.nan

    out["fiscal_year"] = out["year_label"].apply(fiscal_year_from_label)
    out["quarter"] = out["year_label"].apply(quarter_from_label)
    out["is_ttm"] = out["year_label"].astype(str).str.upper().eq("TTM")
    out["is_half_year"] = out["year_label"].astype(str).str.startswith("Sep")

    quarter_weight = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "TTM": 9}
    out["sort_order"] = (
        out["fiscal_year"].fillna(9999).astype(int) * 10
        + out["quarter"].map(quarter_weight).fillna(0).astype(int)
    )
    return out


def infer_sector(symbol: str, company_name: str) -> str:
    sym = canonical_symbol(symbol)
    if sym in CURATED_SECTOR_MAP:
        return CURATED_SECTOR_MAP[sym]

    name = (company_name or "").upper()
    if any(x in name for x in ["BANK", "HDFC", "KOTAK", "SBI"]):
        return "Banking"
    if any(x in name for x in ["FINANCE", "CAPITAL", "CHOLA", "SHRIRAM"]):
        return "NBFC"
    if any(x in name for x in ["INSURANCE", "LIFE"]):
        return "Insurance"
    if any(x in name for x in ["TECH", "INFOTECH", "SOFTWARE", "SYSTEMS"]):
        return "IT"
    if any(x in name for x in ["POWER", "ELECTRIC"]):
        return "Power"
    if any(x in name for x in ["ENERGY", "GAS", "OIL", "PETRO"]):
        return "Energy"
    if any(x in name for x in ["PORT", "LOGISTICS", "SHIPPING"]):
        return "Ports"
    if any(x in name for x in ["CEMENT"]):
        return "Cement"
    if any(x in name for x in ["HOSP", "PHARMA", "LAB", "HEALTH", "MEDIC"]):
        return "Healthcare"
    if any(x in name for x in ["MOTOR", "AUTO", "TYRE", "TRACTOR"]):
        return "Auto"
    if any(x in name for x in ["PAINT", "COATINGS"]):
        return "Paint"
    if any(x in name for x in ["CONSUMER", "FOODS", "RETAIL", "PERSONAL"]):
        return "Consumer Goods"
    if any(x in name for x in ["HOLDING", "INVESTMENT"]):
        return "Holding Company"

    return "Consumer Goods"


def normalize_sector_label(value: object) -> str | None:
    if pd.isna(value):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    if raw in SECTOR_VALUES:
        return raw

    normalized = re.sub(r"\s+", " ", raw.lower())
    return SOURCE_SECTOR_CANONICAL_MAP.get(normalized)


def create_sector_mapping(companies_df: pd.DataFrame) -> pd.DataFrame:
    mapping_path = DATA_DIR / "sector_mapping.csv"

    symbol_col = find_symbol_column(companies_df)
    if not symbol_col:
        raise ValueError("No company symbol column found in companies.csv")

    name_col = first_matching_column(companies_df, ["company", "name"]) or first_matching_column(
        companies_df, ["name"]
    )
    source_sector_col = first_matching_column(companies_df, ["sector"])
    if not name_col:
        name_col = symbol_col

    base = companies_df[[symbol_col, name_col]].copy()
    base.columns = ["symbol", "company_name"]
    if source_sector_col:
        base["source_sector"] = companies_df[source_sector_col]
    else:
        base["source_sector"] = np.nan

    base["symbol"] = clean_symbol(base["symbol"])
    base["company_name"] = base["company_name"].astype(str).str.replace("\r", "", regex=False).str.strip()
    base["source_sector"] = base["source_sector"].apply(normalize_sector_label)

    if mapping_path.exists():
        mapping = pd.read_csv(mapping_path)
        mapping = normalize_columns(mapping)
        if "symbol" not in mapping.columns:
            raise ValueError("sector_mapping.csv exists but has no symbol column")
        if "sector" not in mapping.columns:
            mapping["sector"] = np.nan
        mapping["symbol"] = clean_symbol(mapping["symbol"])
        merged = base.merge(mapping[["symbol", "sector"]], on="symbol", how="left")
    else:
        merged = base.copy()
        merged["sector"] = np.nan

    merged["sector"] = merged.apply(
        lambda row: normalize_sector_label(row["sector"])
        if isinstance(row["sector"], str) and row["sector"].strip()
        else row["source_sector"]
        if isinstance(row["source_sector"], str) and row["source_sector"].strip()
        else infer_sector(row["symbol"], row["company_name"]),
        axis=1,
    )

    merged["sector"] = merged["sector"].apply(lambda x: x if x in SECTOR_VALUES else "Consumer Goods")
    merged = merged.drop(columns=["source_sector"], errors="ignore")
    merged = merged.drop_duplicates(subset=["symbol"]).sort_values("symbol")
    merged.to_csv(mapping_path, index=False)
    return merged


def choose_numeric(df: pd.DataFrame, include: list[str], exclude: list[str] | None = None) -> pd.Series:
    col = first_matching_column(df, include_keywords=include, exclude_keywords=exclude or [])
    if not col:
        return pd.Series([np.nan] * len(df), index=df.index)
    return safe_to_numeric(df[col])


def build_dim_company(companies_df: pd.DataFrame, sector_map: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbol_col = find_symbol_column(companies_df)
    if not symbol_col:
        raise ValueError("No symbol/company_id column found in companies table")

    name_col = first_matching_column(companies_df, ["company", "name"]) or first_matching_column(
        companies_df, ["name"]
    )

    dim = pd.DataFrame()
    dim["symbol"] = clean_symbol(companies_df[symbol_col])
    dim["company_name"] = (
        companies_df[name_col].astype(str).str.replace("\r", "", regex=False).str.replace("\n", " ", regex=False).str.strip()
        if name_col
        else dim["symbol"]
    )

    dim["company_logo"] = companies_df[first_matching_column(companies_df, ["logo"]) or symbol_col]
    dim["website"] = companies_df[first_matching_column(companies_df, ["website"]) or symbol_col]
    dim["nse_url"] = companies_df[first_matching_column(companies_df, ["nse"]) or symbol_col]
    dim["bse_url"] = companies_df[first_matching_column(companies_df, ["bse"]) or symbol_col]
    dim["face_value"] = choose_numeric(companies_df, ["face", "value"])
    dim["book_value"] = choose_numeric(companies_df, ["book", "value"])
    dim["about_company"] = companies_df[first_matching_column(companies_df, ["about"]) or symbol_col]

    dim = dim.merge(sector_map[["symbol", "sector"]], on="symbol", how="left")
    dim = dim.drop_duplicates(subset=["symbol"]).reset_index(drop=True)

    sectors = sorted(dim["sector"].dropna().unique())
    dim_sector = pd.DataFrame(
        {
            "sector_id": list(range(1, len(sectors) + 1)),
            "sector_name": sectors,
        }
    )
    dim_sector["sector_code"] = dim_sector["sector_name"].str.upper().str.replace(" ", "_", regex=False)
    dim_sector["description"] = dim_sector["sector_name"].apply(lambda x: f"{x} sector companies")

    dim = dim.merge(dim_sector[["sector_id", "sector_name"]], left_on="sector", right_on="sector_name", how="left")
    dim = dim.drop(columns=["sector_name"]).rename(columns={"sector": "sector_name"})

    return dim, dim_sector


def build_profit_loss_fact(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "year_label",
                "fiscal_year",
                "quarter",
                "is_ttm",
                "is_half_year",
                "sort_order",
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
            ]
        )

    symbol_col = find_symbol_column(df)
    year_col = find_year_like_column(df)

    out = pd.DataFrame(index=df.index)
    out["symbol"] = clean_symbol(df[symbol_col]) if symbol_col else np.nan
    period_source = df[[year_col]].copy() if year_col and year_col in df.columns else pd.DataFrame(index=df.index)
    period_info = enrich_period_columns(period_source, year_col)
    out = pd.concat(
        [
            out,
            period_info[["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]],
        ],
        axis=1,
    )

    out["sales"] = choose_numeric(df, ["sales"], ["growth", "cagr"])
    out["expenses"] = choose_numeric(df, ["expense"])
    if out["expenses"].isna().all():
        out["expenses"] = choose_numeric(df, ["expenditure"])

    out["operating_profit"] = choose_numeric(df, ["operating", "profit"])
    out["opm_pct"] = choose_numeric(df, ["opm"])
    if out["opm_pct"].isna().all():
        out["opm_pct"] = choose_numeric(df, ["operating", "margin"])

    out["other_income"] = choose_numeric(df, ["other", "income"])
    out["interest"] = choose_numeric(df, ["interest"])
    out["depreciation"] = choose_numeric(df, ["depreciation"])
    out["profit_before_tax"] = choose_numeric(df, ["before", "tax"])
    out["tax_pct"] = choose_numeric(df, ["tax", "pct"])
    if out["tax_pct"].isna().all():
        out["tax_pct"] = choose_numeric(df, ["tax"])
    out["net_profit"] = choose_numeric(df, ["net", "profit"])
    if out["net_profit"].isna().all():
        out["net_profit"] = choose_numeric(df, ["profit", "after", "tax"])
    out["eps"] = choose_numeric(df, ["eps"])
    out["dividend_payout_pct"] = choose_numeric(df, ["dividend", "payout"])

    out["net_profit_margin_pct"] = safe_divide(out["net_profit"], out["sales"]) * 100
    out["expense_ratio_pct"] = safe_divide(out["expenses"], out["sales"]) * 100
    out["interest_coverage"] = safe_divide(out["operating_profit"], out["interest"])

    keep_cols = [
        "symbol",
        "year_label",
        "fiscal_year",
        "quarter",
        "is_ttm",
        "is_half_year",
        "sort_order",
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
    ]

    return out[keep_cols].drop_duplicates(subset=["symbol", "year_label"])


def build_balance_sheet_fact(df: pd.DataFrame, dim_company: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "year_label",
                "fiscal_year",
                "quarter",
                "is_ttm",
                "is_half_year",
                "sort_order",
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
                "shares_outstanding",
                "book_value_per_share",
            ]
        )

    symbol_col = find_symbol_column(df)
    year_col = find_year_like_column(df)

    out = pd.DataFrame(index=df.index)
    out["symbol"] = clean_symbol(df[symbol_col]) if symbol_col else np.nan
    period_source = df[[year_col]].copy() if year_col and year_col in df.columns else pd.DataFrame(index=df.index)
    period_info = enrich_period_columns(period_source, year_col)
    out = pd.concat(
        [
            out,
            period_info[["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]],
        ],
        axis=1,
    )

    out["equity_capital"] = choose_numeric(df, ["equity", "capital"])
    out["reserves"] = choose_numeric(df, ["reserve"])
    out["borrowings"] = choose_numeric(df, ["borrowing"])
    out["other_liabilities"] = choose_numeric(df, ["other", "liabilit"])
    out["total_liabilities"] = choose_numeric(df, ["total", "liabilit"])
    out["fixed_assets"] = choose_numeric(df, ["fixed", "asset"])
    out["cwip"] = choose_numeric(df, ["cwip"])
    out["investments"] = choose_numeric(df, ["investment"])
    out["other_assets"] = choose_numeric(df, ["other", "asset"])
    out["total_assets"] = choose_numeric(df, ["total", "asset"])

    out["debt_to_equity"] = safe_divide(out["borrowings"], out["equity_capital"] + out["reserves"])
    out["equity_ratio"] = safe_divide(out["equity_capital"] + out["reserves"], out["total_assets"])

    shares_col = first_matching_column(df, ["shares", "outstanding"])
    if shares_col:
        out["shares_outstanding"] = safe_to_numeric(df[shares_col])
    else:
        company_face = dim_company[["symbol", "face_value"]].copy()
        out = out.merge(company_face, on="symbol", how="left")
        out["shares_outstanding"] = safe_divide(out["equity_capital"], out["face_value"])  # Approximation.
        out = out.drop(columns=["face_value"])

    out["book_value_per_share"] = safe_divide(out["equity_capital"] + out["reserves"], out["shares_outstanding"])

    keep_cols = [
        "symbol",
        "year_label",
        "fiscal_year",
        "quarter",
        "is_ttm",
        "is_half_year",
        "sort_order",
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
        "shares_outstanding",
        "book_value_per_share",
    ]
    return out[keep_cols].drop_duplicates(subset=["symbol", "year_label"])


def build_cash_flow_fact(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "year_label",
                "fiscal_year",
                "quarter",
                "is_ttm",
                "is_half_year",
                "sort_order",
                "operating_activity",
                "investing_activity",
                "financing_activity",
                "net_cash_flow",
                "free_cash_flow",
            ]
        )

    symbol_col = find_symbol_column(df)
    year_col = find_year_like_column(df)

    out = pd.DataFrame(index=df.index)
    out["symbol"] = clean_symbol(df[symbol_col]) if symbol_col else np.nan
    period_source = df[[year_col]].copy() if year_col and year_col in df.columns else pd.DataFrame(index=df.index)
    period_info = enrich_period_columns(period_source, year_col)
    out = pd.concat(
        [
            out,
            period_info[["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]],
        ],
        axis=1,
    )

    out["operating_activity"] = choose_numeric(df, ["operating", "activity"])
    if out["operating_activity"].isna().all():
        out["operating_activity"] = choose_numeric(df, ["cash", "from", "operat"])

    out["investing_activity"] = choose_numeric(df, ["investing", "activity"])
    if out["investing_activity"].isna().all():
        out["investing_activity"] = choose_numeric(df, ["cash", "from", "invest"])

    out["financing_activity"] = choose_numeric(df, ["financing", "activity"])
    if out["financing_activity"].isna().all():
        out["financing_activity"] = choose_numeric(df, ["cash", "from", "financ"])

    out["net_cash_flow"] = choose_numeric(df, ["net", "cash", "flow"])
    out["free_cash_flow"] = out["operating_activity"] + out["investing_activity"]

    keep_cols = [
        "symbol",
        "year_label",
        "fiscal_year",
        "quarter",
        "is_ttm",
        "is_half_year",
        "sort_order",
        "operating_activity",
        "investing_activity",
        "financing_activity",
        "net_cash_flow",
        "free_cash_flow",
    ]
    return out[keep_cols].drop_duplicates(subset=["symbol", "year_label"])


def build_analysis_fact(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "period_label",
                "compounded_sales_growth_pct",
                "compounded_profit_growth_pct",
                "stock_price_cagr_pct",
                "roe_pct",
            ]
        )

    symbol_col = find_symbol_column(df)
    if not symbol_col:
        raise ValueError("No symbol/company_id column found in analysis table")

    metric_col = first_matching_column(df, ["metric"])
    period_col = first_matching_column(df, ["period"])
    value_col = first_matching_column(df, ["value", "pct"])

    if metric_col and period_col and value_col:
        long_df = df.copy()
        long_df["symbol"] = clean_symbol(long_df[symbol_col])
        long_df["period_label"] = long_df[period_col].apply(period_from_text)
        long_df["value_pct"] = safe_to_numeric(long_df[value_col])

        def metric_to_target(metric: object) -> str | None:
            low = str(metric).strip().lower()
            if "sales" in low and ("growth" in low or "cagr" in low):
                return "compounded_sales_growth_pct"
            if "profit" in low and ("growth" in low or "cagr" in low):
                return "compounded_profit_growth_pct"
            if "stock" in low and ("cagr" in low or "return" in low):
                return "stock_price_cagr_pct"
            if low == "roe" or "roe" in low:
                return "roe_pct"
            return None

        long_df["metric_target"] = long_df[metric_col].apply(metric_to_target)
        long_df = long_df.dropna(subset=["period_label", "metric_target", "value_pct"])

        if long_df.empty:
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "period_label",
                    "compounded_sales_growth_pct",
                    "compounded_profit_growth_pct",
                    "stock_price_cagr_pct",
                    "roe_pct",
                ]
            )

        out = (
            long_df.pivot_table(
                index=["symbol", "period_label"],
                columns="metric_target",
                values="value_pct",
                aggfunc="first",
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )

        for col in [
            "compounded_sales_growth_pct",
            "compounded_profit_growth_pct",
            "stock_price_cagr_pct",
            "roe_pct",
        ]:
            if col not in out.columns:
                out[col] = np.nan

        order = {"10Y": 1, "5Y": 2, "3Y": 3, "TTM": 4}
        out["_period_order"] = out["period_label"].map(order).fillna(99)
        out = out.sort_values(["symbol", "_period_order"]).drop(columns=["_period_order"])
        return out.drop_duplicates(subset=["symbol", "period_label"])

    metric_lookup = {
        "compounded_sales_growth_pct": [["sales", "growth"], ["sales", "cagr"]],
        "compounded_profit_growth_pct": [["profit", "growth"], ["profit", "cagr"]],
        "stock_price_cagr_pct": [["stock", "cagr"], ["stock", "return"]],
        "roe_pct": [["roe"]],
    }

    rows: dict[tuple[str, str], dict[str, object]] = {}

    for _, record in df.iterrows():
        symbol = canonical_symbol(record[symbol_col])

        for col in df.columns:
            if col == symbol_col:
                continue

            metric_name = None
            for target_metric, key_sets in metric_lookup.items():
                for keys in key_sets:
                    if all(k in col for k in keys):
                        metric_name = target_metric
                        break
                if metric_name:
                    break

            if not metric_name:
                continue

            raw_value = record[col]
            period = period_from_text(col) or period_from_text(raw_value)
            value_pct = percent_value_from_text(raw_value)

            if period is None or value_pct is None:
                continue

            key = (symbol, period)
            if key not in rows:
                rows[key] = {
                    "symbol": symbol,
                    "period_label": period,
                    "compounded_sales_growth_pct": np.nan,
                    "compounded_profit_growth_pct": np.nan,
                    "stock_price_cagr_pct": np.nan,
                    "roe_pct": np.nan,
                }
            rows[key][metric_name] = value_pct

    out = pd.DataFrame(rows.values())
    if out.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "period_label",
                "compounded_sales_growth_pct",
                "compounded_profit_growth_pct",
                "stock_price_cagr_pct",
                "roe_pct",
            ]
        )

    order = {"10Y": 1, "5Y": 2, "3Y": 3, "TTM": 4}
    out["_period_order"] = out["period_label"].map(order).fillna(99)
    out = out.sort_values(["symbol", "_period_order"]).drop(columns=["_period_order"])
    return out.drop_duplicates(subset=["symbol", "period_label"])


def explode_text(value: object) -> list[str]:
    if pd.isna(value):
        return []

    text = str(value).strip()
    if not text:
        return []

    chunks = re.split(r"\r\n|\n|\||;", text)
    cleaned = [chunk.strip(" -\t") for chunk in chunks if chunk.strip(" -\t")]
    if cleaned:
        return cleaned
    return [text]


def build_pros_cons_fact(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "is_pro", "category", "text", "source", "confidence", "generated_at"])

    symbol_col = find_symbol_column(df)
    if not symbol_col:
        raise ValueError("No symbol/company_id column found in prosandcons table")

    pro_col = first_matching_column(df, ["pro"], ["con"])
    con_col = first_matching_column(df, ["con"])

    out_rows = []
    for _, row in df.iterrows():
        symbol = canonical_symbol(row[symbol_col])

        if pro_col and pro_col in df.columns:
            for text in explode_text(row[pro_col]):
                out_rows.append(
                    {
                        "symbol": symbol,
                        "is_pro": True,
                        "category": "MANUAL",
                        "text": text,
                        "source": "MANUAL",
                        "confidence": 1.0,
                        "generated_at": None,
                    }
                )

        if con_col and con_col in df.columns:
            for text in explode_text(row[con_col]):
                out_rows.append(
                    {
                        "symbol": symbol,
                        "is_pro": False,
                        "category": "MANUAL",
                        "text": text,
                        "source": "MANUAL",
                        "confidence": 1.0,
                        "generated_at": None,
                    }
                )

    return pd.DataFrame(out_rows)


def build_year_dimension(*fact_dfs: pd.DataFrame) -> pd.DataFrame:
    year_frames = []
    for df in fact_dfs:
        if df.empty:
            continue
        cols = ["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]
        if all(col in df.columns for col in cols):
            year_frames.append(df[cols])

    if not year_frames:
        return pd.DataFrame(
            columns=["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]
        )

    dim_year = pd.concat(year_frames, axis=0, ignore_index=True)
    dim_year = dim_year.dropna(subset=["year_label"]).drop_duplicates(subset=["year_label"])  # Keep one row per label.
    dim_year = dim_year.sort_values(["sort_order", "year_label"]).reset_index(drop=True)
    dim_year["year_id"] = range(1, len(dim_year) + 1)

    return dim_year[["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]]


def attach_year_id(fact_df: pd.DataFrame, dim_year: pd.DataFrame) -> pd.DataFrame:
    if fact_df.empty:
        return fact_df

    out = fact_df.merge(dim_year[["year_id", "year_label"]], on="year_label", how="left")
    out = out.drop(columns=["fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order", "year_label"], errors="ignore")

    cols = list(out.columns)
    if "year_id" in cols:
        cols.insert(1, cols.pop(cols.index("year_id")))
    return out[cols]


def add_cross_table_metrics(fact_profit_loss: pd.DataFrame, fact_balance_sheet: pd.DataFrame, fact_cash_flow: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not fact_profit_loss.empty and not fact_balance_sheet.empty:
        merged = fact_profit_loss.merge(
            fact_balance_sheet[["symbol", "year_label", "total_assets"]], on=["symbol", "year_label"], how="left"
        )
        merged["asset_turnover"] = safe_divide(merged["sales"], merged["total_assets"])
        merged["return_on_assets"] = safe_divide(merged["net_profit"], merged["total_assets"]) * 100
        fact_profit_loss = merged.drop(columns=["total_assets"])

    if not fact_cash_flow.empty and not fact_profit_loss.empty:
        merged_cf = fact_cash_flow.merge(
            fact_profit_loss[["symbol", "year_label", "net_profit"]],
            on=["symbol", "year_label"],
            how="left",
        )
        merged_cf["cash_conversion_ratio"] = safe_divide(merged_cf["operating_activity"], merged_cf["net_profit"])
        fact_cash_flow = merged_cf.drop(columns=["net_profit"])

    return fact_profit_loss, fact_cash_flow


def save_clean_table(df: pd.DataFrame, filename: str) -> Path:
    path = CLEAN_DIR / filename
    df.to_csv(path, index=False)
    print(f"Saved {filename}: rows={len(df)}, cols={list(df.columns)}")
    return path


def main() -> None:
    ensure_data_dirs()

    companies = read_raw_table("companies")
    analysis = read_raw_table("analysis")
    balancesheet = read_raw_table("balancesheet")
    profitandloss = read_raw_table("profitandloss")
    cashflow = read_raw_table("cashflow")
    prosandcons = read_raw_table("prosandcons")
    documents = read_raw_table("documents")

    if companies.empty:
        raise ValueError("Raw companies.csv is required before running transformation.")

    sector_map = create_sector_mapping(companies)
    dim_company, dim_sector = build_dim_company(companies, sector_map)

    fact_profit_loss = build_profit_loss_fact(profitandloss)
    fact_balance_sheet = build_balance_sheet_fact(balancesheet, dim_company)
    fact_cash_flow = build_cash_flow_fact(cashflow)

    fact_profit_loss, fact_cash_flow = add_cross_table_metrics(
        fact_profit_loss=fact_profit_loss,
        fact_balance_sheet=fact_balance_sheet,
        fact_cash_flow=fact_cash_flow,
    )

    fact_analysis = build_analysis_fact(analysis)
    fact_pros_cons = build_pros_cons_fact(prosandcons)

    dim_year = build_year_dimension(fact_profit_loss, fact_balance_sheet, fact_cash_flow)

    fact_profit_loss = attach_year_id(fact_profit_loss, dim_year)
    fact_balance_sheet = attach_year_id(fact_balance_sheet, dim_year)
    fact_cash_flow = attach_year_id(fact_cash_flow, dim_year)

    dim_health_label = pd.DataFrame(DEFAULT_HEALTH_LABELS)

    docs_clean = documents.copy()
    if not docs_clean.empty:
        symbol_col = find_symbol_column(docs_clean)
        if symbol_col:
            docs_clean["symbol"] = clean_symbol(docs_clean[symbol_col])

        year_col = find_year_like_column(docs_clean)
        if year_col:
            docs_clean["year_label"] = docs_clean[year_col].apply(normalize_period_label)

    save_clean_table(dim_company, "dim_company.csv")
    save_clean_table(dim_sector, "dim_sector.csv")
    save_clean_table(dim_year, "dim_year.csv")
    save_clean_table(dim_health_label, "dim_health_label.csv")

    save_clean_table(fact_profit_loss, "fact_profit_loss.csv")
    save_clean_table(fact_balance_sheet, "fact_balance_sheet.csv")
    save_clean_table(fact_cash_flow, "fact_cash_flow.csv")
    save_clean_table(fact_analysis, "fact_analysis.csv")
    save_clean_table(fact_pros_cons, "fact_pros_cons.csv")

    if not docs_clean.empty:
        save_clean_table(docs_clean, "documents_clean.csv")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_meta = pd.DataFrame(
        [
            {
                "created_at_utc": created_at,
                "note": "Transformation completed. Review data/sector_mapping.csv for final manual sector quality check.",
            }
        ]
    )
    save_clean_table(run_meta, "_transform_run_metadata.csv")

    print("Transformation complete.")


if __name__ == "__main__":
    main()
