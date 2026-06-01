from __future__ import annotations

import time

import requests

from backend2.config import WEBHOOK_BACKOFF_SECONDS, WEBHOOK_MAX_ATTEMPTS, WEBHOOK_TIMEOUT_SECONDS
from backend2.logging_utils import get_logger

logger = get_logger(__name__)


def send_webhook_with_retry(
    url: str,
    payload: dict,
    headers: dict | None = None,
    timeout_seconds: int | None = None,
    max_attempts: int | None = None,
    base_backoff_seconds: int | None = None,
) -> dict[str, int | str | bool]:
    timeout = timeout_seconds or WEBHOOK_TIMEOUT_SECONDS
    attempts = max_attempts or WEBHOOK_MAX_ATTEMPTS
    backoff = base_backoff_seconds or WEBHOOK_BACKOFF_SECONDS

    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, json=payload, headers=request_headers, timeout=timeout)
            if 200 <= response.status_code < 300:
                result = {
                    "success": True,
                    "url": url,
                    "attempt": attempt,
                    "status_code": response.status_code,
                }
                logger.info("Webhook dispatched", extra={"event": "webhook_success", "extra_data": result})
                return result

            last_error = f"status_code={response.status_code} body={response.text[:500]}"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < attempts:
            time.sleep(backoff * attempt)

    result = {
        "success": False,
        "url": url,
        "attempt": attempts,
        "status_code": -1,
        "error": last_error,
    }
    logger.error("Webhook dispatch failed", extra={"event": "webhook_failure", "extra_data": result})
    return result
