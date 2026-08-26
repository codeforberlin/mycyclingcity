# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from typing import Protocol

from luanti.models import LuantiCityPreset
from luanti.services.permissions import _ok


class UserLike(Protocol):
    is_authenticated: bool
    is_active: bool
    is_staff: bool
    is_superuser: bool

    def has_perm(self, perm: str, obj=None) -> bool: ...


def user_can_manage_city_presets(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.change_luanticitypreset") or user.has_perm(
        "luanti.add_luanticitypreset"
    )


def user_can_run_city_preset(user: UserLike, preset: LuantiCityPreset | None = None) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    if not (
        user.has_perm("luanti.run_citypreset")
        or user.has_perm("luanti.access_luanti_city")
        or user.has_perm("luanti.change_luanticitypreset")
    ):
        return False
    if preset is None:
        return True
    if preset.category == LuantiCityPreset.CATEGORY_WORLD:
        return True
    if preset.moderator_can_run:
        return True
    return user.has_perm("luanti.change_system_citypreset") or user.has_perm(
        "luanti.change_luanticitypreset"
    )


def user_can_edit_city_preset(user: UserLike, preset: LuantiCityPreset | None) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    if preset is None:
        return user.has_perm("luanti.add_luanticitypreset")
    if not user.has_perm("luanti.change_luanticitypreset"):
        return False
    if preset.is_system:
        return user.has_perm("luanti.change_system_citypreset")
    return True


def user_can_delete_city_preset(user: UserLike, preset: LuantiCityPreset) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    if not user.has_perm("luanti.delete_luanticitypreset"):
        return False
    if preset.is_system:
        return user.has_perm("luanti.delete_system_citypreset")
    return True
