# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Group Velos spend/sync helpers for Minecraft integration.

from __future__ import annotations

from django.db import transaction

from api.models import Group
from config.logger_utils import get_logger
from minecraft.services.outbox import queue_team_velos_update
from minecraft.services.team_registration import get_active_registration_by_mc_username


logger = get_logger("minecraft")


@transaction.atomic
def spend_group_velos_from_minecraft(mc_username: str, amount: int) -> str:
    """
    Deduct spendable Velos for a leaf group identified by Minecraft username.

    Returns: ok | group_not_found | invalid_amount
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return "group_not_found"

    group = registration.group
    group = (
        Group.objects.select_for_update()
        .filter(pk=group.pk)
        .first()
    )

    try:
        spend_amount = int(amount)
    except (TypeError, ValueError):
        return "invalid_amount"
    if spend_amount <= 0:
        return "invalid_amount"

    new_spendable = max(0, int(group.velos_spendable or 0) - spend_amount)
    Group.objects.filter(pk=group.pk).update(velos_spendable=new_spendable)
    group.refresh_from_db(fields=['velos_total', 'velos_spendable', 'mc_username'])

    if registration.is_active:
        queue_team_velos_update(
            player=registration.mc_username,
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
