from django.urls import path

from apps.public import views

urlpatterns = [
    path("", views.home, name="home"),
    path("companies/", views.companies, name="companies"),
    path("company/<str:symbol>/", views.company_detail, name="company-detail"),
    path("compare/", views.compare, name="compare"),
    path("screener/", views.screener, name="screener"),
    path("sector/<str:name>/", views.sector_detail, name="sector-detail"),
    path("admin-insights/", views.admin_insights, name="admin-insights"),
    path("admin-insights/health-monitor/", views.admin_health_monitor, name="admin-health-monitor"),
    path("admin-insights/anomalies/", views.admin_anomalies, name="admin-anomalies"),
    path("admin-insights/data-quality/", views.admin_data_quality, name="admin-data-quality"),
    path("admin-insights/api-management/", views.admin_api_management, name="admin-api-management"),
    path("admin-insights/api-usage/", views.admin_api_usage, name="admin-api-usage"),
    path("admin-insights/webhooks/", views.admin_webhooks, name="admin-webhooks"),
    path("admin-insights/bulk-import/", views.admin_bulk_import, name="admin-bulk-import"),
    path("admin-insights/celery-monitor/", views.admin_celery_monitor, name="admin-celery-monitor"),
    path("api/v1/home/", views.api_home, name="api-home"),
    path("api/v1/companies/", views.api_company_list, name="api-company-list"),
    path("api/v1/companies/<str:symbol>/charts/", views.api_company_charts, name="api-company-charts"),
    path("api/v1/compare/", views.api_compare, name="api-compare"),
    path("api/v1/screener/", views.api_screener, name="api-screener"),
    path("api/v1/sectors/<str:name>/", views.api_sector_detail, name="api-sector-detail"),
    path("api/v1/admin/summary/", views.api_admin_summary, name="api-admin-summary"),
]
