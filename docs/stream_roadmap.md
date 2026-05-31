# Parallel Stream Roadmap

## Stream A: Power BI dashboards

Target dashboards:

1. Executive Market Overview
2. Company Deep Dive
3. Sector Comparison Analyzer
4. Financial Health Scorecard
5. Growth and Valuation Analytics
6. Debt and Leverage Monitor
7. Dividend and Shareholder Returns

Build approach:

1. Connect to warehouse star schema only.
2. Standardize DAX measure naming and KPI cards.
3. Reuse slicer strategy (Company, Year Range, Sector).
4. Publish in Power BI Service and schedule refresh after ETL.

## Stream B: Data engineering and analytics

Implemented baseline:

1. SQL dump extraction
2. Cleaning + transforms + computed metrics
3. Star-schema load with DQ checks
4. Celery scheduling wrapper
5. Health score engine and upsert

Next engineering steps:

1. Add anomaly table and pipeline output.
2. Add peer similarity table.
3. Add forecast table for top companies.
4. Add notebook package with 6 analysis notebooks.

## Stream C: Django web + partner API

Implemented baseline:

1. Django project + route shell
2. Partner API key models
3. HMAC auth with timestamp and nonce
4. Tier throttling
5. Usage logging and webhook retry task
6. OpenAPI docs via drf-spectacular

Next application steps:

1. Build complete HTML templates and Tailwind UI.
2. Replace placeholder public pages with data-backed views.
3. Add chart endpoint payloads for Chart.js.
4. Add pytest coverage for auth/throttle/webhooks.
5. Add admin-insights dashboards.
