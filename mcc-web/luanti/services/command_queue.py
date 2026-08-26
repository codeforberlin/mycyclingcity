# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    command_queue.py
# @note    DB-backed command queue for Luanti bridge (HTTP poll fallback).

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from luanti.models import LuantiPendingCommand


def enqueue_command(payload: dict, *, server_id: str = "") -> LuantiPendingCommand:
    return LuantiPendingCommand.objects.create(
        server_id=(server_id or "")[:64],
        payload=payload if isinstance(payload, dict) else {"raw": payload},
    )


def drain_commands(server_id: str, *, limit: int = 32) -> list[dict]:
    """Return and mark undelivered commands for this server (or broadcast)."""
    sid = (server_id or "").strip()
    limit = max(1, int(limit))
    with transaction.atomic():
        ids = list(
            LuantiPendingCommand.objects.filter(delivered_at__isnull=True)
            .filter(Q(server_id="") | Q(server_id=sid))
            .order_by("id")
            .values_list("id", flat=True)[:limit]
        )
        if not ids:
            return []
        rows = list(LuantiPendingCommand.objects.filter(pk__in=ids).order_by("id"))
        now = timezone.now()
        LuantiPendingCommand.objects.filter(pk__in=ids).update(delivered_at=now)
        return [row.payload for row in rows if isinstance(row.payload, dict)]


def purge_delivered(*, older_than_hours: int = 24) -> int:
    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    deleted, _ = LuantiPendingCommand.objects.filter(
        delivered_at__isnull=False,
        delivered_at__lt=cutoff,
    ).delete()
    return int(deleted)
