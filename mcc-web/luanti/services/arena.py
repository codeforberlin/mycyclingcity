# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from luanti.models import LuantiArenaLane, LuantiArenaMotionSettings


def build_arena_state() -> dict:
    settings = LuantiArenaMotionSettings.get_solo()
    lanes = []
    for lane in LuantiArenaLane.objects.filter(enabled=True).order_by("sort_order", "name"):
        lanes.append(
            {
                "id": lane.pk,
                "name": lane.name,
                "start": [lane.start_x, lane.start_y, lane.start_z],
                "direction": [lane.direction_x, lane.direction_y, lane.direction_z],
                "account": lane.assigned_account.login_name if lane.assigned_account_id else None,
            }
        )
    return {
        "ok": True,
        "enabled": settings.enabled,
        "default_speed": settings.default_speed,
        "lanes": lanes,
    }


def cart_command(op: str, **kwargs) -> dict:
    """Build a WebSocket cart command for the Lua bridge."""
    return {"type": "CART_COMMAND", "op": op, **kwargs}
