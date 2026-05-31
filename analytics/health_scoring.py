#!/usr/bin/env python3
"""Compute and persist ML-like health scores for Nifty 100 companies."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency at runtime
    redis = None


FEATURE_QUERY = text(
    """
    WITH latest_pl AS (
        SELECT DISTINCT ON (symbol)
            symbol,
            year_id,
            sales,
            net_profit,
            opm_pct,
            net_profit_margin_pct,
            interest_coverage,
            dividend_payout_pct
        FROM fact_profit_loss
        ORDER BY symbol, year_id DESC
    ),
    latest_bs AS (
        SELECT DISTINCT ON (symbol)
            symbol,
            year_id,
            debt_to_equity
        FROM fact_balance_sheet
        ORDER BY symbol, year_id DESC
    ),
    latest_cf AS (
        SELECT DISTINCT ON (symbol)
            symbol,
            year_id,
            free_cash_flow,
            cash_conversion_ratio
        FROM fact_cash_flow
        ORDER BY symbol, year_id DESC
    ),
    growth AS (
        SELECT
            symbol,
            MAX(CASE WHEN period_label = '3Y' THEN compounded_sales_growth_pct END) AS sales_growth_3y,
            MAX(CASE WHEN period_label = '3Y' THEN compounded_profit_growth_pct END) AS profit_growth_3y,
            MAX(CASE WHEN period_label = '3Y' THEN stock_price_cagr_pct END) AS stock_cagr_3y,
            MAX(CASE WHEN period_label = '3Y' THEN roe_pct END) AS roe_3y
        FROM fact_analysis
        GROUP BY symbol
    )
    SELECT
        c.symbol,
        pl.sales,
        pl.net_profit,
        pl.opm_pct,
        pl.net_profit_margin_pct,
        pl.interest_coverage,
        pl.dividend_payout_pct,
        bs.debt_to_equity,
        cf.free_cash_flow,
        cf.cash_conversion_ratio,
        g.sales_growth_3y,
        g.profit_growth_3y,
        g.stock_cagr_3y,
        g.roe_3y
    FROM dim_company c
    LEFT JOIN latest_pl pl ON pl.symbol = c.symbol
    LEFT JOIN latest_bs bs ON bs.symbol = c.symbol
    LEFT JOIN latest_cf cf ON cf.symbol = c.symbol
    LEFT JOIN growth g ON g.symbol = c.symbol
    ORDER BY c.symbol
    """
)

SALES_HISTORY_QUERY = text(
    """
    SELECT symbol, year_id, sales
    FROM fact_profit_loss
    WHERE sales IS NOT NULL
    ORDER BY symbol, year_id
    """
)

PREVIOUS_SCORE_QUERY = text(
    """
    SELECT DISTINCT ON (symbol) symbol, overall_score
    FROM fact_ml_scores
    ORDER BY symbol, computed_at DESC
    """
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL SQLAlchemy URL. Falls back to DATABASE_URL.",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL used for cache invalidation.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/clean/fact_ml_scores.csv",
        help="Optional path to export scores as CSV.",
    )
    return parser.parse_args()


def percentile_score(series: pd.Series, higher_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(50.0, index=series.index)

    ranked = numeric if higher_better else -numeric
    scored = ranked.rank(method="average", pct=True) * 100

    fallback = float(scored.dropna().median()) if scored.notna().sum() else 50.0
    return scored.fillna(fallback)


def assign_health_label(score: float) -> str:
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


def blend_scores(columns: Iterable[pd.Series]) -> pd.Series:
    frame = pd.concat(list(columns), axis=1)
    return frame.mean(axis=1, skipna=True).fillna(50.0)


def compute_trend_signal(sales_history: pd.DataFrame) -> Dict[str, float]:
    trends: Dict[str, float] = {}
    if sales_history.empty:
        return trends

    for symbol, group in sales_history.groupby("symbol"):
        values = pd.to_numeric(group["sales"], errors="coerce").dropna().to_numpy(dtype=float)
        if len(values) < 2:
            trends[symbol] = 0.0
            continue

        x_axis = np.arange(len(values), dtype=float)
        slope = float(np.polyfit(x_axis, values, 1)[0])
        baseline = float(np.abs(values).mean())
        trends[symbol] = (slope / baseline) * 100 if baseline else 0.0

    return trends


def fetch_feature_frame(db_url: str) -> pd.DataFrame:
    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        features = pd.read_sql_query(FEATURE_QUERY, conn)
        sales_history = pd.read_sql_query(SALES_HISTORY_QUERY, conn)

    trend_map = compute_trend_signal(sales_history)
    features["trend_signal"] = features["symbol"].map(trend_map).fillna(0.0)
    features["free_cash_flow_margin"] = (
        pd.to_numeric(features["free_cash_flow"], errors="coerce")
        / pd.to_numeric(features["sales"], errors="coerce").replace({0: np.nan})
    ) * 100

    return features


def compute_scores(feature_frame: pd.DataFrame) -> pd.DataFrame:
    frame = feature_frame.copy()

    opm_score = percentile_score(frame["opm_pct"], higher_better=True)
    npm_score = percentile_score(frame["net_profit_margin_pct"], higher_better=True)
    roe_score = percentile_score(frame["roe_3y"], higher_better=True)

    sales_growth_score = percentile_score(frame["sales_growth_3y"], higher_better=True)
    profit_growth_score = percentile_score(frame["profit_growth_3y"], higher_better=True)
    stock_cagr_score = percentile_score(frame["stock_cagr_3y"], higher_better=True)

    debt_score = percentile_score(frame["debt_to_equity"], higher_better=False)
    coverage_score = percentile_score(frame["interest_coverage"], higher_better=True)

    cash_conversion_score = percentile_score(frame["cash_conversion_ratio"], higher_better=True)
    free_cashflow_margin_score = percentile_score(frame["free_cash_flow_margin"], higher_better=True)

    dividend_score = percentile_score(frame["dividend_payout_pct"], higher_better=True)
    trend_score = percentile_score(frame["trend_signal"], higher_better=True)

    frame["profitability_score"] = blend_scores([opm_score, npm_score, roe_score])
    frame["growth_score"] = blend_scores([sales_growth_score, profit_growth_score, stock_cagr_score])
    frame["leverage_score"] = blend_scores([debt_score, coverage_score])
    frame["cashflow_score"] = blend_scores([cash_conversion_score, free_cashflow_margin_score])
    frame["dividend_score"] = dividend_score
    frame["trend_score"] = trend_score

    frame["overall_score"] = (
        frame["profitability_score"] * 0.25
        + frame["growth_score"] * 0.20
        + frame["leverage_score"] * 0.20
        + frame["cashflow_score"] * 0.15
        + frame["dividend_score"] * 0.10
        + frame["trend_score"] * 0.10
    )

    for col in [
        "overall_score",
        "profitability_score",
        "growth_score",
        "leverage_score",
        "cashflow_score",
        "dividend_score",
        "trend_score",
    ]:
        frame[col] = frame[col].clip(lower=0, upper=100).round(2)

    frame["health_label"] = frame["overall_score"].map(assign_health_label)

    return frame[
        [
            "symbol",
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


def fetch_previous_scores(db_url: str) -> pd.DataFrame:
    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        try:
            return pd.read_sql_query(PREVIOUS_SCORE_QUERY, conn)
        except Exception:
            return pd.DataFrame(columns=["symbol", "overall_score"])


def upsert_scores(db_url: str, scores: pd.DataFrame, computed_at: datetime) -> None:
    engine = create_engine(db_url, future=True)
    metadata = MetaData()

    with engine.begin() as conn:
        table = Table("fact_ml_scores", metadata, autoload_with=conn)
        payload = scores.copy()
        payload["computed_at"] = computed_at
        payload = payload.where(pd.notnull(payload), None)
        rows = payload.to_dict(orient="records")

        if not rows:
            return

        stmt = pg_insert(table).values(rows)
        update_cols = [
            "overall_score",
            "profitability_score",
            "growth_score",
            "leverage_score",
            "cashflow_score",
            "dividend_score",
            "trend_score",
            "health_label",
        ]
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "computed_at"],
            set_={col: getattr(stmt.excluded, col) for col in update_cols},
        )
        conn.execute(stmt)


def invalidate_score_cache(redis_url: str, symbols: List[str]) -> int:
    if not symbols or redis is None:
        return 0

    client = redis.from_url(redis_url, decode_responses=True)
    pipe = client.pipeline(transaction=False)

    for symbol in symbols:
        pipe.delete(f"company:{symbol}:health_score")
        pipe.delete(f"company:{symbol}:dashboard")

    pipe.execute()
    return len(symbols)


def run_scoring_pipeline(db_url: str, redis_url: str, output_csv: str) -> Dict[str, object]:
    features = fetch_feature_frame(db_url)
    if features.empty:
        raise RuntimeError("No company data found in warehouse. Run ETL load first.")

    scores = compute_scores(features)
    previous = fetch_previous_scores(db_url).rename(columns={"overall_score": "previous_overall_score"})

    comparison = scores.merge(previous, on="symbol", how="left")
    comparison["score_delta"] = comparison["overall_score"] - comparison["previous_overall_score"]
    changed_symbols = comparison.loc[comparison["score_delta"].abs() > 2, "symbol"].dropna().astype(str).tolist()

    computed_at = datetime.now(timezone.utc).replace(microsecond=0)
    upsert_scores(db_url, scores, computed_at)

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_df = scores.copy()
    export_df["computed_at"] = computed_at.isoformat()
    export_df.to_csv(output_path, index=False)

    invalidated = invalidate_score_cache(redis_url, changed_symbols)

    return {
        "rows_scored": int(len(scores)),
        "changed_symbols": int(len(changed_symbols)),
        "cache_invalidated": int(invalidated),
        "output_csv": str(output_path),
        "computed_at": computed_at.isoformat(),
    }


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise ValueError("Database URL is required. Pass --db-url or set DATABASE_URL.")

    summary = run_scoring_pipeline(
        db_url=args.db_url,
        redis_url=args.redis_url,
        output_csv=args.output_csv,
    )

    print("[health_scoring]", summary)


if __name__ == "__main__":
    main()
