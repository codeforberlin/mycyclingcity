# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Central Velos calculation and formatting (fair performance unit).

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

from django.utils.translation import gettext_lazy as _

FKM_BASE_MM = 2300
PAEDAGOGICAL_BONUS_THRESHOLD_MM = 1600
PAEDAGOGICAL_BONUS = 0.3
VELOS_PER_KM = 100


def get_radumfang_mm(device) -> int:
    """Return wheel circumference in mm from device configuration."""
    if not hasattr(device, 'configuration'):
        return 2075
    try:
        config = device.configuration
    except Exception:
        return 2075
    return int(config.wheel_size)


def get_paedagogischer_bonus(device) -> float:
    """Return pedagogical bonus from device configuration."""
    if not hasattr(device, 'configuration'):
        return 0.0
    try:
        return float(device.configuration.paedagogischer_bonus)
    except Exception:
        return 0.0


def get_fkm_factor(radumfang_mm: int, paedagogischer_bonus: float = 0.0) -> float:
    """Fair km factor: (29\" base / wheel mm) + pedagogical bonus."""
    if radumfang_mm <= 0:
        raise ValueError("radumfang_mm must be positive")
    return (FKM_BASE_MM / radumfang_mm) + paedagogischer_bonus


def get_fkm_factor_for_device(device) -> float:
    """FKM factor for a device using its configuration."""
    return get_fkm_factor(get_radumfang_mm(device), get_paedagogischer_bonus(device))


def calculate_velos(
    km: Union[Decimal, float, int],
    fkm_factor: float,
) -> int:
    """Convert distance in km to integer Velos (100 base units per km at 29\")."""
    return int(float(km) * VELOS_PER_KM * fkm_factor)


def calculate_velos_for_device(km: Union[Decimal, float, int], device) -> int:
    """Convert km to Velos using the device's wheel size and bonus."""
    return calculate_velos(km, get_fkm_factor_for_device(device))


def calculate_session_velos(cumulative_mileage_km, device) -> int:
    """Velos for an active session distance."""
    if not cumulative_mileage_km:
        return 0
    return calculate_velos_for_device(cumulative_mileage_km, device)


def calculate_incremental_session_velos(
    previous_cumulative_km: Union[Decimal, float, int],
    new_cumulative_km: Union[Decimal, float, int],
    device,
) -> int:
    """Velos gained between two cumulative session distances.

    Rounding happens once on each cumulative endpoint, so a sum of consecutive
    increments telescopes to ``floor(total cumulative)`` without per-update
    rounding loss. This keeps the map avatar (sum of per-update deltas) exactly
    equal to the session/toast value (single floor of the cumulative distance).
    """
    return (
        calculate_session_velos(new_cumulative_km, device)
        - calculate_session_velos(previous_cumulative_km, device)
    )


def get_session_epoch(session) -> str:
    """Stable identifier for the active device session (ESP display sync)."""
    return session.start_time.isoformat()


def build_session_velos_api_payload(session, device) -> dict:
    """Build update_data response fields for server-authoritative session Velos."""
    session_velos = calculate_session_velos(session.cumulative_mileage, device)
    return {
        'session_velos': session_velos,
        'session_velos_display': format_velos_de(session_velos),
        'session_epoch': get_session_epoch(session),
        'session_km': str(session.cumulative_mileage),
    }


def track_reference_velos(track_length_km: Union[Decimal, float]) -> int:
    """Reference Velos for full track length at 29\" base (no bonus)."""
    return calculate_velos(track_length_km, FKM_BASE_MM / FKM_BASE_MM)


def format_velos_de(value: Optional[int]) -> str:
    """Format integer Velos with German thousands separator."""
    if value is None:
        return "0"
    return f"{int(value):,}".replace(",", ".")


def is_true_leaf_group(group) -> bool:
    """A leaf group has no child subgroups."""
    return group is not None and not group.children.exists()


def get_cyclist_leaf_group(cyclist) -> Optional[object]:
    """
    Return the single leaf group of a cyclist, or None if invalid assignment.
    """
    groups = list(cyclist.groups.all())
    if len(groups) != 1:
        return None
    group = groups[0]
    if not is_true_leaf_group(group):
        return None
    return group
