# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

from minecraft.models import MinecraftRconPreset

UserLike = AbstractBaseUser | AnonymousUser


def user_can_access_minecraft_control(user: UserLike) -> bool:
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return (
        user.has_perm("minecraft.run_rconpreset")
        or user.has_perm("minecraft.change_minecraftrconpreset")
        or user.has_perm("minecraft.add_minecraftrconpreset")
    )


def user_can_manage_presets(user: UserLike) -> bool:
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.change_minecraftrconpreset") or user.has_perm(
        "minecraft.add_minecraftrconpreset"
    )


def user_can_run_preset(user: UserLike, preset: MinecraftRconPreset) -> bool:
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
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
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False
    if preset.is_system:
        return getattr(user, "is_superuser", False) or user.has_perm(
            "minecraft.delete_system_rconpreset"
        )
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.delete_minecraftrconpreset")


def user_can_export_presets(user: UserLike) -> bool:
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("minecraft.export_rconpreset")
