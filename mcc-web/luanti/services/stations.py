# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from luanti.models import LuantiStation


def station_desired_payload(station: LuantiStation) -> dict:
    cfg = dict(station.desired_config or {})
    server = cfg.get("server") or {
        "address": getattr(settings, "MCC_LUANTI_CLIENT_ADDRESS", "127.0.0.1"),
        "port": int(getattr(settings, "MCC_LUANTI_CLIENT_PORT", 30000)),
    }
    account = station.default_account
    login_name = account.login_name if account else cfg.get("login_name", "")
    password = ""
    if account and getattr(account, "login_password", None):
        password = account.login_password
    if not password:
        password = cfg.get("password", "") or ""
    return {
        "ok": True,
        "station": station.name,
        "hostname": station.hostname,
        "server": server,
        "account": {
            "login_name": login_name or "",
            "password": password,
        },
        "autostart": bool(cfg.get("autostart", True)),
        "fullscreen": bool(cfg.get("fullscreen", True)),
        "updated_at": station.updated_at.isoformat() if station.updated_at else None,
    }


def touch_station(station: LuantiStation, *, reported: dict | None = None, error: str = "") -> None:
    station.last_seen_at = timezone.now()
    if reported is not None:
        station.reported_config = reported
    if error is not None:
        station.last_error = error or ""
    station.save(update_fields=["last_seen_at", "reported_config", "last_error", "updated_at"])


def authenticate_station(api_key: str) -> LuantiStation | None:
    key = (api_key or "").strip()
    if not key:
        return None
    return LuantiStation.objects.filter(api_key=key, is_active=True).first()
