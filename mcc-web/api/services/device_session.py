# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# End active device sessions (CyclistDeviceCurrentMileage) without Velos redemption.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from django.db import transaction

from api.models import Cyclist, CyclistDeviceCurrentMileage
from api.services.hourly_metric_flush import persist_session_to_hourly_metric
from config.logger_utils import get_logger
from iot.models import Device

logger = get_logger(__name__)


@dataclass
class EndSessionsResult:
    ended_cyclist_ids: List[int] = field(default_factory=list)
    skipped_device_names: List[str] = field(default_factory=list)


@transaction.atomic
def end_cyclist_device_session(cyclist: Cyclist, *, reason: str = '') -> bool:
    """End active device session for a cyclist; does not modify velos_balance."""
    cyclist = Cyclist.objects.select_for_update().get(pk=cyclist.pk)
    try:
        session = cyclist.cyclistdevicecurrentmileage
    except CyclistDeviceCurrentMileage.DoesNotExist:
        return False

    persist_session_to_hourly_metric(session)
    session.delete()
    logger.info(
        "[device_session] Ended session for %s (reason=%s)",
        cyclist.user_id,
        reason or 'unspecified',
    )
    return True


@transaction.atomic
def end_device_session_for_device(device: Device, *, reason: str = '') -> Optional[Cyclist]:
    """End whichever cyclist is active on *device*. Returns ended cyclist or None."""
    session = (
        CyclistDeviceCurrentMileage.objects.select_for_update()
        .filter(device=device)
        .select_related('cyclist')
        .first()
    )
    if not session:
        return None

    cyclist = session.cyclist
    persist_session_to_hourly_metric(session)
    session.delete()
    logger.info(
        "[device_session] Ended session on device %s for %s (reason=%s)",
        device.name,
        cyclist.user_id,
        reason or 'unspecified',
    )
    return cyclist


def end_game_round_device_sessions(
    device_assignments: Dict[str, str],
    *,
    reason: str = 'game_round_start',
) -> EndSessionsResult:
    """
    End sessions for game-configured cyclists.

    Standalone cyclists (active on device but not in assignments) are left untouched.
    """
    result = EndSessionsResult()
    if not device_assignments:
        return result

    game_user_ids = set(device_assignments.values())
    ended_ids: set[int] = set()

    for device_name, configured_user_id in device_assignments.items():
        try:
            device = Device.objects.get(name=device_name)
        except Device.DoesNotExist:
            logger.warning("[device_session] Unknown device in assignments: %s", device_name)
            continue

        active = (
            CyclistDeviceCurrentMileage.objects.filter(device=device)
            .select_related('cyclist')
            .first()
        )
        if active and active.cyclist.user_id not in game_user_ids:
            result.skipped_device_names.append(device_name)
            logger.debug(
                "[device_session] Skipping device %s — standalone cyclist %s has priority",
                device_name,
                active.cyclist.user_id,
            )
            continue

        if active and active.cyclist.user_id == configured_user_id:
            if end_cyclist_device_session(active.cyclist, reason=reason):
                ended_ids.add(active.cyclist.id)
                result.ended_cyclist_ids.append(active.cyclist.id)

    configured_cyclists = Cyclist.objects.filter(user_id__in=game_user_ids)
    for cyclist in configured_cyclists:
        if cyclist.id in ended_ids:
            continue
        if end_cyclist_device_session(cyclist, reason=reason):
            result.ended_cyclist_ids.append(cyclist.id)

    return result
