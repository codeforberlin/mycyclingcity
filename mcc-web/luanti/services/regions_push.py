# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    regions_push.py
# @note    Push protected-region catalog to connected mcc_bridge clients.

from __future__ import annotations

from luanti.services.city import build_regions_payload


def push_protected_regions_to_luanti() -> tuple[bool, str]:
    """Ask connected / queued bridge to apply the current region catalog."""
    from luanti.consumers import LuantiEventConsumer

    payload = build_regions_payload()
    message = {
        "type": "REGIONS_UPDATE",
        "version": payload.get("version", 1),
        "outline_enabled": payload.get("outline_enabled", True),
        "enter_hint_enabled": payload.get("enter_hint_enabled", True),
        "view_distance": payload.get("view_distance", 48),
        "regions": payload.get("regions") or [],
    }
    sent = LuantiEventConsumer.push_to_all_sync(message)
    if sent <= 0:
        return False, "no_bridge"
    return True, f"sent={sent}"
