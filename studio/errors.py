"""API error detection and retry helpers (Chat.py 移植)."""

from __future__ import annotations

import time
from typing import Any

API_ERROR_CODES = {
    "413": "Request too large",
    "429": "Rate limit exceeded",
    "503": "Service unavailable",
    "504": "Gateway timeout",
}


def detect_api_error(error_str: str) -> str | None:
    error_str_lower = error_str.lower()

    for code in API_ERROR_CODES:
        if code in error_str:
            return code

    if any(k in error_str_lower for k in ("rate limit", "rate_limit", "too many requests")):
        return "429"
    if any(k in error_str_lower for k in ("request too large", "payload too large", "content too long")):
        return "413"
    if any(k in error_str_lower for k in ("service unavailable", "temporarily unavailable")):
        return "503"
    if any(k in error_str_lower for k in ("timeout", "gateway timeout")):
        return "504"
    return None


def is_temperature_unsupported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "temperature" in text and any(
        k in text
        for k in (
            "deprecated",
            "not supported",
            "unsupported",
            "does not support",
            "only the default",
            "invalid_request_error",
        )
    )


def handle_api_error(
    error_code: str | None,
    attempt: int,
    max_retries: int,
    retry_delay: float,
    *,
    reduce_history: Any | None = None,
) -> bool:
    """Return True if caller should retry."""
    if error_code == "413" and reduce_history is not None and attempt < max_retries - 1:
        if reduce_history():
            return True
        return False

    if error_code in ("429", "503", "504") and attempt < max_retries - 1:
        wait_time = retry_delay * (2**attempt) if error_code == "429" else retry_delay
        time.sleep(wait_time)
        return True

    return False
