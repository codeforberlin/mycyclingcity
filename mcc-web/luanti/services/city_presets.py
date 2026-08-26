# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re
from typing import Any

from django.db.models import Q, QuerySet
from django.utils.text import slugify

from luanti.city_preset_defaults import CITY_PRESET_SEEDS
from luanti.consumers import LuantiEventConsumer
from luanti.models import LuantiCityPreset
from luanti.services.city import mark_preset_run, preset_event_payload


def unique_slug_from_name(name: str, *, exclude_pk: int | None = None) -> str:
    base = slugify(name)[:50] or "preset"
    slug = base
    n = 2
    while True:
        qs = LuantiCityPreset.objects.filter(slug=slug)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        slug = f"{base}-{n}"
        n += 1


def filter_presets_for_list(
    *,
    category: str | None = None,
    enabled: str | None = None,
    query: str | None = None,
) -> QuerySet[LuantiCityPreset]:
    qs = LuantiCityPreset.objects.all().order_by("sort_order", "name")
    if category:
        qs = qs.filter(category=category)
    if enabled == "1":
        qs = qs.filter(enabled=True)
    elif enabled == "0":
        qs = qs.filter(enabled=False)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    return qs

def duplicate_preset(preset: LuantiCityPreset) -> LuantiCityPreset:
    copy = LuantiCityPreset(
        slug=unique_slug_from_name(f"{preset.name} copy"),
        name=f"{preset.name} (Kopie)",
        category=preset.category,
        description=preset.description,
        steps=list(preset.steps or []),
        sort_order=preset.sort_order,
        enabled=False,
        is_system=False,
        moderator_can_run=preset.moderator_can_run,
        requires_confirmation=preset.requires_confirmation,
    )
    copy.save()
    return copy


def run_city_preset(preset: LuantiCityPreset, *, user) -> tuple[bool, str]:
    payload = preset_event_payload(preset)
    sent = LuantiEventConsumer.push_to_all_sync(payload)
    if sent > 0:
        msg = f"An {sent} Bridge(s) gesendet/eingereiht."
        mark_preset_run(preset, user=user, success=True, output=msg)
        return True, msg
    msg = "Keine Bridge verbunden / Befehl nicht zugestellt."
    mark_preset_run(preset, user=user, success=False, output=msg)
    return False, msg


def upsert_seed_presets() -> list[str]:
    """Create missing seed presets; do not overwrite existing DB steps (GUI is source of truth)."""
    created: list[str] = []
    for seed in CITY_PRESET_SEEDS:
        obj, was_created = LuantiCityPreset.objects.get_or_create(
            slug=seed["slug"],
            defaults={
                "name": seed["name"],
                "category": seed.get("category", LuantiCityPreset.CATEGORY_WORLD),
                "description": seed.get("description", ""),
                "steps": list(seed.get("steps") or []),
                "sort_order": seed.get("sort_order", 0),
                "enabled": seed.get("enabled", True),
                "is_system": seed.get("is_system", False),
                "moderator_can_run": seed.get("moderator_can_run", False),
                "requires_confirmation": seed.get("requires_confirmation", True),
            },
        )
        if was_created:
            created.append(obj.slug)
        elif not obj.is_system and seed.get("is_system"):
            # Promote known seeds to system if they already existed from older migrations.
            LuantiCityPreset.objects.filter(pk=obj.pk).update(
                is_system=True,
                category=seed.get("category", obj.category),
                moderator_can_run=seed.get("moderator_can_run", obj.moderator_can_run),
            )
        elif obj.slug in {"daytime", "nighttime", "session-bootstrap"} and not obj.is_system:
            LuantiCityPreset.objects.filter(pk=obj.pk).update(is_system=True)
    return created


def preset_to_export_dict(preset: LuantiCityPreset) -> dict[str, Any]:
    return {
        "slug": preset.slug,
        "name": preset.name,
        "category": preset.category,
        "description": preset.description,
        "steps": list(preset.steps or []),
        "sort_order": preset.sort_order,
        "enabled": preset.enabled,
        "is_system": preset.is_system,
        "moderator_can_run": preset.moderator_can_run,
        "requires_confirmation": preset.requires_confirmation,
    }


_SLUG_SAFE = re.compile(r"[^a-z0-9_-]+")


def sanitize_import_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    s = _SLUG_SAFE.sub("-", s).strip("-")[:64]
    return s or "preset"
