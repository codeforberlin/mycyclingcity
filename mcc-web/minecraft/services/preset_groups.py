# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    preset_groups.py
# @note    Convenience Django auth groups for Minecraft admin menus.

from __future__ import annotations

from django.contrib.auth.models import Group, Permission

# All Minecraft admin menu functions (custom + model perms for arena/shop tiles).
# Assign group ``minecraft_admin`` to staff users who operate the Minecraft app.
MINECRAFT_ADMIN_PERMISSION_CODENAMES: tuple[str, ...] = (
    # Control / city / shop surfaces
    "access_minecraft_control",
    "access_minecraft_city",
    "access_minecraft_shop",
    "run_free_rcon",
    # Sessions & waitlist
    "manage_player_sessions",
    "manage_builder_sessions",
    # Accounts / stations / OP
    "manage_minecraft_accounts",
    "manage_minecraft_operators",
    "manage_minecraft_stations",
    # Proxy / auth failover / CoreProtect / regions
    "manage_minecraft_proxy",
    "manage_auth_failover",
    "manage_coreprotect",
    "manage_protected_regions",
    "manage_assigned_protected_regions",
    # Arena
    "run_arena_sim",
    "view_minecraftarenalane",
    "add_minecraftarenalane",
    "change_minecraftarenalane",
    "delete_minecraftarenalane",
    "view_minecraftarenamotionsettings",
    "change_minecraftarenamotionsettings",
    # Shop catalog (menu tiles beyond Shop-Ops)
    "view_minecraftshopitem",
    "add_minecraftshopitem",
    "change_minecraftshopitem",
    "delete_minecraftshopitem",
    "view_minecraftshopcategory",
    "add_minecraftshopcategory",
    "change_minecraftshopcategory",
    "delete_minecraftshopcategory",
    "view_minecraftshoppurchasecredit",
    "add_minecraftshoppurchasecredit",
    "change_minecraftshoppurchasecredit",
    "delete_minecraftshoppurchasecredit",
    # RCON presets
    "view_minecraftrconpreset",
    "add_minecraftrconpreset",
    "change_minecraftrconpreset",
    "delete_minecraftrconpreset",
    "run_rconpreset",
    "change_system_rconpreset",
    "export_rconpreset",
)

# Operator group keeps the previous (slightly smaller) set for backward compatibility.
MCC_OPERATOR_PERMISSION_CODENAMES: tuple[str, ...] = (
    "access_minecraft_control",
    "access_minecraft_city",
    "access_minecraft_shop",
    "run_free_rcon",
    "manage_player_sessions",
    "manage_builder_sessions",
    "manage_minecraft_accounts",
    "manage_minecraft_operators",
    "manage_minecraft_stations",
    "run_arena_sim",
    "manage_minecraft_proxy",
    "manage_auth_failover",
    "manage_coreprotect",
    "manage_protected_regions",
    "manage_assigned_protected_regions",
    "add_minecraftrconpreset",
    "change_minecraftrconpreset",
    "delete_minecraftrconpreset",
    "run_rconpreset",
    "change_system_rconpreset",
    "export_rconpreset",
    "view_minecraftrconpreset",
)

MINECRAFT_MODERATOR_PERMISSION_CODENAMES: tuple[str, ...] = (
    "access_minecraft_city",
    "run_rconpreset",
    "view_minecraftrconpreset",
    "manage_player_sessions",
    "run_arena_sim",
)

PRESET_GROUP_SPECS: dict[str, tuple[str, ...]] = {
    "minecraft_admin": MINECRAFT_ADMIN_PERMISSION_CODENAMES,
    "mcc_operator": MCC_OPERATOR_PERMISSION_CODENAMES,
    "minecraft_moderator": MINECRAFT_MODERATOR_PERMISSION_CODENAMES,
    "minecraft_arena_sim": ("run_arena_sim",),
    "mcc_viewer": ("view_minecraftrconpreset",),
}


def sync_minecraft_preset_groups(*, clear_existing: bool = True) -> list[tuple[str, bool, list[str]]]:
    """
    Create/update convenience auth groups for Minecraft admin menus.

    Returns a list of (group_name, created, missing_codenames).
    """
    codenames = sorted({c for specs in PRESET_GROUP_SPECS.values() for c in specs})
    perm_map = {
        perm.codename: perm
        for perm in Permission.objects.filter(
            content_type__app_label="minecraft",
            codename__in=codenames,
        )
    }

    results: list[tuple[str, bool, list[str]]] = []
    for group_name, group_codenames in PRESET_GROUP_SPECS.items():
        group, created = Group.objects.get_or_create(name=group_name)
        if clear_existing:
            group.permissions.clear()
        missing: list[str] = []
        for codename in group_codenames:
            perm = perm_map.get(codename)
            if perm is None:
                missing.append(codename)
                continue
            group.permissions.add(perm)
        results.append((group_name, created, missing))
    return results
