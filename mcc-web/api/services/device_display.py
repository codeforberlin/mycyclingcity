# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# OLED display lock: freeze round Velos on device after game round stop.

from __future__ import annotations

import logging
from typing import Iterable, Optional

from api.velos import build_session_velos_api_payload, format_velos_de
from iot.models import Device, DeviceConfiguration

logger = logging.getLogger(__name__)

BOOT_REASON_UNLOCK = frozenset({'deep_sleep', 'power_on'})
DISPLAY_MODE_LIVE = 'live'
DISPLAY_MODE_ROUND_FROZEN = 'round_frozen'


def _get_or_create_configuration(device: Device) -> DeviceConfiguration:
    config, _ = DeviceConfiguration.objects.get_or_create(device=device)
    return config


def unlock_device_display(device: Device, reason: str = '') -> bool:
    """Clear OLED round-frozen lock for a device."""
    config = _get_or_create_configuration(device)
    if not config.display_velos_locked:
        return False
    config.display_velos_locked = False
    config.frozen_display_velos = 0
    config.save(update_fields=['display_velos_locked', 'frozen_display_velos', 'updated_at'])
    logger.info(
        "[device_display] Unlocked display for device %s (reason=%s)",
        device.name,
        reason or 'unspecified',
    )
    return True


def lock_device_display(device: Device, frozen_velos: int) -> None:
    """Freeze OLED Velos for a device until unlock."""
    config = _get_or_create_configuration(device)
    config.display_velos_locked = True
    config.frozen_display_velos = max(0, int(frozen_velos))
    config.save(
        update_fields=['display_velos_locked', 'frozen_display_velos', 'updated_at']
    )
    logger.info(
        "[device_display] Locked display for device %s at %s Velos",
        device.name,
        config.frozen_display_velos,
    )


def unlock_devices_by_names(device_names: Iterable[str], reason: str = '') -> int:
    """Unlock display for all given device names. Returns count unlocked."""
    unlocked = 0
    for device_name in device_names:
        if not device_name:
            continue
        try:
            device = Device.objects.get(name__iexact=device_name)
        except Device.DoesNotExist:
            continue
        if unlock_device_display(device, reason=reason):
            unlocked += 1
    return unlocked


def lock_devices_for_round_stop(
    device_assignments: dict,
    stop_session_velos: dict,
) -> None:
    """
    Lock OLED display for all devices in round assignments.

    device_assignments maps device_name -> cyclist user_id.
    stop_session_velos maps user_id -> frozen session Velos.
    """
    for device_name, user_id in (device_assignments or {}).items():
        frozen_velos = int((stop_session_velos or {}).get(user_id, 0))
        try:
            device = Device.objects.get(name__iexact=device_name)
        except Device.DoesNotExist:
            logger.warning(
                "[device_display] Cannot lock unknown device %s",
                device_name,
            )
            continue
        lock_device_display(device, frozen_velos)


def handle_boot_reason(device: Device, boot_reason: Optional[str]) -> bool:
    """Unlock display after deep sleep or cold power-on boot."""
    if not boot_reason:
        return False
    normalized = str(boot_reason).strip().lower()
    if normalized not in BOOT_REASON_UNLOCK:
        return False
    return unlock_device_display(device, reason=normalized)


def get_active_session_for_device(device: Device):
    """Return active CyclistDeviceCurrentMileage for device, if any."""
    from api.models import CyclistDeviceCurrentMileage

    return (
        CyclistDeviceCurrentMileage.objects.filter(device=device)
        .select_related('device', 'cyclist')
        .first()
    )


def build_device_display_api_payload(device: Device, session=None) -> dict:
    """
    Build display_* and session_* fields for device API responses.

    OLED uses display_velos_display; session_velos remains live session data.
    """
    session_fields = {}
    session_velos = 0
    if session is not None:
        session_fields = build_session_velos_api_payload(session, session.device)
        session_velos = session_fields.get('session_velos', 0)

    config = _get_or_create_configuration(device)
    if config.display_velos_locked:
        display_mode = DISPLAY_MODE_ROUND_FROZEN
        display_velos = config.frozen_display_velos
    else:
        display_mode = DISPLAY_MODE_LIVE
        display_velos = session_velos

    payload = {
        'display_mode': display_mode,
        'display_velos': display_velos,
        'display_velos_display': format_velos_de(display_velos),
    }
    payload.update(session_fields)
    return payload
