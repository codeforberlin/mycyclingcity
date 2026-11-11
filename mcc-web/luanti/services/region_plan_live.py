# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Admin actions for plan live conversion on protected regions.

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model

from luanti.models import LuantiProtectedRegion
from luanti.services.plan import (
    materialize_blocks,
    region_summary,
    set_plan_live_convert,
)

User = get_user_model()


def plan_summary_for_admin(region: LuantiProtectedRegion) -> dict:
    summary = region_summary(region)
    summary["live_active"] = bool(region.plan_live_convert_active)
    summary["live_started_at"] = region.plan_live_convert_started_at
    if region.plan_live_convert_started_by_id:
        summary["live_started_by"] = (
            region.plan_live_convert_started_by.get_username()
            if region.plan_live_convert_started_by
            else ""
        )
    else:
        summary["live_started_by"] = ""
    return summary


def admin_convert_once(region: LuantiProtectedRegion, *, max_count: int = 4) -> dict:
    """Manual single batch without toggling live flag (testing / operator)."""
    max_count = max(1, min(int(max_count or 4), 256))
    tx_id = f"admin-once-{region.pk}-{uuid.uuid4().hex[:12]}"
    result = materialize_blocks(
        login_name="",
        region_id=region.region_id,
        client_tx_id=tx_id,
        max_count=max_count,
        mode="auto",
    )
    return result


def start_plan_live(region: LuantiProtectedRegion, user: User | None) -> LuantiProtectedRegion:
    return set_plan_live_convert(region, active=True, user=user)


def stop_plan_live(region: LuantiProtectedRegion, user: User | None) -> LuantiProtectedRegion:
    return set_plan_live_convert(region, active=False, user=user)
