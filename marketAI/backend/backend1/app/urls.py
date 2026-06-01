from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('reports/', views.reports, name='reports'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),
    path('compare/', views.compare, name='compare'),

    path('companies/', views.companies, name='companies'),

    # Lightweight integration APIs.
    path('api/dashboard/', views.api_dashboard, name='api_dashboard'),
    path('api/companies/', views.api_companies, name='api_companies'),
    path('api/summary/', views.api_summary, name='api_summary'),
    path('api/reports/sector/', views.api_reports_sector, name='api_reports_sector'),
    path('api/compare/', views.api_compare, name='api_compare'),
]