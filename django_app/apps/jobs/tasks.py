from __future__ import annotations

import hashlib
import hmac
import json

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.partner_api.models import APIUsageLog, PartnerAPIKey, WebhookEvent, WebhookSubscription


@shared_task(name="apps.jobs.tasks.log_partner_api_usage")
def log_partner_api_usage(
    api_key_id: str,
    endpoint: str,
    method: str,
    status_code: int,
    response_time_ms: int,
    ip_address: str | None,
    request_size: int,
    response_size: int,
) -> None:
    try:
        api_key = PartnerAPIKey.objects.get(key_id=api_key_id)
    except PartnerAPIKey.DoesNotExist:
        return

    APIUsageLog.objects.create(
        api_key=api_key,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        response_time_ms=response_time_ms,
        ip_address=ip_address,
        request_size=request_size,
        response_size=response_size,
    )


@shared_task(bind=True, max_retries=5, name="apps.jobs.tasks.deliver_webhook_event")
def deliver_webhook_event(self, subscription_id: int, event_type: str, payload: dict) -> None:
    try:
        subscription = WebhookSubscription.objects.get(id=subscription_id, is_active=True)
    except WebhookSubscription.DoesNotExist:
        return

    body = json.dumps(payload).encode("utf-8")
    signing_secret = settings.SECRET_KEY
    signature = hmac.new(signing_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    try:
        response = requests.post(
            subscription.url,
            data=body,
            timeout=20,
            headers={
                "Content-Type": "application/json",
                "X-Bluestock-Signature": signature,
                "X-Event-Type": event_type,
            },
        )
        success = 200 <= response.status_code < 300

        WebhookEvent.objects.create(
            subscription=subscription,
            event_type=event_type,
            payload=payload,
            attempt_no=self.request.retries + 1,
            status_code=response.status_code,
            success=success,
            error_message="" if success else response.text[:1000],
            delivered_at=timezone.now(),
        )

        if not success:
            delay_seconds = (2 ** self.request.retries) * 60
            raise self.retry(countdown=delay_seconds)

    except Exception as exc:
        WebhookEvent.objects.create(
            subscription=subscription,
            event_type=event_type,
            payload=payload,
            attempt_no=self.request.retries + 1,
            success=False,
            error_message=str(exc)[:1000],
            delivered_at=timezone.now(),
        )
        delay_seconds = (2 ** self.request.retries) * 60
        raise self.retry(exc=exc, countdown=delay_seconds)
