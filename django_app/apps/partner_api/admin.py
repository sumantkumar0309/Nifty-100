from django.contrib import admin

from apps.partner_api import models


@admin.register(models.Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tier", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("tier", "is_active")


@admin.register(models.PartnerAPIKey)
class PartnerAPIKeyAdmin(admin.ModelAdmin):
    list_display = ("partner", "key_id", "label", "is_active", "created_at")
    search_fields = ("partner__name", "partner__slug", "key_id")
    list_filter = ("is_active",)


@admin.register(models.APIUsageLog)
class APIUsageLogAdmin(admin.ModelAdmin):
    list_display = ("api_key", "endpoint", "method", "status_code", "response_time_ms", "created_at")
    list_filter = ("method", "status_code")
    search_fields = ("endpoint", "api_key__partner__name")


@admin.register(models.WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("partner", "url", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(models.WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("subscription", "event_type", "attempt_no", "status_code", "success", "delivered_at")
    list_filter = ("event_type", "success")
