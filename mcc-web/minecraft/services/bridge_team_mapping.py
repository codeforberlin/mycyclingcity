# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.conf import settings

from config.logger_utils import get_logger
from minecraft.consumers import MinecraftEventConsumer
from minecraft.services.bridge_connection import get_connected_server_ids
from minecraft.services.luckperms_sync import luckperms_group_name
from minecraft.services.team_registration import active_registrations


logger = get_logger("minecraft")


def _target_server_ids(server_id: str | None = None) -> list[str]:
    if server_id:
        return [server_id]
    connected = get_connected_server_ids()
    if connected:
        return connected
    return list(settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS or [])


def push_team_mapping_to_bridge(mc_username: str, *, server_id: str | None = None) -> int:
    """Notify connected MCC-Bridge plugins about lp_group -> mc_username mapping."""
    if not settings.MCC_MINECRAFT_WS_ENABLED:
        return 0

    lp_group = luckperms_group_name(mc_username)
    sent = 0
    for target_id in _target_server_ids(server_id):
        consumer = MinecraftEventConsumer.connections.get(target_id)
        if consumer is None:
            continue
        async_to_sync(consumer.send_json)(
            {
                "type": "PUSH_TEAM_MAPPING",
                "server_id": target_id,
                "lp_group": lp_group,
                "mc_username": mc_username,
            }
        )
        sent += 1
        logger.info(
            "[minecraft_bridge] pushed team mapping server_id=%s lp_group=%s mc=%s",
            target_id,
            lp_group,
            mc_username,
        )
    return sent


def remove_team_mapping_from_bridge(mc_username: str, *, server_id: str | None = None) -> int:
    if not settings.MCC_MINECRAFT_WS_ENABLED:
        return 0

    lp_group = luckperms_group_name(mc_username)
    sent = 0
    for target_id in _target_server_ids(server_id):
        consumer = MinecraftEventConsumer.connections.get(target_id)
        if consumer is None:
            continue
        async_to_sync(consumer.send_json)(
            {
                "type": "REMOVE_TEAM_MAPPING",
                "server_id": target_id,
                "lp_group": lp_group,
                "mc_username": mc_username,
            }
        )
        sent += 1
    return sent


def sync_all_team_mappings_to_bridge(*, server_id: str | None = None) -> int:
    """Push all active team registrations to connected bridge(s)."""
    count = 0
    for registration in active_registrations():
        count += push_team_mapping_to_bridge(registration.mc_username, server_id=server_id)
    return count
