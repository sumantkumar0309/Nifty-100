from __future__ import annotations

from typing import Dict, Iterable, List

from django.conf import settings
from sqlalchemy import create_engine, text


def _engine():
    db_url = settings.WAREHOUSE_DATABASE_URL
    if not db_url:
        raise RuntimeError("WAREHOUSE_DATABASE_URL/DATABASE_URL is not configured.")
    return create_engine(db_url, future=True)


def _rows(query: str, params: Dict[str, object] | None = None) -> List[Dict[str, object]]:
    with _engine().connect() as conn:
        result = conn.execute(text(query), params or {})
        return [dict(row._mapping) for row in result]


def _scalar(query: str, params: Dict[str, object] | None = None) -> float:
    with _engine().connect() as conn:
        result = conn.execute(text(query), params or {})
        value = result.scalar_one_or_none()
    if value is None:
        return 0.0
    return float(value)


def _normalize_symbols(symbols: Iterable[str], max_items: int) -> List[str]:
    values = [symbol.upper().strip() for symbol in symbols if symbol]
    return values[:max_items]


def fetch_company_full(symbol: str) -> Dict[str, object]:
    symbol = symbol.upper().strip()
    company = _rows("SELECT * FROM dim_company WHERE symbol = :symbol", {"symbol": symbol})
    if not company:
        return {}

    profit = _rows(
        """
        SELECT y.year_label, y.sort_order, pl.*
        FROM fact_profit_loss pl
        JOIN dim_year y ON y.year_id = pl.year_id
        WHERE pl.symbol = :symbol
        ORDER BY y.sort_order
        """,
        {"symbol": symbol},
    )
    balance = _rows(
        """
        SELECT y.year_label, y.sort_order, bs.*
        FROM fact_balance_sheet bs
        JOIN dim_year y ON y.year_id = bs.year_id
        WHERE bs.symbol = :symbol
        ORDER BY y.sort_order
        """,
        {"symbol": symbol},
    )
    cashflow = _rows(
        """
        SELECT y.year_label, y.sort_order, cf.*
        FROM fact_cash_flow cf
        JOIN dim_year y ON y.year_id = cf.year_id
        WHERE cf.symbol = :symbol
        ORDER BY y.sort_order
        """,
        {"symbol": symbol},
    )
    scores = _rows(
        """
        SELECT * FROM fact_ml_scores
        WHERE symbol = :symbol
        ORDER BY computed_at DESC
        LIMIT 10
        """,
        {"symbol": symbol},
    )
    growth = _rows(
        """
        SELECT period_label, compounded_sales_growth_pct, compounded_profit_growth_pct, stock_price_cagr_pct, roe_pct
        FROM fact_analysis
        WHERE symbol = :symbol
        ORDER BY CASE period_label WHEN '10Y' THEN 1 WHEN '5Y' THEN 2 WHEN '3Y' THEN 3 WHEN 'TTM' THEN 4 ELSE 99 END
        """,
        {"symbol": symbol},
    )
    pros_cons = _rows(
        """
        SELECT symbol, is_pro, category, text, source, confidence, generated_at
        FROM fact_pros_cons
        WHERE symbol = :symbol
        ORDER BY generated_at DESC NULLS LAST
        """,
        {"symbol": symbol},
    )

    try:
        documents = _rows(
            """
            SELECT symbol, year_label, document_url
            FROM fact_documents
            WHERE symbol = :symbol
            ORDER BY year_label DESC
            """,
            {"symbol": symbol},
        )
    except Exception:
        documents = []

    return {
        "company": company[0],
        "profitandloss": profit,
        "balancesheet": balance,
        "cashflow": cashflow,
        "growth": growth,
        "scores": scores,
        "pros_cons": pros_cons,
        "documents": documents,
    }


def fetch_home_payload(featured_limit: int = 6, ticker_limit: int = 15) -> Dict[str, object]:
    featured = _rows(
        """
        WITH latest_scores AS (
            SELECT DISTINCT ON (symbol) symbol, overall_score, health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ),
        latest_pl AS (
            SELECT DISTINCT ON (symbol) symbol, sales, net_profit, opm_pct
            FROM fact_profit_loss
            ORDER BY symbol, year_id DESC
        )
        SELECT
            c.symbol,
            c.company_name,
            c.sector,
            c.company_logo,
            s.overall_score,
            s.health_label,
            p.sales,
            p.net_profit,
            p.opm_pct
        FROM dim_company c
        LEFT JOIN latest_scores s ON s.symbol = c.symbol
        LEFT JOIN latest_pl p ON p.symbol = c.symbol
        ORDER BY random()
        LIMIT :limit
        """,
        {"limit": featured_limit},
    )

    sectors = _rows(
        """
        WITH latest_scores AS (
            SELECT DISTINCT ON (symbol) symbol, overall_score
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        )
        SELECT
            c.sector,
            COUNT(*) AS company_count,
            ROUND(AVG(s.overall_score)::numeric, 2) AS avg_health_score
        FROM dim_company c
        LEFT JOIN latest_scores s ON s.symbol = c.symbol
        GROUP BY c.sector
        ORDER BY c.sector
        """
    )

    ticker = _rows(
        """
        SELECT symbol, is_pro, text, generated_at
        FROM fact_pros_cons
        ORDER BY generated_at DESC NULLS LAST
        LIMIT :limit
        """,
        {"limit": ticker_limit},
    )

    return {
        "featured_companies": featured,
        "sector_overview": sectors,
        "live_insights": ticker,
    }


def fetch_company_list(
    filters: Dict[str, object],
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "overall_score",
    sort_order: str = "desc",
) -> Dict[str, object]:
    conditions: List[str] = []
    params: Dict[str, object] = {}

    if filters.get("sector"):
        conditions.append("base.sector = :sector")
        params["sector"] = str(filters["sector"])

    if filters.get("health_label"):
        conditions.append("base.health_label = :health_label")
        params["health_label"] = str(filters["health_label"]).upper()

    if filters.get("search"):
        conditions.append("(base.symbol ILIKE :search OR base.company_name ILIKE :search)")
        params["search"] = f"%{str(filters['search']).strip()}%"

    if filters.get("min_health_score") is not None:
        conditions.append("base.overall_score >= :min_health_score")
        params["min_health_score"] = float(filters["min_health_score"])

    sort_map = {
        "symbol": "base.symbol",
        "company_name": "base.company_name",
        "sector": "base.sector",
        "overall_score": "base.overall_score",
        "opm_pct": "base.opm_pct",
        "debt_to_equity": "base.debt_to_equity",
        "sales_growth_3y": "base.sales_growth_3y",
        "roe_pct": "base.roe_pct",
    }
    sort_column = sort_map.get(sort_by, "base.overall_score")
    direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    offset = max(page - 1, 0) * page_size
    params.update({"limit": int(page_size), "offset": int(offset)})

    base_query = f"""
        WITH latest_scores AS (
            SELECT DISTINCT ON (symbol) symbol, overall_score, health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ),
        latest_pl AS (
            SELECT DISTINCT ON (symbol) symbol, opm_pct
            FROM fact_profit_loss
            ORDER BY symbol, year_id DESC
        ),
        latest_bs AS (
            SELECT DISTINCT ON (symbol) symbol, debt_to_equity
            FROM fact_balance_sheet
            ORDER BY symbol, year_id DESC
        ),
        growth AS (
            SELECT
                symbol,
                compounded_sales_growth_pct AS sales_growth_3y,
                roe_pct
            FROM fact_analysis
            WHERE period_label = '3Y'
        )
        SELECT
            c.symbol,
            c.company_name,
            c.sector,
            c.company_logo,
            s.overall_score,
            s.health_label,
            p.opm_pct,
            b.debt_to_equity,
            g.sales_growth_3y,
            g.roe_pct
        FROM dim_company c
        LEFT JOIN latest_scores s ON s.symbol = c.symbol
        LEFT JOIN latest_pl p ON p.symbol = c.symbol
        LEFT JOIN latest_bs b ON b.symbol = c.symbol
        LEFT JOIN growth g ON g.symbol = c.symbol
    """

    data_query = f"""
        SELECT *
        FROM ({base_query}) AS base
        {where_sql}
        ORDER BY {sort_column} {direction} NULLS LAST, base.symbol
        LIMIT :limit OFFSET :offset
    """

    count_query = f"""
        SELECT COUNT(*)
        FROM ({base_query}) AS base
        {where_sql}
    """

    items = _rows(data_query, params)
    total = int(_scalar(count_query, params))

    return {
        "items": items,
        "page": int(page),
        "page_size": int(page_size),
        "total": total,
        "pages": max((total + page_size - 1) // page_size, 1),
    }


def fetch_company_charts(symbol: str) -> Dict[str, object]:
    payload = fetch_company_full(symbol)
    if not payload:
        return {}

    pl_rows = payload["profitandloss"]
    bs_rows = payload["balancesheet"]
    cf_rows = payload["cashflow"]
    growth_rows = payload["growth"]
    score_rows = list(reversed(payload["scores"]))

    years = [row.get("year_label") for row in pl_rows]

    chart_data = {
        "revenue_profit_trend": {
            "labels": years,
            "sales": [row.get("sales") for row in pl_rows],
            "net_profit": [row.get("net_profit") for row in pl_rows],
            "opm_pct": [row.get("opm_pct") for row in pl_rows],
        },
        "balance_sheet_composition": {
            "labels": [row.get("year_label") for row in bs_rows],
            "equity": [row.get("equity_capital") for row in bs_rows],
            "reserves": [row.get("reserves") for row in bs_rows],
            "borrowings": [row.get("borrowings") for row in bs_rows],
            "other_liabilities": [row.get("other_liabilities") for row in bs_rows],
        },
        "cash_flow_waterfall": {
            "labels": [row.get("year_label") for row in cf_rows],
            "operating_activity": [row.get("operating_activity") for row in cf_rows],
            "investing_activity": [row.get("investing_activity") for row in cf_rows],
            "financing_activity": [row.get("financing_activity") for row in cf_rows],
            "free_cash_flow": [row.get("free_cash_flow") for row in cf_rows],
        },
        "eps_dividend_history": {
            "labels": years,
            "eps": [row.get("eps") for row in pl_rows],
            "dividend_payout_pct": [row.get("dividend_payout_pct") for row in pl_rows],
        },
        "debt_equity": {
            "labels": [row.get("year_label") for row in bs_rows],
            "borrowings": [row.get("borrowings") for row in bs_rows],
            "equity_plus_reserves": [
                (row.get("equity_capital") or 0) + (row.get("reserves") or 0) for row in bs_rows
            ],
            "debt_to_equity": [row.get("debt_to_equity") for row in bs_rows],
        },
        "cagr_radar": {
            "labels": [row.get("period_label") for row in growth_rows],
            "sales_growth": [row.get("compounded_sales_growth_pct") for row in growth_rows],
            "profit_growth": [row.get("compounded_profit_growth_pct") for row in growth_rows],
            "stock_cagr": [row.get("stock_price_cagr_pct") for row in growth_rows],
        },
        "margin_trend": {
            "labels": years,
            "opm_pct": [row.get("opm_pct") for row in pl_rows],
            "net_profit_margin_pct": [row.get("net_profit_margin_pct") for row in pl_rows],
            "expense_ratio_pct": [row.get("expense_ratio_pct") for row in pl_rows],
        },
        "health_score": {
            "current": payload["scores"][0] if payload["scores"] else None,
            "trend_labels": [str(row.get("computed_at")) for row in score_rows],
            "trend_scores": [row.get("overall_score") for row in score_rows],
            "sub_scores": payload["scores"][0] if payload["scores"] else None,
        },
    }

    return chart_data


def fetch_compare(symbols: Iterable[str]) -> Dict[str, object]:
    normalized = _normalize_symbols(symbols, max_items=4)
    if not normalized:
        return {"items": [], "trend": []}

    metrics = _rows(
        """
        WITH latest_scores AS (
            SELECT DISTINCT ON (symbol) symbol, overall_score, health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ),
        latest_pl AS (
            SELECT DISTINCT ON (symbol) symbol, year_id, sales, net_profit, opm_pct, eps, dividend_payout_pct
            FROM fact_profit_loss
            ORDER BY symbol, year_id DESC
        ),
        latest_bs AS (
            SELECT DISTINCT ON (symbol) symbol, year_id, debt_to_equity
            FROM fact_balance_sheet
            ORDER BY symbol, year_id DESC
        ),
        growth AS (
            SELECT symbol,
                MAX(CASE WHEN period_label = '3Y' THEN compounded_sales_growth_pct END) AS sales_growth_3y,
                MAX(CASE WHEN period_label = '3Y' THEN compounded_profit_growth_pct END) AS profit_growth_3y,
                MAX(CASE WHEN period_label = '3Y' THEN roe_pct END) AS roe_pct
            FROM fact_analysis
            GROUP BY symbol
        )
        SELECT
            c.symbol,
            c.company_name,
            c.sector,
            p.sales,
            p.net_profit,
            p.opm_pct,
            g.roe_pct,
            b.debt_to_equity,
            g.sales_growth_3y,
            g.profit_growth_3y,
            p.eps,
            p.dividend_payout_pct,
            s.overall_score,
            s.health_label
        FROM dim_company c
        LEFT JOIN latest_pl p ON p.symbol = c.symbol
        LEFT JOIN latest_bs b ON b.symbol = c.symbol
        LEFT JOIN latest_scores s ON s.symbol = c.symbol
        LEFT JOIN growth g ON g.symbol = c.symbol
        WHERE c.symbol = ANY(string_to_array(:symbols_csv, ','))
        ORDER BY c.symbol
        """,
        {"symbols_csv": ",".join(normalized)},
    )

    trend = _rows(
        """
        SELECT pl.symbol, y.year_label, y.sort_order, pl.sales
        FROM fact_profit_loss pl
        JOIN dim_year y ON y.year_id = pl.year_id
        WHERE pl.symbol = ANY(string_to_array(:symbols_csv, ','))
        ORDER BY y.sort_order, pl.symbol
        """,
        {"symbols_csv": ",".join(normalized)},
    )

    return {"items": metrics, "trend": trend}


def fetch_sector_detail(sector_name: str) -> Dict[str, object]:
    sector = sector_name.strip()
    rows = _rows(
        """
        WITH latest_scores AS (
            SELECT DISTINCT ON (symbol) symbol, overall_score, health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ),
        latest_pl AS (
            SELECT DISTINCT ON (symbol) symbol, year_id, sales, opm_pct
            FROM fact_profit_loss
            ORDER BY symbol, year_id DESC
        ),
        latest_bs AS (
            SELECT DISTINCT ON (symbol) symbol, year_id, debt_to_equity
            FROM fact_balance_sheet
            ORDER BY symbol, year_id DESC
        ),
        growth AS (
            SELECT symbol,
                MAX(CASE WHEN period_label = '3Y' THEN compounded_sales_growth_pct END) AS sales_growth_3y,
                MAX(CASE WHEN period_label = '3Y' THEN roe_pct END) AS roe_pct
            FROM fact_analysis
            GROUP BY symbol
        )
        SELECT
            c.symbol,
            c.company_name,
            c.sector,
            s.overall_score,
            s.health_label,
            p.sales,
            p.opm_pct,
            b.debt_to_equity,
            g.roe_pct,
            g.sales_growth_3y
        FROM dim_company c
        LEFT JOIN latest_scores s ON s.symbol = c.symbol
        LEFT JOIN latest_pl p ON p.symbol = c.symbol
        LEFT JOIN latest_bs b ON b.symbol = c.symbol
        LEFT JOIN growth g ON g.symbol = c.symbol
        WHERE c.sector = :sector
        ORDER BY s.overall_score DESC NULLS LAST, c.symbol
        """,
        {"sector": sector},
    )

    trend = _rows(
        """
        SELECT y.year_label, y.sort_order, SUM(pl.sales) AS sector_sales
        FROM fact_profit_loss pl
        JOIN dim_year y ON y.year_id = pl.year_id
        JOIN dim_company c ON c.symbol = pl.symbol
        WHERE c.sector = :sector
        GROUP BY y.year_label, y.sort_order
        ORDER BY y.sort_order
        """,
        {"sector": sector},
    )

    avg_metrics = {
        "avg_opm_pct": round(sum((r.get("opm_pct") or 0) for r in rows) / len(rows), 2) if rows else None,
        "avg_debt_to_equity": round(sum((r.get("debt_to_equity") or 0) for r in rows) / len(rows), 2) if rows else None,
        "avg_roe_pct": round(sum((r.get("roe_pct") or 0) for r in rows) / len(rows), 2) if rows else None,
        "avg_sales_growth_3y": round(sum((r.get("sales_growth_3y") or 0) for r in rows) / len(rows), 2) if rows else None,
    }

    return {
        "sector": sector,
        "companies": rows,
        "trend": trend,
        "top3": rows[:3],
        "bottom3": list(reversed(rows[-3:])) if len(rows) >= 3 else list(reversed(rows)),
        "average_metrics": avg_metrics,
    }


def fetch_admin_insights_summary() -> Dict[str, object]:
    total_companies = int(_scalar("SELECT COUNT(*) FROM dim_company"))
    avg_health_score = _scalar(
        """
        SELECT AVG(overall_score)
        FROM (
            SELECT DISTINCT ON (symbol) symbol, overall_score
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ) s
        """
    )

    health_distribution = _rows(
        """
        SELECT health_label, COUNT(*) AS company_count
        FROM (
            SELECT DISTINCT ON (symbol) symbol, health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
        ) s
        GROUP BY health_label
        ORDER BY health_label
        """
    )

    sector_distribution = _rows(
        """
        SELECT sector, COUNT(*) AS company_count
        FROM dim_company
        GROUP BY sector
        ORDER BY sector
        """
    )

    return {
        "total_companies": total_companies,
        "avg_health_score": round(avg_health_score, 2),
        "health_distribution": health_distribution,
        "sector_distribution": sector_distribution,
        "unreviewed_anomalies": 0,
    }


def fetch_bulk_financials(symbols: Iterable[str]) -> Dict[str, object]:
    normalized = _normalize_symbols(symbols, max_items=10)
    if not normalized:
        return {"items": []}

    rows = _rows(
        """
        SELECT pl.symbol, y.year_label, pl.sales, pl.net_profit, pl.opm_pct, pl.eps
        FROM fact_profit_loss pl
        JOIN dim_year y ON y.year_id = pl.year_id
        WHERE pl.symbol = ANY(string_to_array(:symbols_csv, ','))
        ORDER BY pl.symbol, y.sort_order
        """,
        {"symbols_csv": ",".join(normalized)},
    )
    return {"items": rows}


def fetch_latest_scores(symbols: Iterable[str] | None = None) -> Dict[str, object]:
    symbol_list = _normalize_symbols(symbols or [], max_items=100)

    if symbol_list:
        data = _rows(
            """
            SELECT DISTINCT ON (symbol)
                symbol,
                computed_at,
                overall_score,
                profitability_score,
                growth_score,
                leverage_score,
                cashflow_score,
                dividend_score,
                trend_score,
                health_label
            FROM fact_ml_scores
            WHERE symbol = ANY(string_to_array(:symbols_csv, ','))
            ORDER BY symbol, computed_at DESC
            """,
            {"symbols_csv": ",".join(symbol_list)},
        )
    else:
        data = _rows(
            """
            SELECT DISTINCT ON (symbol)
                symbol,
                computed_at,
                overall_score,
                profitability_score,
                growth_score,
                leverage_score,
                cashflow_score,
                dividend_score,
                trend_score,
                health_label
            FROM fact_ml_scores
            ORDER BY symbol, computed_at DESC
            """
        )

    return {"items": data}


def run_screener(filters: Dict[str, object]) -> Dict[str, object]:
    query_filters = {
        "sector": filters.get("sector"),
        "health_label": filters.get("health_label"),
        "search": filters.get("search"),
        "min_health_score": filters.get("min_health_score"),
    }
    output = fetch_company_list(query_filters, page=1, page_size=200, sort_by="overall_score", sort_order="desc")

    items = output["items"]
    if filters.get("min_roe") is not None:
        min_roe = float(filters["min_roe"])
        items = [row for row in items if (row.get("roe_pct") or 0) >= min_roe]

    if filters.get("max_de") is not None:
        max_de = float(filters["max_de"])
        items = [row for row in items if row.get("debt_to_equity") is not None and row.get("debt_to_equity") <= max_de]

    if filters.get("min_sales_growth") is not None:
        min_growth = float(filters["min_sales_growth"])
        items = [row for row in items if (row.get("sales_growth_3y") or 0) >= min_growth]

    return {"items": items, "count": len(items)}
