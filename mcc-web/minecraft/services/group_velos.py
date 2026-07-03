# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Group Velos spend/sync helpers for Minecraft integration.

from __future__ import annotations

from django.db import transaction

from api.models import Group
from config.logger_utils import get_logger
from minecraft.services.outbox import queue_group_velos_update


logger = get_logger("minecraft")


@transaction.atomic
def spend_group_velos_from_minecraft(mc_username: str, amount: int) -> str:
    """
    Deduct spendable Velos for a leaf group identified by Minecraft username.

    Returns: ok | group_not_found | invalid_amount
    """
    group = (
        Group.objects.select_for_update()
        .filter(mc_username__iexact=mc_username)
        .first()
    )
    if not group:
        return "group_not_found"

    try:
        spend_amount = int(amount)
    except (TypeError, ValueError):
        return "invalid_amount"
    if spend_amount <= 0:
        return "invalid_amount"

    new_spendable = max(0, int(group.velos_spendable or 0) - spend_amount)
    Group.objects.filter(pk=group.pk).update(velos_spendable=new_spendable)
    group.refresh_from_db(fields=['velos_total', 'velos_spendable', 'mc_username'])

    if group.mc_username:
        queue_group_velos_update(
            player=group.mc_username,
            velos_total=int(group.velos_total or 0),
            velos_spendable=int(group.velos_spendable or 0),
            reason="minecraft_spend",
            spendable_action="set",
        )

    logger.info(
        "[minecraft_group_velos] spent %s Velos for mc=%s (group=%s), new_spendable=%s",
        spend_amount,
        mc_username,
        group.name,
        group.velos_spendable,
    )
    return "ok"
