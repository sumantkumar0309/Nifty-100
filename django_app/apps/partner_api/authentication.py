from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from secrets import compare_digest

from django.core.cache import cache
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from apps.partner_api.models import PartnerAPIKey


class PartnerHMACAuthentication(authentication.BaseAuthentication):
    timestamp_tolerance_seconds = 300

    def authenticate(self, request):
        key_id = request.headers.get("X-API-Key-ID")
        timestamp = request.headers.get("X-Timestamp")
        signature = request.headers.get("X-Signature")
        nonce = request.headers.get("X-Nonce")

        if not all([key_id, timestamp, signature, nonce]):
            return None

        try:
            key_uuid = uuid.UUID(key_id)
        except (ValueError, TypeError) as exc:
            raise AuthenticationFailed("Invalid API key id format.") from exc

        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError) as exc:
            raise AuthenticationFailed("Invalid timestamp format.") from exc

        now = int(time.time())
        if abs(now - timestamp_int) > self.timestamp_tolerance_seconds:
            raise AuthenticationFailed("Request timestamp expired.")

        normalized_signature = signature.replace("sha256=", "").strip().lower()

        try:
            api_key = PartnerAPIKey.objects.select_related("partner").get(key_id=key_uuid, is_active=True, partner__is_active=True)
        except PartnerAPIKey.DoesNotExist as exc:
            raise AuthenticationFailed("Invalid API key.") from exc

        replay_key = f"partner_nonce:{api_key.key_id}:{nonce}"
        if not cache.add(replay_key, 1, timeout=self.timestamp_tolerance_seconds):
            raise AuthenticationFailed("Replay attack detected.")

        body_hash = hashlib.sha256(request.body or b"").hexdigest()
        canonical = "\n".join(
            [
                request.method.upper(),
                request.get_full_path(),
                str(timestamp_int),
                body_hash,
                nonce,
            ]
        )

        try:
            signing_secret = api_key.get_signing_secret()
        except Exception as exc:
            raise AuthenticationFailed("API signing secret unavailable.") from exc

        expected_signature = hmac.new(
            signing_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not compare_digest(expected_signature, normalized_signature):
            raise AuthenticationFailed("Invalid request signature.")

        request.partner_api_key = api_key
        return api_key.partner, api_key
