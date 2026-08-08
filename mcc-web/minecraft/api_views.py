# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    api_views.py
# @note    Device/IoT-facing Minecraft APIs (RFID counter scan).

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from api.views import validate_api_key
from config.logger_utils import get_logger
from minecraft.models import MCSession, MinecraftPlayAccount
from minecraft.services.session_control import (
    AccountAlreadyActiveError,
    RconSequenceError,
    SessionControlError,
    models_q_id_or_short,
    start_player_session,
)

logger = get_logger("minecraft")


def _extract_token(data: dict) -> str | None:
    """Return first non-empty token from token / id_tag / rfid keys."""
    for key in ("token", "id_tag", "rfid"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        else:
            text = str(value).strip()
            if text:
                return text
    return None


@csrf_exempt
@require_POST
def mcc_counter_scan(request):
    """
    Start a Minecraft play session from an RFID / counter scan.

    POST /api/mcc-counter/scan/
    Body: {"token": "Arena1"}  (aliases: id_tag, rfid)
    Auth: X-Api-Key (MCC_APP_API_KEY or device-specific keys)
    """
    api_key_header = request.headers.get("X-Api-Key")
    is_valid, _api_device = validate_api_key(api_key_header)
    if not is_valid:
        logger.warning("[mcc_counter_scan] Invalid or missing API key")
        return JsonResponse({"ok": False, "error": "invalid_api_key"}, status=403)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        logger.warning("[mcc_counter_scan] Invalid JSON body")
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    token = _extract_token(data)
    if not token:
        logger.warning("[mcc_counter_scan] Missing token")
        return JsonResponse({"ok": False, "error": "missing_token"}, status=400)

    account = (
        MinecraftPlayAccount.objects.filter(is_active=True)
        .filter(models_q_id_or_short(token))
        .first()
    )
    if account is None:
        logger.info("[mcc_counter_scan] Unknown token=%s", token)
        return JsonResponse(
            {"ok": False, "error": "unknown_token", "token": token},
            status=404,
        )

    try:
        session = start_player_session(token, source=MCSession.SOURCE_RFID)
    except AccountAlreadyActiveError:
        logger.info(
            "[mcc_counter_scan] Already active account=%s token=%s",
            account.short_name,
            token,
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "already_active",
                "account": account.short_name,
            },
            status=409,
        )
    except RconSequenceError as exc:
        logger.error(
            "[mcc_counter_scan] RCON failed account=%s detail=%s",
            account.short_name,
            exc,
        )
        return JsonResponse(
            {"ok": False, "error": "rcon_failed", "detail": str(exc)},
            status=502,
        )
    except SessionControlError as exc:
        code = getattr(exc, "code", "session_error") or "session_error"
        logger.warning(
            "[mcc_counter_scan] SessionControlError account=%s code=%s detail=%s",
            account.short_name,
            code,
            exc,
        )
        return JsonResponse(
            {"ok": False, "error": code, "detail": str(exc)},
            status=400,
        )

    logger.info(
        "[mcc_counter_scan] Session started account=%s session_id=%s source=rfid",
        session.account_name,
        session.session_id,
    )
    return JsonResponse(
        {
            "ok": True,
            "account": session.account_name,
            "session_id": str(session.session_id),
            "ends_at": session.ends_at.isoformat() if session.ends_at else None,
            "duration_minutes": session.duration_minutes,
        },
        status=200,
    )
