from __future__ import annotations

import time

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.partner_api.authentication import PartnerHMACAuthentication
from apps.partner_api.models import PartnerAPIKey, WebhookSubscription
from apps.partner_api.permissions import IsActivePartner
from apps.partner_api.serializers import (
    APIKeyCreateSerializer,
    APIKeySerializer,
    ScreenerQuerySerializer,
    WebhookSubscriptionSerializer,
)
from apps.partner_api.throttling import PartnerTierThrottle
from apps.partner_api.utils import queue_usage_log
from apps.warehouse import services


class PartnerBaseAPIView(APIView):
    authentication_classes = [PartnerHMACAuthentication]
    throttle_classes = [PartnerTierThrottle]
    permission_classes = [IsAuthenticated, IsActivePartner]


class CompanyFullView(PartnerBaseAPIView):
    @extend_schema(
        parameters=[OpenApiParameter(name="symbol", location=OpenApiParameter.PATH, required=True, type=str)],
        responses={200: dict},
    )
    def get(self, request, symbol: str):
        started_at = time.perf_counter()
        payload = services.fetch_company_full(symbol)
        if not payload:
            response = Response({"detail": "Company not found."}, status=status.HTTP_404_NOT_FOUND)
            queue_usage_log(request, response.data, response.status_code, started_at)
            return response

        response = Response(payload)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class BulkFinancialsView(PartnerBaseAPIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="symbols",
                location=OpenApiParameter.QUERY,
                required=True,
                type=str,
                description="Comma-separated symbols, max 10",
            )
        ],
        responses={200: dict},
    )
    def get(self, request):
        started_at = time.perf_counter()
        symbols_param = request.query_params.get("symbols", "")
        symbols = [value.strip().upper() for value in symbols_param.split(",") if value.strip()]
        payload = services.fetch_bulk_financials(symbols)
        response = Response(payload)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class PartnerScreenerView(PartnerBaseAPIView):
    @extend_schema(parameters=[ScreenerQuerySerializer], responses={200: dict})
    def get(self, request):
        started_at = time.perf_counter()
        serializer = ScreenerQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = services.run_screener(serializer.validated_data)
        response = Response(payload)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class ScoresView(PartnerBaseAPIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(name="symbols", location=OpenApiParameter.QUERY, required=False, type=str),
        ],
        responses={200: dict},
    )
    def get(self, request):
        started_at = time.perf_counter()
        symbols_param = request.query_params.get("symbols", "")
        symbols = [value.strip().upper() for value in symbols_param.split(",") if value.strip()]
        payload = services.fetch_latest_scores(symbols or None)
        response = Response(payload)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class APIKeyListCreateView(PartnerBaseAPIView):
    @extend_schema(responses={200: APIKeySerializer(many=True)})
    def get(self, request):
        started_at = time.perf_counter()
        queryset = PartnerAPIKey.objects.filter(partner=request.user).order_by("-created_at")
        response = Response(APIKeySerializer(queryset, many=True).data)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response

    @extend_schema(request=APIKeyCreateSerializer, responses={201: dict})
    def post(self, request):
        started_at = time.perf_counter()
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        label = serializer.validated_data.get("label") or "default"
        api_key, plain_secret = PartnerAPIKey.create_key_pair(partner=request.user, label=label)

        payload = {
            "key_id": str(api_key.key_id),
            "label": api_key.label,
            "key_secret": plain_secret,
            "message": "Store this secret securely. It will not be shown again.",
        }
        response = Response(payload, status=status.HTTP_201_CREATED)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class APIKeyDeleteView(PartnerBaseAPIView):
    @extend_schema(responses={204: None})
    def delete(self, request, key_id):
        started_at = time.perf_counter()
        try:
            key_obj = PartnerAPIKey.objects.get(partner=request.user, key_id=key_id, is_active=True)
        except PartnerAPIKey.DoesNotExist:
            response = Response({"detail": "API key not found."}, status=status.HTTP_404_NOT_FOUND)
            queue_usage_log(request, response.data, response.status_code, started_at)
            return response

        key_obj.revoke()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        queue_usage_log(request, {}, response.status_code, started_at)
        return response


class WebhookListCreateView(PartnerBaseAPIView):
    @extend_schema(responses={200: WebhookSubscriptionSerializer(many=True)})
    def get(self, request):
        started_at = time.perf_counter()
        queryset = WebhookSubscription.objects.filter(partner=request.user).order_by("-created_at")
        response = Response(WebhookSubscriptionSerializer(queryset, many=True).data)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response

    @extend_schema(request=WebhookSubscriptionSerializer, responses={201: WebhookSubscriptionSerializer})
    def post(self, request):
        started_at = time.perf_counter()
        serializer = WebhookSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook = serializer.save(partner=request.user)
        response = Response(WebhookSubscriptionSerializer(webhook).data, status=status.HTTP_201_CREATED)
        queue_usage_log(request, response.data, response.status_code, started_at)
        return response


class WebhookDeleteView(PartnerBaseAPIView):
    @extend_schema(responses={204: None})
    def delete(self, request, webhook_id: int):
        started_at = time.perf_counter()
        try:
            webhook = WebhookSubscription.objects.get(id=webhook_id, partner=request.user)
        except WebhookSubscription.DoesNotExist:
            response = Response({"detail": "Webhook not found."}, status=status.HTTP_404_NOT_FOUND)
            queue_usage_log(request, response.data, response.status_code, started_at)
            return response

        webhook.delete()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        queue_usage_log(request, {}, response.status_code, started_at)
        return response
