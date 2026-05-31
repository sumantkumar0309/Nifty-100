from __future__ import annotations

import json
import time
from typing import Any

from apps.jobs.tasks import log_partner_api_usage
from apps.partner_api.models import PartnerAPIKey


def queue_usage_log(request, response_data: Any, status_code: int, started_at: float) -> None:
    api_key = getattr(request, "auth", None)
    if not isinstance(api_key, PartnerAPIKey):
        return

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    request_size = len(request.body or b"")
    try:
        response_size = len(json.dumps(response_data, default=str).encode("utf-8"))
    except Exception:
        response_size = 0

    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")

    try:
        log_partner_api_usage.delay(
            api_key_id=str(api_key.key_id),
            endpoint=request.path,
            method=request.method,
            status_code=int(status_code),
            response_time_ms=duration_ms,
            ip_address=ip_address,
            request_size=request_size,
            response_size=response_size,
        )
    except Exception:
        return
