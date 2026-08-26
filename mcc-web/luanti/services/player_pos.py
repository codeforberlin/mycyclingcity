# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    player_pos.py
# @note    Request player block position from mcc_bridge via WS/HTTP queue + DB reply.
#          Must use DB (not LocMem) so multi-worker Gunicorn can see the bridge reply.

from __future__ import annotations

import time
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

from luanti.services.region_ops import normalize_player

# Heartbeat is typically 5s; allow a full poll + HTTP round-trip.
_DEFAULT_TIMEOUT_SEC = 12.0
_POLL_INTERVAL_SEC = 0.1


def store_player_pos(request_id: str, x: int, y: int, z: int) -> None:
    from luanti.models import LuantiPlayerPosReply

    rid = (request_id or "").strip()[:64]
    if not rid:
        return
    LuantiPlayerPosReply.objects.update_or_create(
        request_id=rid,
        defaults={"x": int(x), "y": int(y), "z": int(z)},
    )


def _purge_old_replies() -> None:
    from luanti.models import LuantiPlayerPosReply

    cutoff = timezone.now() - timedelta(minutes=10)
    LuantiPlayerPosReply.objects.filter(created_at__lt=cutoff).delete()


def fetch_player_block_pos(
    player: str,
    *,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
) -> tuple[int, int, int]:
    """
    Ask the Luanti bridge for a player's position and wait for the HTTP reply.

    Raises ValueError if the player name is invalid, the bridge is offline,
    or no reply arrives within ``timeout_sec``.
    """
    from luanti.models import LuantiPlayerPosReply

    name = normalize_player(player)
    request_id = uuid.uuid4().hex
    from luanti.consumers import LuantiEventConsumer
    from luanti.services.bridge_connection import bridge_is_online

    if not bridge_is_online():
        raise ValueError(_("Luanti-Bridge ist nicht verbunden."))

    _purge_old_replies()
    LuantiPlayerPosReply.objects.filter(request_id=request_id).delete()

    sent = LuantiEventConsumer.push_to_all_sync(
        {
            "type": "GET_PLAYER_POS",
            "player": name,
            "request_id": request_id,
        }
    )
    if sent <= 0:
        raise ValueError(_("Kein Luanti-Bridge-Client erreichbar."))

    deadline = time.monotonic() + max(0.5, float(timeout_sec))
    while time.monotonic() < deadline:
        row = (
            LuantiPlayerPosReply.objects.filter(request_id=request_id)
            .only("x", "y", "z")
            .first()
        )
        if row is not None:
            x, y, z = int(row.x), int(row.y), int(row.z)
            LuantiPlayerPosReply.objects.filter(request_id=request_id).delete()
            return x, y, z
        time.sleep(_POLL_INTERVAL_SEC)

    raise ValueError(
        _("Spielerposition nicht lesbar (Spieler offline oder keine Antwort).")
    )
