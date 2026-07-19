# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from minecraft.models import MinecraftBridgeConnection

STALE_AFTER = timedelta(minutes=5)


def mark_bridge_connected(server_id: str) -> None:
    now = timezone.now()
    connection, created = MinecraftBridgeConnection.objects.get_or_create(
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
    MinecraftBridgeConnection.objects.filter(pk=server_id).update(**updates)


def mark_bridge_disconnected(server_id: str) -> None:
    MinecraftBridgeConnection.objects.filter(pk=server_id).update(
        is_connected=False,
        last_seen_at=timezone.now(),
    )


def touch_bridge_connection(server_id: str) -> None:
    mark_bridge_connected(server_id)


def get_connected_server_ids() -> list[str]:
    cutoff = timezone.now() - STALE_AFTER
    return list(
        MinecraftBridgeConnection.objects.filter(
            is_connected=True,
            last_seen_at__gte=cutoff,
        )
        .order_by("server_id")
        .values_list("server_id", flat=True)
    )


def get_bridge_connection(server_id: str) -> MinecraftBridgeConnection | None:
    try:
        return MinecraftBridgeConnection.objects.get(pk=server_id)
    except MinecraftBridgeConnection.DoesNotExist:
        return None
