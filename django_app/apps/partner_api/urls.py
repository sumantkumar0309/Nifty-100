from django.urls import path

from apps.partner_api import views

urlpatterns = [
    path("companies/<str:symbol>/full/", views.CompanyFullView.as_view(), name="partner-company-full"),
    path("bulk-financials/", views.BulkFinancialsView.as_view(), name="partner-bulk-financials"),
    path("screener/", views.PartnerScreenerView.as_view(), name="partner-screener"),
    path("scores/", views.ScoresView.as_view(), name="partner-scores"),
    path("keys/", views.APIKeyListCreateView.as_view(), name="partner-keys"),
    path("keys/<uuid:key_id>/", views.APIKeyDeleteView.as_view(), name="partner-key-delete"),
    path("webhooks/", views.WebhookListCreateView.as_view(), name="partner-webhooks"),
    path("webhooks/<int:webhook_id>/", views.WebhookDeleteView.as_view(), name="partner-webhook-delete"),
]
