from __future__ import annotations

from typing import Dict

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.warehouse import services


def _to_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _service_json(callable_obj) -> JsonResponse:
    try:
        payload = callable_obj()
        return JsonResponse(payload)
    except RuntimeError as exc:
        return JsonResponse(
            {
                "detail": str(exc),
                "required": [
                    "Set WAREHOUSE_DATABASE_URL or DATABASE_URL",
                    "Ensure PostgreSQL warehouse is running",
                    "Run ETL load scripts before requesting analytics endpoints",
                ],
            },
            status=503,
        )
    except Exception as exc:
        return JsonResponse(
            {
                "detail": f"Warehouse service unavailable: {exc}",
                "required": [
                    "Ensure PostgreSQL warehouse is running and reachable",
                    "Verify DATABASE_URL/WAREHOUSE_DATABASE_URL in .env",
                    "Run ETL load scripts before requesting analytics endpoints",
                ],
            },
            status=503,
        )


def _render_page(request: HttpRequest, page_title: str, page_key: str, extra: Dict[str, object] | None = None) -> HttpResponse:
    context = {
        "page_title": page_title,
        "page_key": page_key,
    }
    if extra:
        context.update(extra)
    return render(request, "public/page.html", context)


def home(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Nifty 100 Financial Intelligence", "home")


def companies(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Companies", "companies")


def company_detail(request: HttpRequest, symbol: str) -> HttpResponse:
    payload = services.fetch_company_full(symbol)
    if not payload:
        raise Http404("Company not found")
    return _render_page(
        request,
        f"Company Detail - {symbol.upper()}",
        "company-detail",
        {
            "company_payload": payload,
            "symbol": symbol.upper(),
        },
    )


def compare(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Compare Companies", "compare")


def screener(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Screener", "screener")


def sector_detail(request: HttpRequest, name: str) -> HttpResponse:
    payload = services.fetch_sector_detail(name)
    return _render_page(request, f"Sector - {name}", "sector-detail", {"sector_payload": payload})


@staff_member_required
def admin_insights(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Executive Summary", "admin-insights")


@staff_member_required
def admin_health_monitor(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Health Monitor", "admin-health-monitor")


@staff_member_required
def admin_anomalies(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Anomalies", "admin-anomalies")


@staff_member_required
def admin_data_quality(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Data Quality", "admin-data-quality")


@staff_member_required
def admin_api_management(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - API Management", "admin-api-management")


@staff_member_required
def admin_api_usage(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - API Usage", "admin-api-usage")


@staff_member_required
def admin_webhooks(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Webhooks", "admin-webhooks")


@staff_member_required
def admin_bulk_import(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Bulk Import", "admin-bulk-import")


@staff_member_required
def admin_celery_monitor(request: HttpRequest) -> HttpResponse:
    return _render_page(request, "Admin Insights - Celery Monitor", "admin-celery-monitor")


@require_GET
def api_home(request: HttpRequest) -> JsonResponse:
    return _service_json(lambda: services.fetch_home_payload())


@require_GET
def api_company_list(request: HttpRequest) -> JsonResponse:
    page = _to_int(request.GET.get("page"), 1)
    page_size = _to_int(request.GET.get("page_size"), 20)
    sort_by = request.GET.get("sort_by", "overall_score")
    sort_order = request.GET.get("sort_order", "desc")

    filters = {
        "sector": request.GET.get("sector") or None,
        "health_label": request.GET.get("health_label") or None,
        "search": request.GET.get("search") or None,
        "min_health_score": _to_float(request.GET.get("min_health_score")),
    }

    return _service_json(
        lambda: services.fetch_company_list(
            filters=filters,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
            sort_by=sort_by,
            sort_order=sort_order,
        )
    )


@require_GET
def api_company_charts(request: HttpRequest, symbol: str) -> JsonResponse:
    try:
        payload = services.fetch_company_charts(symbol)
    except RuntimeError as exc:
        return JsonResponse(
            {
                "detail": str(exc),
                "required": [
                    "Set WAREHOUSE_DATABASE_URL or DATABASE_URL",
                    "Ensure PostgreSQL warehouse is running",
                    "Run ETL load scripts before requesting analytics endpoints",
                ],
            },
            status=503,
        )
    if not payload:
        return JsonResponse({"detail": "Company not found."}, status=404)
    return JsonResponse(payload)


@require_GET
def api_compare(request: HttpRequest) -> JsonResponse:
    symbols = [item.strip().upper() for item in (request.GET.get("symbols") or "").split(",") if item.strip()]
    return _service_json(lambda: services.fetch_compare(symbols))


@require_GET
def api_screener(request: HttpRequest) -> JsonResponse:
    filters = {
        "sector": request.GET.get("sector") or None,
        "health_label": request.GET.get("health_label") or None,
        "min_roe": _to_float(request.GET.get("min_roe")),
        "max_de": _to_float(request.GET.get("max_de")),
        "min_sales_growth": _to_float(request.GET.get("min_sales_growth")),
        "min_health_score": _to_float(request.GET.get("min_health_score")),
    }
    return _service_json(lambda: services.run_screener(filters))


@require_GET
def api_sector_detail(request: HttpRequest, name: str) -> JsonResponse:
    return _service_json(lambda: services.fetch_sector_detail(name))


@staff_member_required
@require_GET
def api_admin_summary(request: HttpRequest) -> JsonResponse:
    return _service_json(lambda: services.fetch_admin_insights_summary())
