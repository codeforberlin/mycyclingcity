# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Apply Velos earnings on device updates (balance + group ledger + Minecraft outbox).

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

from api.models import Cyclist, Group
from api.velos import (
    calculate_incremental_session_velos,
    calculate_velos_for_device,
    get_cyclist_leaf_group,
)
from config.logger_utils import get_logger

logger = get_logger(__name__)


def _delta_velos_for_update(
    device,
    distance_delta: Union[Decimal, float, int],
    cumulative_mileage_after: Optional[Union[Decimal, float, int]],
) -> int:
    """Velos credited for a single update using one cumulative rounding boundary.

    When the session's cumulative mileage after this update is known, the delta
    is computed as the difference of the floored cumulative endpoints. Summed
    over a session this telescopes to ``floor(total cumulative)``, so the map
    avatar (sum of deltas) stays identical to the session/toast value and no
    per-update rounding is lost. Falls back to legacy per-delta rounding when
    no session context is available.
    """
    if cumulative_mileage_after is None:
        return calculate_velos_for_device(distance_delta, device)

    new_cumulative = Decimal(str(cumulative_mileage_after))
    previous_cumulative = new_cumulative - Decimal(str(distance_delta))
    if previous_cumulative < 0:
        previous_cumulative = Decimal('0')
    return calculate_incremental_session_velos(previous_cumulative, new_cumulative, device)


def apply_velos_earn(
    cyclist: Cyclist,
    device,
    distance_delta: Union[Decimal, float, int],
    cumulative_mileage_after: Optional[Union[Decimal, float, int]] = None,
) -> int:
    """
    Credit Velos to cyclist balance and leaf-group ledger when distance is earned.

    Pass ``cumulative_mileage_after`` (the session's cumulative mileage after
    this update) so the credited Velos use a single cumulative rounding
    strategy shared with the session/toast display.

    Returns the number of Velos credited (0 if skipped).
    """
    if distance_delta is None or distance_delta <= 0:
        return 0

    if getattr(device, 'is_operator_box', False):
        logger.debug("[apply_velos_earn] Skipping operator box device %s", device.name)
        return 0

    delta_velos = _delta_velos_for_update(device, distance_delta, cumulative_mileage_after)
    if delta_velos <= 0:
        return 0

    cyclist.velos_balance = (cyclist.velos_balance or 0) + delta_velos

    leaf_group = get_cyclist_leaf_group(cyclist)
    if leaf_group is None:
        logger.warning(
            "[apply_velos_earn] Cyclist %s has no valid single leaf group; Velos balance updated only",
            cyclist.id_tag,
        )
        return delta_velos

    leaf_group.add_velos_to_totals(delta_velos)
    leaf_group.add_velos_spendable(delta_velos)
    leaf_group.refresh_from_db(fields=['velos_total', 'velos_spendable', 'mc_username'])

    if leaf_group.mc_username:
        push_group_velos_to_minecraft(
            leaf_group,
            spendable_delta=delta_velos,
        )

    logger.debug(
        "[apply_velos_earn] +%s Velos for %s (leaf group %s)",
        delta_velos,
        cyclist.id_tag,
        leaf_group.name,
    )
    return delta_velos


def push_group_velos_to_minecraft(
    group: Group,
    spendable_delta: Optional[int] = None,
    spendable_action: str = "add",
) -> bool:
    """Queue Minecraft scoreboard sync for a leaf group's Velos ledger."""
    if not group.mc_username:
        return False

    try:
        from minecraft.services.outbox import queue_group_velos_update

        group.refresh_from_db(fields=['velos_total', 'velos_spendable'])
        queue_group_velos_update(
            player=group.mc_username,
            velos_total=int(group.velos_total),
            velos_spendable=int(group.velos_spendable),
            reason="db_update",
            spendable_action=spendable_action,
            spendable_delta=spendable_delta,
        )
        logger.info(
            "[push_group_velos_to_minecraft] Queued Velos for group %s (mc=%s)",
            group.name,
            group.mc_username,
        )
        return True
    except Exception as exc:
        logger.error("[push_group_velos_to_minecraft] Failed: %s", exc)
        return False
