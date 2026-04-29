from __future__ import annotations

from pathlib import Path

import pandas as pd
from django.http import JsonResponse
from django.shortcuts import render


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
CLEAN_DATA_DIR = WORKSPACE_ROOT / "data" / "clean"
ML_SCORES_PATH = WORKSPACE_ROOT / "marketAI" / "data" / "ml_scores.csv"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _company_snapshot() -> list[dict]:
    dim_company = _read_csv(CLEAN_DATA_DIR / "dim_company.csv")
    fact_profit_loss = _read_csv(CLEAN_DATA_DIR / "fact_profit_loss.csv")
    ml_scores = _read_csv(ML_SCORES_PATH)

    if dim_company.empty:
        return []

    if not fact_profit_loss.empty and "year_id" in fact_profit_loss.columns:
        latest_year = fact_profit_loss["year_id"].max()
        latest_profit = fact_profit_loss[fact_profit_loss["year_id"] == latest_year].copy()
        latest_profit = latest_profit[["symbol", "sales", "net_profit"]]
    else:
        latest_profit = pd.DataFrame(columns=["symbol", "sales", "net_profit"])

    if not ml_scores.empty:
        symbol_column = "symbol" if "symbol" in ml_scores.columns else "company_id" if "company_id" in ml_scores.columns else None
        score_column = "overall_score" if "overall_score" in ml_scores.columns else "health" if "health" in ml_scores.columns else None

        if symbol_column and score_column:
            ml_scores = ml_scores[[symbol_column, score_column]].rename(columns={symbol_column: "symbol", score_column: "health"})
        else:
            ml_scores = pd.DataFrame(columns=["symbol", "health"])
    else:
        ml_scores = pd.DataFrame(columns=["symbol", "health"])

    merged = dim_company.merge(latest_profit, on="symbol", how="left")
    merged = merged.merge(ml_scores, on="symbol", how="left")
    merged = merged.assign(
        sales=pd.to_numeric(merged.get("sales"), errors="coerce").fillna(0),
        net_profit=pd.to_numeric(merged.get("net_profit"), errors="coerce").fillna(0),
        health=pd.to_numeric(merged.get("health"), errors="coerce").fillna(50),
    )

    merged = merged.rename(
        columns={
            "company_name": "name",
            "sector_name": "sector",
            "sales": "revenue",
            "net_profit": "profit",
        }
    )
    merged = merged.assign(sector=merged["sector"].fillna("Unknown"))

    merged = merged[["symbol", "name", "sector", "revenue", "profit", "health"]]
    merged = merged.sort_values("revenue", ascending=False)

    records = merged.to_dict(orient="records")
    for record in records:
        record["revenue"] = round(float(record["revenue"]), 2)
        record["profit"] = round(float(record["profit"]), 2)
        record["health"] = round(float(record["health"]), 2)
    return records


def _dashboard_payload(companies_data: list[dict], limit: int = 10) -> dict:
    top = companies_data[:limit]
    labels = [c["name"] for c in top]
    revenue = [round(float(c["revenue"]), 2) for c in top]
    profit = [round(float(c["profit"]), 2) for c in top]

    health_labels = ["Excellent", "Good", "Average", "Weak"]
    health_counts = [
        len([c for c in companies_data if c["health"] >= 85]),
        len([c for c in companies_data if 70 <= c["health"] < 85]),
        len([c for c in companies_data if 55 <= c["health"] < 70]),
        len([c for c in companies_data if c["health"] < 55]),
    ]

    return {
        "labels": labels,
        "revenue": revenue,
        "profit": profit,
        "health_labels": health_labels,
        "health_counts": health_counts,
    }


def _summary_payload(companies_data: list[dict]) -> dict:
    if not companies_data:
        return {
            "total_companies": 0,
            "avg_health_score": 0,
            "top_sector": "N/A",
            "total_revenue": 0,
            "top_companies": [],
        }

    frame = pd.DataFrame(companies_data)
    total_companies = int(len(frame))
    avg_health_score = round(float(frame["health"].mean()), 2)
    top_sector = str(frame["sector"].value_counts().idxmax()) if not frame.empty else "N/A"
    total_revenue = round(float(frame["revenue"].sum()), 2)

    top_companies_frame = frame.sort_values(["health", "revenue"], ascending=False).head(5)
    top_companies = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "sector": str(row["sector"]),
            "health": round(float(row["health"]), 2),
        }
        for _, row in top_companies_frame.iterrows()
    ]

    return {
        "total_companies": total_companies,
        "avg_health_score": avg_health_score,
        "top_sector": top_sector,
        "total_revenue": total_revenue,
        "top_companies": top_companies,
    }


def _sector_report_payload(companies_data: list[dict]) -> dict:
    if not companies_data:
        return {"rows": [], "labels": [], "revenue": [], "profit": []}

    frame = pd.DataFrame(companies_data)
    grouped = (
        frame.groupby("sector", dropna=False)
        .agg(
            company_count=("symbol", "count"),
            total_revenue=("revenue", "sum"),
            total_profit=("profit", "sum"),
            avg_health=("health", "mean"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
    )

    rows = [
        {
            "sector": str(row["sector"]),
            "company_count": int(row["company_count"]),
            "total_revenue": round(float(row["total_revenue"]), 2),
            "total_profit": round(float(row["total_profit"]), 2),
            "avg_health": round(float(row["avg_health"]), 2),
        }
        for _, row in grouped.iterrows()
    ]

    return {
        "rows": rows,
        "labels": [row["sector"] for row in rows],
        "revenue": [row["total_revenue"] for row in rows],
        "profit": [row["total_profit"] for row in rows],
    }


def _compare_payload(companies_data: list[dict], symbols_query: str) -> dict:
    if not companies_data:
        return {"selected_symbols": [], "results": []}

    frame = pd.DataFrame(companies_data)

    selected_symbols = [s.strip().upper() for s in symbols_query.split(",") if s.strip()]
    if selected_symbols:
        filtered = frame[frame["symbol"].isin(selected_symbols)].copy()
    else:
        filtered = frame.sort_values("revenue", ascending=False).head(5).copy()

    filtered["profit_margin"] = filtered.apply(
        lambda row: (float(row["profit"]) / float(row["revenue"]) * 100) if float(row["revenue"]) > 0 else 0,
        axis=1,
    )

    results = [
        {
            "symbol": str(row["symbol"]),
            "name": str(row["name"]),
            "sector": str(row["sector"]),
            "revenue": round(float(row["revenue"]), 2),
            "profit": round(float(row["profit"]), 2),
            "health": round(float(row["health"]), 2),
            "profit_margin": round(float(row["profit_margin"]), 2),
        }
        for _, row in filtered.iterrows()
    ]

    return {
        "selected_symbols": selected_symbols,
        "results": results,
    }


def home(request):
    return render(request, "app/home.html")


def about(request):
    return render(request, "app/about.html")


def reports(request):
    return render(request, "app/reports.html")


def profile(request):
    return render(request, "app/profile.html")


def settings(request):
    return render(request, "app/settings.html")


def compare(request):
    return render(request, "app/compare.html")


def dashboard(request):
    return render(request, "app/dashboard.html")


def companies(request):
    return render(
        request,
        "app/companies.html",
        {
            "search": request.GET.get("search", "").strip(),
            "sector": request.GET.get("sector", "").strip(),
            "sort": request.GET.get("sort", "").strip(),
            "min_health": request.GET.get("min_health", "").strip(),
        },
    )


def api_dashboard(request):
    companies_data = _company_snapshot()
    return JsonResponse(_dashboard_payload(companies_data))


def api_companies(request):
    return JsonResponse({"results": _company_snapshot()})


def api_summary(request):
    return JsonResponse(_summary_payload(_company_snapshot()))


def api_reports_sector(request):
    return JsonResponse(_sector_report_payload(_company_snapshot()))


def api_compare(request):
    symbols = request.GET.get("symbols", "")
    return JsonResponse(_compare_payload(_company_snapshot(), symbols))