from django.db.models import Max, F, Sum, Avg, Count
from django.http import JsonResponse
from django.shortcuts import render
from .models import DimCompany, FactProfitLoss, MlScore

def _company_snapshot() -> list[dict]:
    # Query database instead of reading CSV
    try:
        # We need the latest year for each company
        latest_year = FactProfitLoss.objects.aggregate(Max('year_id'))['year_id__max']
        
        # Get companies with latest profit loss, and ML scores
        companies = DimCompany.objects.all().prefetch_related(
            'factprofitloss_set',
            'mlscore_set'
        )
        
        records = []
        for company in companies:
            # Find the latest profit/loss record for this company
            fpl = FactProfitLoss.objects.filter(symbol=company, year_id=latest_year).first()
            score = MlScore.objects.filter(symbol=company).first()
            
            revenue = fpl.sales if fpl and fpl.sales else 0
            profit = fpl.net_profit if fpl and fpl.net_profit else 0
            health = score.overall_score if score and score.overall_score else 50
            
            records.append({
                "symbol": company.symbol,
                "name": company.company_name,
                "sector": company.sector_name or "Unknown",
                "revenue": float(revenue),
                "profit": float(profit),
                "health": float(health)
            })
            
        return sorted(records, key=lambda x: x['revenue'], reverse=True)
    except Exception as e:
        print(f"Error querying database: {e}")
        return []

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

    total_companies = len(companies_data)
    avg_health_score = round(sum(c["health"] for c in companies_data) / total_companies, 2) if total_companies else 0
    total_revenue = round(sum(c["revenue"] for c in companies_data), 2)
    
    # Group by sector to find top sector
    sectors = {}
    for c in companies_data:
        sectors[c["sector"]] = sectors.get(c["sector"], 0) + 1
    top_sector = max(sectors.items(), key=lambda x: x[1])[0] if sectors else "N/A"

    top_companies = sorted(companies_data, key=lambda x: (x["health"], x["revenue"]), reverse=True)[:5]
    
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

    grouped = {}
    for c in companies_data:
        sector = c["sector"]
        if sector not in grouped:
            grouped[sector] = {"company_count": 0, "total_revenue": 0, "total_profit": 0, "health_sum": 0}
        
        grouped[sector]["company_count"] += 1
        grouped[sector]["total_revenue"] += c["revenue"]
        grouped[sector]["total_profit"] += c["profit"]
        grouped[sector]["health_sum"] += c["health"]
        
    rows = []
    for sector, data in grouped.items():
        rows.append({
            "sector": sector,
            "company_count": data["company_count"],
            "total_revenue": round(data["total_revenue"], 2),
            "total_profit": round(data["total_profit"], 2),
            "avg_health": round(data["health_sum"] / data["company_count"], 2)
        })
        
    rows.sort(key=lambda x: x["total_revenue"], reverse=True)

    return {
        "rows": rows,
        "labels": [row["sector"] for row in rows],
        "revenue": [row["total_revenue"] for row in rows],
        "profit": [row["total_profit"] for row in rows],
    }

def _compare_payload(companies_data: list[dict], symbols_query: str) -> dict:
    if not companies_data:
        return {"selected_symbols": [], "results": []}

    selected_symbols = [s.strip().upper() for s in symbols_query.split(",") if s.strip()]
    if selected_symbols:
        filtered = [c for c in companies_data if c["symbol"] in selected_symbols]
    else:
        filtered = sorted(companies_data, key=lambda x: x["revenue"], reverse=True)[:5]
        
    results = []
    for row in filtered:
        profit_margin = (row["profit"] / row["revenue"] * 100) if row["revenue"] > 0 else 0
        results.append({
            "symbol": row["symbol"],
            "name": row["name"],
            "sector": row["sector"],
            "revenue": round(row["revenue"], 2),
            "profit": round(row["profit"], 2),
            "health": round(row["health"], 2),
            "profit_margin": round(profit_margin, 2),
        })

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

