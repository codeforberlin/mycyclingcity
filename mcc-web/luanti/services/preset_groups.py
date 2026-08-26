# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.contrib.auth.models import Group, Permission

LUANTI_ADMIN_PERMISSION_CODENAMES: tuple[str, ...] = (
    "access_luanti_control",
    "access_luanti_city",
    "access_luanti_shop",
    "access_luanti_arena",
    "manage_luanti_accounts",
    "manage_luanti_sessions",
    "manage_luanti_stations",
    "view_luantiaccount",
    "add_luantiaccount",
    "change_luantiaccount",
    "delete_luantiaccount",
    "view_luantishopitem",
    "add_luantishopitem",
    "change_luantishopitem",
    "delete_luantishopitem",
    "view_luantishopcategory",
    "add_luantishopcategory",
    "change_luantishopcategory",
    "delete_luantishopcategory",
    "view_luanticitypreset",
    "add_luanticitypreset",
    "change_luanticitypreset",
    "delete_luanticitypreset",
    "run_citypreset",
    "change_system_citypreset",
    "delete_system_citypreset",
    "view_luantiarenalane",
    "add_luantiarenalane",
    "change_luantiarenalane",
    "delete_luantiarenalane",
    "view_luantistation",
    "add_luantistation",
    "change_luantistation",
    "delete_luantistation",
)

LUANTI_MODERATOR_PERMISSION_CODENAMES: tuple[str, ...] = (
    "access_luanti_control",
    "access_luanti_city",
    "manage_luanti_sessions",
    "access_luanti_arena",
    "run_citypreset",
    "view_luanticitypreset",
)

PRESET_GROUP_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("luanti_admin", LUANTI_ADMIN_PERMISSION_CODENAMES),
    ("luanti_moderator", LUANTI_MODERATOR_PERMISSION_CODENAMES),
)


def sync_luanti_preset_groups() -> list[tuple[str, bool, list[str]]]:
    results: list[tuple[str, bool, list[str]]] = []
    for group_name, codenames in PRESET_GROUP_SPECS:
        group, created = Group.objects.get_or_create(name=group_name)
        perms = list(
            Permission.objects.filter(
                content_type__app_label="luanti",
                codename__in=codenames,
            )
        )
        found = {p.codename for p in perms}
        missing = [c for c in codenames if c not in found]
        group.permissions.set(perms)
        results.append((group_name, created, missing))
    return results
