# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    api_pulse.py
# @note    Arena API-Live: pulse distance through /api/update-data.

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.test import RequestFactory

from config.logger_utils import get_logger

logger = get_logger("minecraft")


@dataclass(frozen=True)
class PulseTarget:
    lane_id: str
    cyclist_key: str
    id_tag: str
    device_name: str


def resolve_pulse_targets(assignments: list[dict[str, Any]]) -> list[PulseTarget]:
    """Map arena assignments to update-data id_tag + device_id pairs."""
    from api.models import Cyclist

    targets: list[PulseTarget] = []
    for entry in assignments:
        cyclist_key = str(entry.get("cyclist") or "").strip()
        device_name = str(entry.get("device_name") or "").strip()
        lane_id = str(entry.get("lane_id") or "").strip()
        if not cyclist_key or not device_name or not lane_id:
            continue
        cyclist = (
            Cyclist.objects.filter(user_id=cyclist_key).first()
            or Cyclist.objects.filter(id_tag=cyclist_key).first()
        )
        if cyclist is None or not cyclist.id_tag:
            raise ValueError(f"Kein id_tag für Radler „{cyclist_key}“")
        targets.append(
            PulseTarget(
                lane_id=lane_id,
                cyclist_key=cyclist_key,
                id_tag=str(cyclist.id_tag),
                device_name=device_name,
            )
        )
    return targets


def pulse_distance_km(*, id_tag: str, device_name: str, distance_km: float) -> tuple[bool, str]:
    """
    Post one distance delta through the real update_data view (API path).

    Uses RequestFactory so the arena worker does not depend on Gunicorn HTTP.
    Returns (ok, error_message).
    """
    if distance_km <= 0:
        return True, ""

    from api.views import update_data

    api_key = getattr(settings, "MCC_APP_API_KEY", "") or ""
    if not api_key:
        return False, "MCC_APP_API_KEY fehlt"

    body = {
        "id_tag": id_tag,
        "device_id": device_name,
        "distance": str(Decimal(str(round(distance_km, 8)))),
    }
    factory = RequestFactory()
    request = factory.post(
        "/api/update-data",
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )
    try:
        response = update_data(request)
    except Exception as exc:
        logger.exception("[arena_api_pulse] update_data failed")
        return False, str(exc)

    payload: dict[str, Any] = {}
    try:
        payload = json.loads(response.content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        payload = {}

    if response.status_code != 200:
        err = payload.get("error") or f"HTTP {response.status_code}"
        return False, str(err)
    if payload.get("skipped"):
        return False, str(payload.get("message") or payload.get("reason") or "update-data skipped")
    if payload.get("success") is False:
        return False, str(payload.get("error") or "update-data failed")
    return True, ""


def pulse_meters(*, id_tag: str, device_name: str, distance_m: float) -> tuple[bool, str]:
    """Convenience: meters → km for update-data."""
    return pulse_distance_km(
        id_tag=id_tag,
        device_name=device_name,
        distance_km=float(distance_m) / 1000.0,
    )
