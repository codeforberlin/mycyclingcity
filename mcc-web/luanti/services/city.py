# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.utils import timezone

from luanti.models import LuantiCityPreset, LuantiProtectedRegion


def build_regions_payload() -> dict:
    rows = []
    for r in LuantiProtectedRegion.objects.filter(enabled=True).order_by("sort_order", "region_id"):
        rows.append(
            {
                "region_id": r.region_id,
                "display_name": r.display_name or r.region_id,
                "world": r.world,
                "min": [r.min_x, r.min_y, r.min_z],
                "max": [r.max_x, r.max_y, r.max_z],
                "protect_build": r.protect_build,
            }
        )
    return {"ok": True, "regions": rows}


def mark_preset_run(preset: LuantiCityPreset, *, user, success: bool, output: str) -> None:
    preset.last_run_at = timezone.now()
    preset.last_run_by = user if getattr(user, "is_authenticated", False) else None
    preset.last_run_success = success
    preset.last_run_output = (output or "")[:5000]
    preset.save(
        update_fields=[
            "last_run_at",
            "last_run_by",
            "last_run_success",
            "last_run_output",
        ]
    )


def preset_event_payload(preset: LuantiCityPreset) -> dict:
    return {
        "type": "RUN_CITY_PRESET",
        "slug": preset.slug,
        "name": preset.name,
        "steps": preset.steps or [],
    }
