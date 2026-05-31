#!/usr/bin/env python3
"""Clean and standardize raw Nifty 100 CSV files into analytics-ready datasets."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

RAW_TABLES: Sequence[str] = (
    "companies",
    "analysis",
    "balancesheet",
    "profitandloss",
    "cashflow",
    "prosandcons",
    "documents",
)

NULL_TOKENS = {"", "null", "none", "na", "n/a", "nil"}

MONTH_ALIAS = {
    "JAN": "Jan",
    "FEB": "Feb",
    "MAR": "Mar",
    "APR": "Apr",
    "MAY": "May",
    "JUN": "Jun",
    "JUL": "Jul",
    "AUG": "Aug",
    "SEP": "Sep",
    "SEPT": "Sep",
    "OCT": "Oct",
    "NOV": "Nov",
    "DEC": "Dec",
}

QUARTER_BY_MONTH = {
    "Jun": "Q1",
    "Sep": "Q2",
    "Dec": "Q3",
    "Mar": "Q4",
}

PERIOD_ALIAS = {
    "10 YEARS": "10Y",
    "10 YEAR": "10Y",
    "10Y": "10Y",
    "5 YEARS": "5Y",
    "5 YEAR": "5Y",
    "5Y": "5Y",
    "3 YEARS": "3Y",
    "3 YEAR": "3Y",
    "3Y": "3Y",
    "TTM": "TTM",
}

DEFAULT_SECTOR_MAP: Dict[str, str] = {
    "ABB": "Holding Company",
    "ABCAPITAL": "NBFC",
    "ABFRL": "Consumer Goods",
    "ACC": "Cement",
    "ADANIENSOL": "Energy",
    "ADANIENT": "Holding Company",
    "ADANIGREEN": "Energy",
    "ADANIPORTS": "Ports",
    "ADANIPOWER": "Power",
    "AMBUJACEM": "Cement",
    "APOLLOHOSP": "Healthcare",
    "ASIANPAINT": "Paint",
    "AUROPHARMA": "Healthcare",
    "AXISBANK": "Banking",
    "BAJAJ-AUTO": "Auto",
    "BAJAJFINSV": "NBFC",
    "BAJFINANCE": "NBFC",
    "BANDHANBNK": "Banking",
    "BANKBARODA": "Banking",
    "BEL": "Holding Company",
    "BHARATFORG": "Auto",
    "BHARTIARTL": "Holding Company",
    "BHEL": "Holding Company",
    "BIOCON": "Healthcare",
    "BOSCHLTD": "Auto",
    "BRITANNIA": "Consumer Goods",
    "CANBK": "Banking",
    "CHOLAFIN": "NBFC",
    "CIPLA": "Healthcare",
    "COALINDIA": "Energy",
    "COLPAL": "Consumer Goods",
    "CONCOR": "Ports",
    "CUMMINSIND": "Holding Company",
    "DABUR": "Consumer Goods",
    "DIVISLAB": "Healthcare",
    "DLF": "Holding Company",
    "DRREDDY": "Healthcare",
    "EICHERMOT": "Auto",
    "GAIL": "Energy",
    "GLAND": "Healthcare",
    "GODREJCP": "Consumer Goods",
    "GRASIM": "Holding Company",
    "HAVELLS": "Consumer Goods",
    "HCLTECH": "IT",
    "HDFCAMC": "NBFC",
    "HDFCBANK": "Banking",
    "HDFCLIFE": "Insurance",
    "HEROMOTOCO": "Auto",
    "HINDALCO": "Holding Company",
    "HINDPETRO": "Energy",
    "HINDUNILVR": "Consumer Goods",
    "ICICIBANK": "Banking",
    "ICICIGI": "Insurance",
    "ICICIPRULI": "Insurance",
    "IDFCFIRSTB": "Banking",
    "IGL": "Energy",
    "INDHOTEL": "Consumer Goods",
    "INDIGO": "Holding Company",
    "INDUSINDBK": "Banking",
    "INFY": "IT",
    "IOC": "Energy",
    "IRCTC": "Consumer Goods",
    "ITC": "Consumer Goods",
    "JINDALSTEL": "Holding Company",
    "JSWENERGY": "Power",
    "JSWSTEEL": "Holding Company",
    "JUBLFOOD": "Consumer Goods",
    "KOTAKBANK": "Banking",
    "LT": "Holding Company",
    "LTIM": "IT",
    "LTTS": "IT",
    "LUPIN": "Healthcare",
    "M&M": "Auto",
    "MARICO": "Consumer Goods",
    "MARUTI": "Auto",
    "MCDOWELL-N": "Consumer Goods",
    "MOTHERSON": "Auto",
    "MPHASIS": "IT",
    "NAUKRI": "Holding Company",
    "NESTLEIND": "Consumer Goods",
    "NHPC": "Power",
    "NMDC": "Holding Company",
    "NTPC": "Power",
    "OBEROIRLTY": "Holding Company",
    "ONGC": "Energy",
    "PAGEIND": "Consumer Goods",
    "PEL": "NBFC",
    "PERSISTENT": "IT",
    "PETRONET": "Energy",
    "PFC": "NBFC",
    "PIDILITIND": "Consumer Goods",
    "PIIND": "Holding Company",
    "PNB": "Banking",
    "POLYCAB": "Holding Company",
    "POWERGRID": "Power",
    "RAMCOCEM": "Cement",
    "RECLTD": "NBFC",
    "RELIANCE": "Energy",
    "SAIL": "Holding Company",
    "SBICARD": "NBFC",
    "SBILIFE": "Insurance",
    "SBIN": "Banking",
    "SHREECEM": "Cement",
    "SIEMENS": "Holding Company",
    "SRF": "Holding Company",
    "SUNPHARMA": "Healthcare",
    "TATACONSUM": "Consumer Goods",
    "TATAMOTORS": "Auto",
    "TATAPOWER": "Power",
    "TATASTEEL": "Holding Company",
    "TCS": "IT",
    "TECHM": "IT",
    "TITAN": "Consumer Goods",
    "TORNTPHARM": "Healthcare",
    "TRENT": "Consumer Goods",
    "TVSMOTOR": "Auto",
    "ULTRACEMCO": "Cement",
    "UPL": "Holding Company",
    "VEDL": "Energy",
    "VOLTAS": "Consumer Goods",
    "WIPRO": "IT",
    "ZOMATO": "Consumer Goods",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default="data/raw", help="Directory containing extracted raw CSV files.")
    parser.add_argument("--clean-dir", default="data/clean", help="Directory to write cleaned CSV files.")
    parser.add_argument(
        "--sector-mapping",
        default="data/sector_mapping.csv",
        help="Path to sector mapping file.",
    )
    return parser.parse_args()


def to_snake_case(name: str) -> str:
    value = re.sub(r"[^0-9A-Za-z]+", "_", str(name))
    value = re.sub(r"_+", "_", value)
    return value.strip("_").lower()


def clean_string_value(value: object) -> object:
    if pd.isna(value):
        return np.nan

    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if text.lower() in NULL_TOKENS:
        return np.nan
    return text


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out.columns = [to_snake_case(col) for col in out.columns]

    for col in out.select_dtypes(include="object").columns:
        out[col] = out[col].map(clean_string_value)
    return out


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


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace({0: np.nan})
    return numerator / denominator


def first_existing(df: pd.DataFrame, options: Sequence[str]) -> Optional[str]:
    for name in options:
        if name in df.columns:
            return name
    return None


def ensure_symbol_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    source = first_existing(out, ["symbol", "company_id", "companyid", "ticker", "code"])
    if source and source != "symbol":
        out["symbol"] = out[source]

    if "symbol" in out.columns:
        out["symbol"] = out["symbol"].where(out["symbol"].notna(), np.nan)
        out["symbol"] = out["symbol"].map(lambda v: v.upper().strip() if isinstance(v, str) else v)
    return out


def normalize_year_label(raw_value: object) -> Tuple[object, object, object, bool, bool, object]:
    if pd.isna(raw_value):
        return (np.nan, np.nan, np.nan, False, False, np.nan)

    token = str(raw_value).strip()
    if not token:
        return (np.nan, np.nan, np.nan, False, False, np.nan)

    if token.upper() == "TTM":
        return ("TTM", np.nan, np.nan, True, False, 999999)

    fy_match = re.match(r"^FY\s*([0-9]{2,4})$", token, flags=re.IGNORECASE)
    if fy_match:
        year_value = int(fy_match.group(1))
        if year_value < 100:
            year_value += 2000
        return (f"Mar {year_value}", year_value, "Q4", False, False, year_value * 10 + 4)

    normalized = re.sub(r"[-_/]", " ", token)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    month_year_match = re.match(r"^([A-Za-z]{3,9})\s*([0-9]{2,4})$", normalized)
    if month_year_match:
        month = month_year_match.group(1)[:4].upper()
        month = MONTH_ALIAS.get(month, month_year_match.group(1)[:3].title())

        year_value = int(month_year_match.group(2))
        if year_value < 100:
            year_value += 2000

        quarter = QUARTER_BY_MONTH.get(month)
        quarter_rank = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(quarter, 0)
        is_half_year = quarter == "Q2"
        sort_order = year_value * 10 + quarter_rank
        return (f"{month} {year_value}", year_value, quarter, False, is_half_year, sort_order)

    year_match = re.match(r"^([0-9]{4})$", normalized)
    if year_match:
        year_value = int(year_match.group(1))
        return (f"Mar {year_value}", year_value, "Q4", False, False, year_value * 10 + 4)

    parsed_date = pd.to_datetime(token, errors="coerce")
    if not pd.isna(parsed_date):
        month = parsed_date.strftime("%b")
        year_value = int(parsed_date.year)
        quarter = QUARTER_BY_MONTH.get(month)
        quarter_rank = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(quarter, 0)
        is_half_year = quarter == "Q2"
        return (f"{month} {year_value}", year_value, quarter, False, is_half_year, year_value * 10 + quarter_rank)

    return (token, np.nan, np.nan, False, False, np.nan)


def add_year_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    year_col = first_existing(out, ["year_label", "year", "period_end", "period", "as_on", "date"]) 
    if not year_col:
        return out

    parsed = out[year_col].map(normalize_year_label)
    parsed_df = pd.DataFrame(
        parsed.tolist(),
        columns=["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"],
        index=out.index,
    )
    for col in parsed_df.columns:
        out[col] = parsed_df[col]
    return out


def canonicalize_columns(df: pd.DataFrame, alias_map: Dict[str, Sequence[str]]) -> pd.DataFrame:
    out = df.copy()
    for canonical, aliases in alias_map.items():
        if canonical in out.columns:
            continue
        source = first_existing(out, aliases)
        if source:
            out[canonical] = out[source]
    return out


def infer_sector(symbol: str, company_name: str) -> str:
    symbol = (symbol or "").upper()
    text = f"{symbol} {(company_name or '').upper()}"

    keyword_map = [
        ("Banking", ["BANK", "SBIN", "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK"]),
        ("Insurance", ["INSURANCE", "LIFE", "PRU", "GI"]),
        ("IT", ["TECH", "INFY", "TCS", "WIPRO", "LTIM", "MPHASIS", "PERSISTENT"]),
        ("Power", ["POWERGRID", "NTPC", "NHPC", "POWER"]),
        ("Energy", ["ENERGY", "OIL", "GAS", "ONGC", "PETRO", "RELIANCE", "GAIL", "IOC"]),
        ("Ports", ["PORT", "CONCOR", "SHIPPING"]),
        ("Cement", ["CEMENT", "CEM"]),
        ("Healthcare", ["PHARMA", "HOSP", "HEALTH", "MED", "BIO"]),
        ("Auto", ["AUTO", "MOTOR", "MOTORS", "TYRE", "FORGE"]),
        ("Paint", ["PAINT"]),
        ("NBFC", ["FINANCE", "CAPITAL", "FINSERV", "HOUSING", "AMC", "CARD"]),
        (
            "Consumer Goods",
            ["CONSUM", "FOOD", "BREWER", "RETAIL", "HOTEL", "APPAREL", "UNILEVER", "ITC", "NESTLE", "BRITANNIA"],
        ),
    ]

    for sector_name, keywords in keyword_map:
        if any(keyword in text for keyword in keywords):
            return sector_name

    return "Holding Company"


def normalize_companies(df: pd.DataFrame, sector_mapping_path: Path) -> pd.DataFrame:
    out = df.copy()

    if "company_name" not in out.columns:
        source_name_col = first_existing(out, ["name", "company", "companyname"])
        if source_name_col:
            out["company_name"] = out[source_name_col]

    if "company_name" in out.columns:
        out["company_name"] = (
            out["company_name"].astype(str).str.replace("\\r", " ", regex=False).str.replace("\\n", " ", regex=False).str.strip()
        )

    if sector_mapping_path.exists():
        sector_mapping = pd.read_csv(sector_mapping_path)
    else:
        sector_mapping = pd.DataFrame(columns=["symbol", "sector", "sub_sector"])

    sector_mapping = normalize_dataframe(sector_mapping)
    if "symbol" in sector_mapping.columns:
        sector_mapping["symbol"] = sector_mapping["symbol"].map(lambda v: v.upper().strip() if isinstance(v, str) else v)

    mapping_dict = dict(DEFAULT_SECTOR_MAP)
    if not sector_mapping.empty and {"symbol", "sector"}.issubset(sector_mapping.columns):
        for row in sector_mapping[["symbol", "sector"]].dropna().itertuples(index=False):
            mapping_dict[row.symbol] = row.sector

    if "symbol" not in out.columns:
        out["symbol"] = np.nan

    symbols = out["symbol"].dropna().unique().tolist()
    records: List[Dict[str, object]] = []
    name_lookup = (
        out[["symbol", "company_name"]]
        .dropna(subset=["symbol"])
        .drop_duplicates(subset=["symbol"])
        .set_index("symbol")["company_name"]
        .to_dict()
    )

    for symbol in sorted(symbols):
        company_name = str(name_lookup.get(symbol, ""))
        sector = mapping_dict.get(symbol) or infer_sector(symbol, company_name)
        records.append(
            {
                "symbol": symbol,
                "sector": sector,
                "sub_sector": np.nan,
            }
        )

    merged_mapping = pd.DataFrame(records)
    merged_mapping.to_csv(sector_mapping_path, index=False)

    out = out.merge(merged_mapping, on="symbol", how="left")
    return out


def parse_period_value(raw_value: object) -> Tuple[object, object]:
    if pd.isna(raw_value):
        return (np.nan, np.nan)

    text = str(raw_value).strip()
    if not text:
        return (np.nan, np.nan)

    match = re.search(
        r"(?P<period>10\s*Years?|5\s*Years?|3\s*Years?|TTM)\s*:?\s*(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*%?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        period_token = match.group("period").upper().replace("  ", " ").strip()
        period = PERIOD_ALIAS.get(period_token, period_token)
        return (period, float(match.group("value")))

    numeric = pd.to_numeric(text.replace("%", "").replace(",", ""), errors="coerce")
    return (np.nan, numeric)


def normalize_period_label(value: object) -> object:
    if pd.isna(value):
        return np.nan
    token = str(value).upper().strip()
    token = re.sub(r"\s+", " ", token)
    return PERIOD_ALIAS.get(token, token)


def normalize_analysis(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    metric_cols = [
        col
        for col in out.columns
        if col not in {"symbol", "company_id", "company_name", "period", "period_label", "year_label", "fiscal_year", "sort_order"}
    ]

    for col in metric_cols:
        if out[col].dtype != "object":
            continue
        parsed = out[col].map(parse_period_value)
        periods = parsed.map(lambda x: x[0])
        values = parsed.map(lambda x: x[1])
        if values.notna().sum() == 0:
            continue
        out[f"{col}_period_label"] = periods
        out[f"{col}_value_pct"] = values

    if "period_label" not in out.columns:
        period_cols = [col for col in out.columns if col.endswith("_period_label")]
        if period_cols:
            out["period_label"] = out[period_cols].bfill(axis=1).iloc[:, 0]

    if "period_label" in out.columns:
        out["period_label"] = out["period_label"].map(normalize_period_label)

    metric_lookup = {
        "compounded_sales_growth_pct": ["sales_growth", "sales_cagr", "compounded_sales_growth"],
        "compounded_profit_growth_pct": ["profit_growth", "profit_cagr", "compounded_profit_growth"],
        "stock_price_cagr_pct": ["stock", "cagr", "price"],
        "roe_pct": ["roe"],
    }

    for target_col, keywords in metric_lookup.items():
        if target_col in out.columns:
            out[target_col] = to_numeric(out[target_col])
            continue

        candidate_cols = [
            col
            for col in out.columns
            if col.endswith("_value_pct") and all(keyword in col for keyword in keywords)
        ]
        if not candidate_cols:
            candidate_cols = [col for col in out.columns if all(keyword in col for keyword in keywords)]

        if candidate_cols:
            out[target_col] = to_numeric(out[candidate_cols[0]])
        else:
            out[target_col] = np.nan

    return out


def merge_keys(left: pd.DataFrame, right: pd.DataFrame) -> List[str]:
    candidates = [["symbol", "year_label"], ["symbol", "fiscal_year"], ["symbol", "sort_order"]]
    for keys in candidates:
        if all(k in left.columns for k in keys) and all(k in right.columns for k in keys):
            return keys
    return []


def compute_balance_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = canonicalize_columns(
        df,
        {
            "equity_capital": ["equity_share_capital", "share_capital", "equity"],
            "reserves": ["reserves_and_surplus", "reserves_surplus"],
            "borrowings": ["total_borrowings", "debt"],
            "other_liabilities": ["liabilities_other", "otherliabilities"],
            "total_liabilities": ["liabilities", "liabilities_total"],
            "fixed_assets": ["fixed_asset", "net_fixed_assets"],
            "cwip": ["capital_work_in_progress"],
            "investments": ["investment", "total_investments"],
            "other_assets": ["assets_other"],
            "total_assets": ["assets_total", "assets"],
            "shares_outstanding": ["shares", "no_of_shares", "shares_no"],
        },
    )

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
        "shares_outstanding",
    ]:
        if col in out.columns:
            out[col] = to_numeric(out[col])

    equity_base = out.get("equity_capital", pd.Series(np.nan, index=out.index)).fillna(0) + out.get(
        "reserves", pd.Series(np.nan, index=out.index)
    ).fillna(0)
    borrowings = out.get("borrowings", pd.Series(np.nan, index=out.index))
    total_assets = out.get("total_assets", pd.Series(np.nan, index=out.index))

    out["debt_to_equity"] = safe_divide(borrowings, equity_base)
    out["equity_ratio"] = safe_divide(equity_base, total_assets)

    if "shares_outstanding" in out.columns:
        out["book_value_per_share"] = safe_divide(equity_base, out["shares_outstanding"])

    return out


def compute_profit_metrics(df: pd.DataFrame, balance_df: pd.DataFrame) -> pd.DataFrame:
    out = canonicalize_columns(
        df,
        {
            "sales": ["revenue", "net_sales"],
            "expenses": ["total_expenses", "expense"],
            "operating_profit": ["operating_income", "ebitda"],
            "other_income": ["otherincome"],
            "interest": ["finance_cost", "interest_cost"],
            "depreciation": ["depreciation_amortization", "depriciation"],
            "profit_before_tax": ["pbt", "profit_before_tax_before_exceptional_items"],
            "tax_pct": ["tax_rate", "tax"],
            "net_profit": ["pat", "profit_after_tax", "netprofit"],
            "eps": ["earning_per_share"],
            "dividend_payout_pct": ["dividend_payout", "dividend"],
        },
    )

    for col in [
        "sales",
        "expenses",
        "operating_profit",
        "other_income",
        "interest",
        "depreciation",
        "profit_before_tax",
        "tax_pct",
        "net_profit",
        "eps",
        "dividend_payout_pct",
    ]:
        if col in out.columns:
            out[col] = to_numeric(out[col])

    sales = out.get("sales", pd.Series(np.nan, index=out.index))
    expenses = out.get("expenses", pd.Series(np.nan, index=out.index))
    operating_profit = out.get("operating_profit", pd.Series(np.nan, index=out.index))
    interest = out.get("interest", pd.Series(np.nan, index=out.index))
    net_profit = out.get("net_profit", pd.Series(np.nan, index=out.index))

    out["net_profit_margin_pct"] = safe_divide(net_profit, sales) * 100
    out["expense_ratio_pct"] = safe_divide(expenses, sales) * 100
    out["interest_coverage"] = safe_divide(operating_profit, interest)

    keys = merge_keys(out, balance_df)
    if keys:
        asset_base = balance_df[keys + ["total_assets"]].drop_duplicates(keys)
        out = out.merge(asset_base, on=keys, how="left", suffixes=("", "_bs"))
        out["asset_turnover"] = safe_divide(out["sales"], out["total_assets"])
        out["return_on_assets"] = safe_divide(out["net_profit"], out["total_assets"]) * 100

    return out


def compute_cashflow_metrics(df: pd.DataFrame, profit_df: pd.DataFrame) -> pd.DataFrame:
    out = canonicalize_columns(
        df,
        {
            "operating_activity": ["cash_from_operating_activity", "cash_flow_from_operating_activities"],
            "investing_activity": ["cash_from_investing_activity", "cash_flow_from_investing_activities"],
            "financing_activity": ["cash_from_financing_activity", "cash_flow_from_financing_activities"],
            "net_cash_flow": ["net_increase_in_cash", "netchangeincash"],
        },
    )

    for col in ["operating_activity", "investing_activity", "financing_activity", "net_cash_flow"]:
        if col in out.columns:
            out[col] = to_numeric(out[col])

    operating = out.get("operating_activity", pd.Series(np.nan, index=out.index))
    investing = out.get("investing_activity", pd.Series(np.nan, index=out.index))
    out["free_cash_flow"] = operating + investing

    keys = merge_keys(out, profit_df)
    if keys and "net_profit" in profit_df.columns:
        joined = profit_df[keys + ["net_profit"]].drop_duplicates(keys)
        out = out.merge(joined, on=keys, how="left", suffixes=("", "_pl"))
        out["cash_conversion_ratio"] = safe_divide(out["operating_activity"], out["net_profit"])

    return out


def build_dim_year(clean_tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    year_frames: List[pd.DataFrame] = []
    for df in clean_tables.values():
        cols = ["year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]
        if all(col in df.columns for col in cols):
            subset = df[cols].dropna(subset=["year_label"]).copy()
            year_frames.append(subset)

    if not year_frames:
        return pd.DataFrame(columns=["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"])

    dim_year = pd.concat(year_frames, ignore_index=True).drop_duplicates(subset=["year_label"]).copy()
    dim_year = dim_year.sort_values(by=["sort_order", "year_label"], na_position="last").reset_index(drop=True)
    dim_year["year_id"] = np.arange(1, len(dim_year) + 1)
    return dim_year[["year_id", "year_label", "fiscal_year", "quarter", "is_ttm", "is_half_year", "sort_order"]]


def load_raw_tables(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    tables: Dict[str, pd.DataFrame] = {}
    for table in RAW_TABLES:
        path = raw_dir / f"{table}.csv"
        if path.exists():
            tables[table] = pd.read_csv(path, dtype=str)
        else:
            tables[table] = pd.DataFrame()
    return tables


def save_clean_tables(clean_tables: Dict[str, pd.DataFrame], clean_dir: Path) -> None:
    clean_dir.mkdir(parents=True, exist_ok=True)
    for table, df in clean_tables.items():
        output_path = clean_dir / f"{table}.csv"
        df.to_csv(output_path, index=False)
        print(f"[{table}] rows={len(df)} columns={list(df.columns)}")


def main() -> None:
    args = parse_args()
    raw_dir = Path(args.raw_dir)
    clean_dir = Path(args.clean_dir)
    sector_mapping_path = Path(args.sector_mapping)

    raw_tables = load_raw_tables(raw_dir)

    clean_tables: Dict[str, pd.DataFrame] = {}
    for table_name, df in raw_tables.items():
        current = normalize_dataframe(df)
        current = ensure_symbol_column(current)
        current = add_year_fields(current)
        clean_tables[table_name] = current

    if "companies" in clean_tables:
        clean_tables["companies"] = normalize_companies(clean_tables["companies"], sector_mapping_path)

    if "analysis" in clean_tables:
        clean_tables["analysis"] = normalize_analysis(clean_tables["analysis"])

    if "balancesheet" in clean_tables:
        clean_tables["balancesheet"] = compute_balance_metrics(clean_tables["balancesheet"])

    if "profitandloss" in clean_tables:
        clean_tables["profitandloss"] = compute_profit_metrics(
            clean_tables["profitandloss"],
            clean_tables.get("balancesheet", pd.DataFrame()),
        )

    if "cashflow" in clean_tables:
        clean_tables["cashflow"] = compute_cashflow_metrics(
            clean_tables["cashflow"],
            clean_tables.get("profitandloss", pd.DataFrame()),
        )

    dim_year = build_dim_year(clean_tables)
    clean_tables["dim_year"] = dim_year

    save_clean_tables(clean_tables, clean_dir)


if __name__ == "__main__":
    main()
