"""Secret and sensitive data redaction."""

from __future__ import annotations

import json
import re
from typing import Any

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADER_NAMES:
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    return out


def redact_json_fields(data: Any, sensitive_fields: list[str]) -> Any:
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if k in sensitive_fields:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact_json_fields(v, sensitive_fields)
        return out
    if isinstance(data, list):
        return [redact_json_fields(x, sensitive_fields) for x in data]
    return data


def redact_text(text: str) -> str:
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", r"\1***REDACTED***", text, flags=re.I)
    text = re.sub(r"(api[_-]?key[\"']?\s*[:=]\s*)[\"']?[^\"'\s]+", r"\1***REDACTED***", text, flags=re.I)
    return text


def fingerprint_request(method: str, path: str, query: dict[str, str]) -> str:
    q = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    return f"{method.upper()} {path}" + (f"?{q}" if q else "")
