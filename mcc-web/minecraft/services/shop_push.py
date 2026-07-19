# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hmac
import json
import uuid

import requests
from django.conf import settings

from config.logger_utils import get_logger
from minecraft.services.bridge_connection import get_connected_server_ids


logger = get_logger("minecraft")


def push_shop_catalog_to_minecraft(server_id: str | None = None) -> tuple[bool, str]:
    """
    Ask a connected MCC-Bridge (via Daphne internal HTTP) to sync the shop catalog.
    """
    if not settings.MCC_MINECRAFT_WS_ENABLED:
        return False, "WebSocket ist deaktiviert"

    target_server_id = server_id or _default_server_id()
    if not target_server_id:
        return False, "Keine server_id konfiguriert"

    allowed = settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS
    if target_server_id not in allowed:
        return False, f"server_id '{target_server_id}' ist nicht erlaubt"

    if target_server_id not in get_connected_server_ids():
        return False, (
            f"Keine aktive MCC-Bridge-Verbindung für '{target_server_id}'. "
            "Auf dem MC-Server /mccbridge status prüfen oder Plugin neu laden."
        )

    url = (
        f"http://127.0.0.1:{settings.MCC_MINECRAFT_WS_PORT}"
        "/internal/minecraft/push-shop/"
    )
    request_id = f"admin-push-{uuid.uuid4().hex[:12]}"
    payload = {"server_id": target_server_id, "request_id": request_id}

    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-MCC-Internal-Secret": settings.MCC_MINECRAFT_WS_SHARED_SECRET,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("[minecraft_ws] internal push request failed: %s", exc)
        return False, f"Daphne-Push fehlgeschlagen: {exc}"

    if response.status_code == 200:
        logger.info(
            "[minecraft_ws] requested catalog sync push server_id=%s request_id=%s",
            target_server_id,
            request_id,
        )
        return True, f"Shop-Sync an '{target_server_id}' gesendet"

    try:
        data = response.json()
        error = data.get("error", response.text)
    except json.JSONDecodeError:
        error = response.text or f"HTTP {response.status_code}"

    return False, str(error)


def _default_server_id() -> str | None:
    allowed = settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS
    if not allowed:
        return None
    return allowed[0]
