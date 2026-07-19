# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json

from django.contrib.auth.models import AbstractBaseUser
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from minecraft.models import MinecraftRconPreset
from minecraft.services import rcon_client
from minecraft.services.preset_permissions import user_can_run_preset


def get_enabled_presets():
    return MinecraftRconPreset.objects.filter(enabled=True).order_by(
        "category", "sort_order", "name"
    )


def presets_grouped() -> list[dict]:
    """Return enabled presets grouped by category for the admin UI."""
    groups: dict[str, list[MinecraftRconPreset]] = {}
    for preset in get_enabled_presets():
        groups.setdefault(preset.category, []).append(preset)

    category_labels = dict(MinecraftRconPreset.CATEGORY_CHOICES)
    ordered_categories = [choice[0] for choice in MinecraftRconPreset.CATEGORY_CHOICES]
    result = []
    for category in ordered_categories:
        presets = groups.get(category)
        if not presets:
            continue
        result.append(
            {
                "category": category,
                "label": category_labels.get(category, category),
                "presets": presets,
            }
        )
    return result


def filter_presets_for_list(
    *,
    category: str | None = None,
    enabled: str | None = None,
    query: str | None = None,
):
    qs = MinecraftRconPreset.objects.all().order_by("category", "sort_order", "name")
    if category:
        qs = qs.filter(category=category)
    if enabled == "1":
        qs = qs.filter(enabled=True)
    elif enabled == "0":
        qs = qs.filter(enabled=False)
    if query:
        qs = qs.filter(
            models.Q(name__icontains=query)
            | models.Q(slug__icontains=query)
            | models.Q(description__icontains=query)
        )
    return qs


def record_preset_run(
    preset: MinecraftRconPreset,
    *,
    user: AbstractBaseUser | None,
    success: bool,
    output: str,
) -> None:
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


def run_preset(
    preset_id: int,
    *,
    user: AbstractBaseUser | None = None,
    test_first_only: bool = False,
) -> tuple[bool, str]:
    try:
        preset = MinecraftRconPreset.objects.get(pk=preset_id, enabled=True)
    except MinecraftRconPreset.DoesNotExist:
        return False, _("Preset nicht gefunden oder deaktiviert.")

    if user is not None and not user_can_run_preset(user, preset):
        return False, _("Keine Berechtigung, dieses Preset auszuführen.")

    commands = list(preset.commands or [])
    if test_first_only and commands:
        commands = commands[:1]

    success, output = rcon_client.run_commands(
        commands,
        stop_on_error=preset.stop_on_error,
    )
    header = _("Preset „%(name)s“:") % {"name": preset.name}
    message = f"{header}\n{output}"
    record_preset_run(preset, user=user, success=success, output=message)
    return success, message


@transaction.atomic
def duplicate_preset(preset: MinecraftRconPreset) -> MinecraftRconPreset:
    base_slug = f"{preset.slug}-kopie"
    slug = base_slug
    counter = 2
    while MinecraftRconPreset.objects.filter(slug=slug).exists():
        slug = f"{preset.slug}-kopie-{counter}"
        counter += 1

    return MinecraftRconPreset.objects.create(
        slug=slug,
        name=f"{preset.name} (Kopie)",
        category=preset.category,
        description=preset.description,
        commands=list(preset.commands or []),
        sort_order=preset.sort_order,
        enabled=preset.enabled,
        is_system=False,
        moderator_can_run=preset.moderator_can_run,
        requires_confirmation=preset.requires_confirmation,
        stop_on_error=preset.stop_on_error,
    )


def export_presets_json(presets) -> str:
    payload = []
    for preset in presets:
        payload.append(
            {
                "slug": preset.slug,
                "name": preset.name,
                "category": preset.category,
                "description": preset.description,
                "commands": preset.commands,
                "sort_order": preset.sort_order,
                "enabled": preset.enabled,
                "moderator_can_run": preset.moderator_can_run,
                "requires_confirmation": preset.requires_confirmation,
                "stop_on_error": preset.stop_on_error,
                "is_system": preset.is_system,
            }
        )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def unique_slug_from_name(name: str, *, exclude_pk: int | None = None) -> str:
    base = slugify(name, allow_unicode=False).replace("-", "_") or "preset"
    slug = base[:64]
    counter = 2
    while True:
        qs = MinecraftRconPreset.objects.filter(slug=slug)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        suffix = f"-{counter}"
        slug = f"{base[: 64 - len(suffix)]}{suffix}"
        counter += 1
