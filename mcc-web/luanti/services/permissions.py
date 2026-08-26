# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from typing import Protocol

from django.contrib.auth.models import AnonymousUser


class UserLike(Protocol):
    is_authenticated: bool
    is_active: bool
    is_staff: bool
    is_superuser: bool

    def has_perm(self, perm: str, obj=None) -> bool: ...


def _ok(user: UserLike) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


def user_can_access_luanti_control(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.access_luanti_control")


def user_can_access_luanti_city(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.access_luanti_city")


def user_can_access_luanti_shop(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.access_luanti_shop")


def user_can_access_luanti_arena(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.access_luanti_arena")


def user_can_manage_luanti_accounts(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.manage_luanti_accounts")


def user_can_manage_luanti_sessions(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.manage_luanti_sessions")


def user_can_manage_luanti_stations(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.manage_luanti_stations")


def user_can_manage_luanti_regions(user: UserLike) -> bool:
    if not _ok(user):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("luanti.manage_luanti_regions") or user.has_perm(
        "luanti.access_luanti_city"
    )


def can_access_luanti_control(user) -> bool:
    if isinstance(user, AnonymousUser) or user is None:
        return False
    return user_can_access_luanti_control(user)
