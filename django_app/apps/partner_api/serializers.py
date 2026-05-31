from rest_framework import serializers

from apps.partner_api.models import PartnerAPIKey, WebhookSubscription


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerAPIKey
        fields = ("key_id", "label", "is_active", "created_at", "revoked_at")


class APIKeyCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=120, required=False, allow_blank=True, default="default")


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookSubscription
        fields = ("id", "url", "events", "is_active", "created_at")


class ScreenerQuerySerializer(serializers.Serializer):
    sector = serializers.CharField(required=False)
    health_label = serializers.CharField(required=False)
    min_roe = serializers.FloatField(required=False)
    max_de = serializers.FloatField(required=False)
    min_sales_growth = serializers.FloatField(required=False)
    min_health_score = serializers.FloatField(required=False)
