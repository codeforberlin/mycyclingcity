# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    city.py
# @note    City presets and protected-region catalog for the Luanti bridge.

from __future__ import annotations

import colorsys
import hashlib

from django.utils import timezone

from luanti.models import LuantiCityPreset, LuantiIntegrationConfig, LuantiProtectedRegion

_PALETTE_SIZE = 12


def region_outline_rgb(region_id: str) -> list[int]:
    """Stable RGB 0–255 from region_id hash (same palette idea as Minecraft)."""
    digest = hashlib.sha1((region_id or "").encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % _PALETTE_SIZE
    hue = idx / float(_PALETTE_SIZE)
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return [int(r * 255), int(g * 255), int(b * 255)]


def build_regions_payload() -> dict:
    config = LuantiIntegrationConfig.get_config()
    rows = []
    qs = (
        LuantiProtectedRegion.objects.filter(enabled=True)
        .select_related("parent")
        .prefetch_related("members")
        .order_by("sort_order", "region_id")
    )
    for r in qs:
        members = list(
            r.members.filter(is_active=True).values_list("login_name", flat=True)
        )
        min_x, min_y, min_z, max_x, max_y, max_z = r.normalized_bounds()
        row = {
            "region_id": r.region_id,
            "display_name": r.display_name or r.region_id,
            "world": r.world,
            "min": [min_x, min_y, min_z],
            "max": [max_x, max_y, max_z],
            "min_x": min_x,
            "min_y": min_y,
            "min_z": min_z,
            "max_x": max_x,
            "max_y": max_y,
            "max_z": max_z,
            "protect_build": r.protect_build,
            "parent_id": r.parent.region_id if r.parent_id else None,
            "members": sorted(members, key=str.lower),
            "color_rgb": region_outline_rgb(r.region_id),
        }
        if r.has_custom_spawn:
            row["spawn"] = [r.spawn_x, r.spawn_y, r.spawn_z]
        rows.append(row)
    return {
        "ok": True,
        "version": 1,
        "outline_enabled": bool(getattr(config, "region_outline_enabled", True)),
        "enter_hint_enabled": bool(getattr(config, "region_outline_enter_hint", True)),
        "view_distance": int(getattr(config, "region_outline_view_distance", 48) or 48),
        "regions": rows,
    }


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
