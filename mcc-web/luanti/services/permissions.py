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


def user_can_view_luanti_account_password(user: UserLike) -> bool:
    """Plaintext Luanti login passwords — system administrators only."""
    return _ok(user) and user.is_superuser


def user_can_set_luanti_account_password(user: UserLike) -> bool:
    """Set or reset Luanti login passwords — system administrators only."""
    return _ok(user) and user.is_superuser


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


def operator_session_top_ids(user: UserLike) -> set[int] | None:
    """
    TOP group PKs the staff user may see on Luanti session tiles.

    None = unrestricted (superuser). Empty set = no managed TOPs.
    Non-superusers are limited to their managed_groups that are TOP roots.
    """
    if not _ok(user):
        return set()
    if user.is_superuser:
        return None
    managed = getattr(user, "managed_groups", None)
    if managed is None:
        return set()
    return set(managed.filter(parent__isnull=True).values_list("id", flat=True))


def account_in_operator_session_scope(user: UserLike, account) -> bool:
    """Whether this Luanti account is visible/startable for the operator."""
    allowed = operator_session_top_ids(user)
    if allowed is None:
        return True
    home_id = getattr(account, "assigned_to_group_id", None)
    if home_id is None:
        return False
    return int(home_id) in allowed


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
