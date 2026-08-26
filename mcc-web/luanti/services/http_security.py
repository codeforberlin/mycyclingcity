# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hmac
import json
import time
from hashlib import sha256

from django.conf import settings


def sign_payload(payload: dict) -> str:
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    secret = settings.MCC_LUANTI_HTTP_SHARED_SECRET.encode("utf-8")
    return hmac.new(secret, message, sha256).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature or "")


def verify_request_auth(
    *,
    server_id: str,
    signature: str,
    payload: dict,
    timestamp: int | None = None,
    max_skew_seconds: int = 300,
) -> tuple[bool, str]:
    """Validate server_id allowlist, optional timestamp skew, and HMAC or auth_token."""
    allowed = set(settings.MCC_LUANTI_ALLOWED_SERVER_IDS or [])
    if allowed and server_id not in allowed:
        return False, "server_id_not_allowed"
    if timestamp is not None:
        now = int(time.time())
        if abs(now - int(timestamp)) > max_skew_seconds:
            return False, "timestamp_skew"
    body = dict(payload)
    body.pop("signature", None)
    auth_token = str(body.pop("auth_token", "") or "")
    secret = settings.MCC_LUANTI_HTTP_SHARED_SECRET or ""
    # Lua bridge may send auth_token when HMAC helpers are unavailable.
    if auth_token and hmac.compare_digest(auth_token, secret):
        return True, ""
    if verify_signature(body, signature):
        return True, ""
    return False, "invalid_signature"