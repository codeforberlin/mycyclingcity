# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    presence.py
# @note    Track online Luanti players waiting for session freigabe.

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from luanti.models import LuantiAccount, LuantiWaitingPlayer

# Drop from Admin list if bridge stopped refreshing (player left / crash).
STALE_AFTER = timedelta(seconds=90)


def mark_waiting(login_name: str, *, server_id: str = "") -> LuantiWaitingPlayer | None:
    name = (login_name or "").strip()
    if not name:
        return None
    account = LuantiAccount.objects.filter(login_name__iexact=name, is_active=True).first()
    if not account:
        return None
    now = timezone.now()
    entry, created = LuantiWaitingPlayer.objects.get_or_create(
        login_name=account.login_name,
        defaults={
            "account": account,
            "server_id": (server_id or "")[:64],
            "first_seen_at": now,
            "last_seen_at": now,
        },
    )
    if not created:
        entry.account = account
        entry.server_id = (server_id or entry.server_id or "")[:64]
        entry.last_seen_at = now
        entry.save(update_fields=["account", "server_id", "last_seen_at"])
    return entry


def clear_waiting(login_name: str) -> None:
    name = (login_name or "").strip()
    if not name:
        return
    LuantiWaitingPlayer.objects.filter(login_name__iexact=name).delete()


def list_waiting(*, include_stale: bool = False) -> list[LuantiWaitingPlayer]:
    qs = LuantiWaitingPlayer.objects.select_related("account").order_by("-last_seen_at")
    if include_stale:
        return list(qs)
    cutoff = timezone.now() - STALE_AFTER
    return list(qs.filter(last_seen_at__gte=cutoff))


def purge_stale_waiting() -> int:
    cutoff = timezone.now() - STALE_AFTER
    deleted, _ = LuantiWaitingPlayer.objects.filter(last_seen_at__lt=cutoff).delete()
    return int(deleted)
