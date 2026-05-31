from __future__ import annotations

import time

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle

from apps.partner_api.models import PartnerAPIKey, Partner


class PartnerTierThrottle(BaseThrottle):
    LIMITS = {
        Partner.Tier.BASIC: {"minute": 10, "hour": 100, "day": 500},
        Partner.Tier.PRO: {"minute": 60, "hour": 1000, "day": 10000},
        Partner.Tier.ENTERPRISE: {"minute": 300, "hour": 10000, "day": 1000000000},
    }

    WINDOWS = {
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }

    def __init__(self) -> None:
        self.wait_seconds = 0

    def allow_request(self, request, view) -> bool:
        auth = getattr(request, "auth", None)
        user = getattr(request, "user", None)

        if not isinstance(auth, PartnerAPIKey) or not isinstance(user, Partner):
            return True

        tier_limits = self.LIMITS.get(user.tier, self.LIMITS[Partner.Tier.BASIC])
        now = int(time.time())

        for window_name, limit in tier_limits.items():
            window_seconds = self.WINDOWS[window_name]
            bucket = now // window_seconds
            key = f"partner_rate:{auth.key_id}:{window_name}:{bucket}"

            created = cache.add(key, 1, timeout=window_seconds + 2)
            if created:
                current_count = 1
            else:
                try:
                    current_count = int(cache.incr(key))
                except Exception:
                    cache.set(key, 1, timeout=window_seconds + 2)
                    current_count = 1

            if current_count > limit:
                self.wait_seconds = window_seconds - (now % window_seconds)
                return False

        return True

    def wait(self):
        return self.wait_seconds
