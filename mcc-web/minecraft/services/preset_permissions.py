# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

from minecraft.models import MinecraftRconPreset

UserLike = AbstractBaseUser | AnonymousUser


def _is_active_staff(user: UserLike) -> bool:
    return bool(getattr(user, "is_active", False) and getattr(user, "is_staff", False))


def user_can_access_minecraft_control(user: UserLike) -> bool:
    """
    Control page access: explicit perm, or legacy preset perms so existing
    moderators keep working.
    """
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return (
        user.has_perm("minecraft.access_minecraft_control")
        or user.has_perm("minecraft.run_rconpreset")
        or user.has_perm("minecraft.change_minecraftrconpreset")
        or user.has_perm("minecraft.add_minecraftrconpreset")
    )


def user_can_access_minecraft_city(user: UserLike) -> bool:
    """Stadtsteuerung: explicit perm, or legacy run_rconpreset."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.access_minecraft_city") or user.has_perm(
        "minecraft.run_rconpreset"
    )


def user_can_access_minecraft_shop(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.access_minecraft_shop")


def user_can_run_free_rcon(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.run_free_rcon")


def user_can_manage_player_sessions(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_player_sessions")


def user_can_manage_grant_catalog(user: UserLike) -> bool:
    """Vergabe-Katalog (Fahrzeuge / Items) in der Stadtsteuerung."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_grant_catalog")


def user_can_run_arena_sim(user: UserLike) -> bool:
    """Arena distance-simulation GUI (permission: minecraft.run_arena_sim)."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.run_arena_sim")


def user_can_manage_minecraft_proxy(user: UserLike) -> bool:
    """Start/stop Velocity proxy and Limbo waiting room."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_minecraft_proxy")


def user_can_manage_auth_failover(user: UserLike) -> bool:
    """Auth-Failover mode and playerdata online/offline migration."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_auth_failover")


def user_can_manage_coreprotect(user: UserLike) -> bool:
    """CoreProtect rollback/restore for player time ranges."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_coreprotect")


def user_can_manage_protected_regions(user: UserLike) -> bool:
    """WorldGuard protected regions in Stadtsteuerung."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_protected_regions")


def user_can_manage_assigned_protected_regions(user: UserLike) -> bool:
    """TOP operators: manage subregions inside their assigned master regions."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_assigned_protected_regions")


def user_can_manage_builder_sessions(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_builder_sessions")


def user_can_manage_minecraft_accounts(user: UserLike) -> bool:
    """Unified play/builder account stammdaten in Admin."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_minecraft_accounts")


def user_can_manage_minecraft_operators(user: UserLike) -> bool:
    """Vanilla /op and /deop via RCON (not for low-privilege session operators)."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_minecraft_operators")


def user_can_manage_minecraft_stations(user: UserLike) -> bool:
    """Physical PCs and MS allowlist management."""
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.manage_minecraft_stations")


def user_can_manage_presets(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.change_minecraftrconpreset") or user.has_perm(
        "minecraft.add_minecraftrconpreset"
    )


def user_can_run_preset(user: UserLike, preset: MinecraftRconPreset) -> bool:
    if not _is_active_staff(user):
        return False
    if not preset.enabled:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not user.has_perm("minecraft.run_rconpreset"):
        return False
    if user.has_perm("minecraft.change_system_rconpreset"):
        return True
    if preset.category == MinecraftRconPreset.CATEGORY_WORLD:
        return True
    if preset.moderator_can_run:
        return True
    return False


def user_can_edit_preset(user: UserLike, preset: MinecraftRconPreset | None = None) -> bool:
    if not user_can_manage_presets(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if preset is None:
        return user.has_perm("minecraft.add_minecraftrconpreset")
    if preset.is_system and not user.has_perm("minecraft.change_system_rconpreset"):
        return False
    return user.has_perm("minecraft.change_minecraftrconpreset")


def user_can_delete_preset(user: UserLike, preset: MinecraftRconPreset) -> bool:
    if not _is_active_staff(user):
        return False
    if preset.is_system:
        return getattr(user, "is_superuser", False) or user.has_perm(
            "minecraft.delete_system_rconpreset"
        )
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.delete_minecraftrconpreset")


def user_can_export_presets(user: UserLike) -> bool:
    if not _is_active_staff(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.export_rconpreset")
