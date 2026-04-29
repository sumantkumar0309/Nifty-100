from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from etl.config import CLEAN_DIR, MARKETAI_DATA_DIR, ensure_data_dirs
from etl.utils.io_helpers import normalize_columns


INPUT_FILES = {
    "dim_company": "dim_company.csv",
    "profit": "fact_profit_loss.csv",
    "balance": "fact_balance_sheet.csv",
    "cash": "fact_cash_flow.csv",
    "analysis": "fact_analysis.csv",
    "pros_cons": "fact_pros_cons.csv",
}


def read_clean_file(file_name: str) -> pd.DataFrame:
    path = CLEAN_DIR / file_name
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path)
    return normalize_columns(frame)


def latest_rows(frame: pd.DataFrame, order_column: str = "year_id") -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns or order_column not in frame.columns:
        return pd.DataFrame(columns=frame.columns)

    ordered = frame.copy()
    ordered[order_column] = pd.to_numeric(ordered[order_column], errors="coerce")
    ordered = ordered.dropna(subset=[order_column])
    if ordered.empty:
        return pd.DataFrame(columns=frame.columns)

    ordered = ordered.sort_values(["symbol", order_column])
    return ordered.groupby("symbol", as_index=False).tail(1)


def summarize_analysis(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return pd.DataFrame(columns=["symbol"])

    numeric_columns = [
        column
        for column in [
            "compounded_profit_growth_pct",
            "compounded_sales_growth_pct",
            "roe_pct",
            "stock_price_cagr_pct",
        ]
        if column in frame.columns
    ]

    if not numeric_columns:
        return pd.DataFrame(columns=["symbol"])

    analysis = frame[["symbol", *numeric_columns]].copy()
    for column in numeric_columns:
        analysis[column] = pd.to_numeric(analysis[column], errors="coerce")

    return analysis.groupby("symbol", as_index=False)[numeric_columns].mean(numeric_only=True)


def summarize_pros_cons(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return pd.DataFrame(columns=["symbol", "pro_count", "con_count", "sentiment_score"])

    source = frame[["symbol", "is_pro"]].copy()
    source["is_pro"] = source["is_pro"].astype(str).str.lower().isin({"1", "true", "t", "yes", "y"})

    summary = source.groupby("symbol", as_index=False).agg(
        pro_count=("is_pro", "sum"),
        total_count=("is_pro", "size"),
    )
    summary["con_count"] = summary["total_count"] - summary["pro_count"]
    summary["sentiment_score"] = (summary["pro_count"] - summary["con_count"]) / summary["total_count"].clip(lower=1)
    return summary[["symbol", "pro_count", "con_count", "sentiment_score"]]


def percentile_score(series: pd.Series, invert: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(50.0, index=series.index)

    ranks = numeric.rank(method="average", pct=True)
    if invert:
        ranks = 1 - ranks

    fill_value = float(ranks.dropna().median()) if ranks.notna().any() else 0.5
    return (ranks.fillna(fill_value) * 100).clip(0, 100)


def blend_scores(frame: pd.DataFrame, columns: list[tuple[str, bool]]) -> pd.Series:
    components: list[pd.Series] = []
    for column, invert in columns:
        if column in frame.columns:
            components.append(percentile_score(frame[column], invert=invert))

    if not components:
        return pd.Series(50.0, index=frame.index)

    blended = pd.concat(components, axis=1)
    return blended.mean(axis=1).fillna(50.0).clip(0, 100)


def build_scores() -> pd.DataFrame:
    dim_company = read_clean_file(INPUT_FILES["dim_company"])
    if dim_company.empty or "symbol" not in dim_company.columns:
        return pd.DataFrame()

    profit = latest_rows(read_clean_file(INPUT_FILES["profit"]))
    balance = latest_rows(read_clean_file(INPUT_FILES["balance"]))
    cash = latest_rows(read_clean_file(INPUT_FILES["cash"]))
    analysis = summarize_analysis(read_clean_file(INPUT_FILES["analysis"]))
    pros_cons = summarize_pros_cons(read_clean_file(INPUT_FILES["pros_cons"]))

    company_frame = dim_company[[column for column in ["symbol", "company_name", "sector_name"] if column in dim_company.columns]].drop_duplicates("symbol")
    frame = company_frame.copy()

    for source in [profit, balance, cash, analysis, pros_cons]:
        if not source.empty:
            frame = frame.merge(source, on="symbol", how="left")

    if "total_assets" in frame.columns and "borrowings" in frame.columns:
        frame["borrowings_to_assets"] = pd.to_numeric(frame["borrowings"], errors="coerce") / pd.to_numeric(frame["total_assets"], errors="coerce").replace({0: pd.NA})

    if "sentiment_score" in frame.columns:
        frame["sentiment_score"] = pd.to_numeric(frame["sentiment_score"], errors="coerce")

    profitability_score = blend_scores(
        frame,
        [
            ("net_profit_margin_pct", False),
            ("return_on_assets", False),
            ("interest_coverage", False),
            ("opm_pct", False),
        ],
    )
    growth_score = blend_scores(
        frame,
        [
            ("compounded_sales_growth_pct", False),
            ("compounded_profit_growth_pct", False),
            ("stock_price_cagr_pct", False),
        ],
    )
    leverage_score = blend_scores(
        frame,
        [
            ("debt_to_equity", True),
            ("equity_ratio", False),
            ("borrowings_to_assets", True),
        ],
    )
    cashflow_score = blend_scores(
        frame,
        [
            ("free_cash_flow", False),
            ("cash_conversion_ratio", False),
            ("operating_activity", False),
            ("net_cash_flow", False),
        ],
    )
    dividend_score = blend_scores(frame, [("dividend_payout_pct", False)])
    trend_score = blend_scores(
        frame,
        [
            ("stock_price_cagr_pct", False),
            ("roe_pct", False),
            ("sentiment_score", False),
        ],
    )

    overall_score = (
        (profitability_score * 0.25)
        + (growth_score * 0.20)
        + (leverage_score * 0.15)
        + (cashflow_score * 0.20)
        + (dividend_score * 0.10)
        + (trend_score * 0.10)
    ).clip(0, 100)

    scored = frame[[column for column in ["symbol", "company_name", "sector_name"] if column in frame.columns]].copy()
    scored["computed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    scored["overall_score"] = overall_score.round(4)
    scored["profitability_score"] = profitability_score.round(4)
    scored["growth_score"] = growth_score.round(4)
    scored["leverage_score"] = leverage_score.round(4)
    scored["cashflow_score"] = cashflow_score.round(4)
    scored["dividend_score"] = dividend_score.round(4)
    scored["trend_score"] = trend_score.round(4)
    scored["health_label"] = pd.cut(
        scored["overall_score"],
        bins=[-1, 40, 55, 70, 85, 100],
        labels=["POOR", "WEAK", "AVERAGE", "GOOD", "EXCELLENT"],
    ).astype(str)

    return scored.sort_values(["overall_score", "symbol"], ascending=[False, True])


def main() -> None:
    ensure_data_dirs()
    scored = build_scores()
    if scored.empty:
        raise RuntimeError("No ML scores were generated because the clean inputs were missing or empty.")

    warehouse_path = CLEAN_DIR / "fact_ml_scores.csv"
    frontend_path = MARKETAI_DATA_DIR / "ml_scores.csv"

    warehouse_columns = [
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
    scored[warehouse_columns].to_csv(warehouse_path, index=False)
    scored.to_csv(frontend_path, index=False)

    print(f"Generated ML scores for {len(scored)} companies")
    print(f"Wrote warehouse file: {warehouse_path}")
    print(f"Wrote frontend file: {frontend_path}")


if __name__ == "__main__":
    main()