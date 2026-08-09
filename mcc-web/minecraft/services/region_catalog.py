# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_catalog.py
# @note    WS payload of protected regions for MCC-Bridge particle outlines.

from __future__ import annotations

import colorsys
import hashlib

from minecraft.models import MinecraftIntegrationConfig, MinecraftProtectedRegion
from minecraft.services.region_ops import desired_member_logins


# Distinct, saturated hues for region outlines (builders share one scoreboard color).
_PALETTE_SIZE = 12


def region_outline_rgb(region_id: str) -> list[int]:
    """Stable RGB 0–255 from region_id hash (evenly spaced hues)."""
    digest = hashlib.sha1((region_id or "").encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % _PALETTE_SIZE
    hue = idx / float(_PALETTE_SIZE)
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return [int(r * 255), int(g * 255), int(b * 255)]


def build_protected_regions_payload() -> dict:
    """
    Catalog of WorldGuard-managed cuboids for in-game particle outlines.

    Shape:
      {
        "version": 1,
        "outline_enabled": true,
        "enter_hint_enabled": true,
        "view_distance": 48,
        "regions": [ { region_id, display_name, world, bounds, color_rgb, ... } ]
      }
    """
    config = MinecraftIntegrationConfig.get_config()
    regions: list[dict] = []
    qs = (
        MinecraftProtectedRegion.objects.select_related(
            "parent", "assigned_to_group", "parent__assigned_to_group"
        )
        .prefetch_related("builders")
        .order_by("sort_order", "region_id", "parent_id")
    )
    for region in qs:
        min_x, min_y, min_z, max_x, max_y, max_z = region.normalized_bounds()
        members = desired_member_logins(region)
        builder_names = [
            (b.mc_username or "").strip()
            for b in region.builders.all()
            if (b.mc_username or "").strip()
        ]
        regions.append(
            {
                "region_id": region.region_id,
                "display_name": (region.display_name or "").strip() or region.region_id,
                "world": (region.world or "").strip() or "MyCyclingCity",
                "kind": region.region_kind,
                "parent_id": region.parent.region_id if region.parent_id else None,
                "assigned_group": (
                    (region.effective_top_group().name if region.effective_top_group() else "")
                    or ""
                ),
                "min_x": min_x,
                "min_y": min_y,
                "min_z": min_z,
                "max_x": max_x,
                "max_y": max_y,
                "max_z": max_z,
                "protect_build": bool(region.protect_build),
                "color_rgb": region_outline_rgb(region.region_id),
                "members": members,
                "builder_teams": builder_names,
            }
        )

    return {
        "version": 1,
        "outline_enabled": bool(getattr(config, "region_outline_enabled", True)),
        "enter_hint_enabled": bool(getattr(config, "region_outline_enter_hint", True)),
        "view_distance": int(getattr(config, "region_outline_view_distance", 48) or 48),
        "regions": regions,
    }
