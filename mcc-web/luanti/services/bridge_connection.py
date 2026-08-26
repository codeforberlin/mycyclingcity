# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from luanti.models import LuantiBridgeConnection

STALE_AFTER = timedelta(minutes=5)


def mark_bridge_connected(server_id: str) -> None:
    now = timezone.now()
    connection, created = LuantiBridgeConnection.objects.get_or_create(
        server_id=server_id,
        defaults={
            "is_connected": True,
            "connected_at": now,
            "last_seen_at": now,
        },
    )
    if created:
        return
    updates = {"is_connected": True, "last_seen_at": now}
    if not connection.is_connected or connection.connected_at is None:
        updates["connected_at"] = now
    LuantiBridgeConnection.objects.filter(pk=server_id).update(**updates)


def mark_bridge_disconnected(server_id: str) -> None:
    LuantiBridgeConnection.objects.filter(pk=server_id).update(
        is_connected=False,
        last_seen_at=timezone.now(),
    )


def touch_bridge_connection(server_id: str) -> None:
    mark_bridge_connected(server_id)


def get_connected_server_ids() -> list[str]:
    cutoff = timezone.now() - STALE_AFTER
    return list(
        LuantiBridgeConnection.objects.filter(
            is_connected=True,
            last_seen_at__gte=cutoff,
        )
        .order_by("server_id")
        .values_list("server_id", flat=True)
    )


def bridge_is_online(server_id: str | None = None) -> bool:
    ids = get_connected_server_ids()
    if server_id:
        return server_id in ids
    return bool(ids)
