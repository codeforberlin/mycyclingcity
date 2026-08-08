# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    iot_update_sim.py
# @note    Simulate sparse IoT update-data intervals; Motion holds last rate between pulses.

from __future__ import annotations

import random

# Fallback when no Device.send_interval is available (matches common arena testInterval).
DEFAULT_SIM_UPDATE_INTERVAL_SECONDS = 5.0
# Arena Motion must pulse often enough for live HUD / held Motion. Real IoT stations
# may report 60s; that freezes the sidebar for nearly a minute between updates.
DEFAULT_MAX_ARENA_PULSE_INTERVAL_SECONDS = 5.0
# After this multiple of the send interval without a pulse, held speed drops to 0.
PULSE_HOLD_TIMEOUT_FACTOR = 1.5


def max_arena_pulse_interval_seconds() -> float:
    from django.conf import settings

    raw = getattr(
        settings,
        "MCC_MINECRAFT_ARENA_MAX_PULSE_INTERVAL_S",
        DEFAULT_MAX_ARENA_PULSE_INTERVAL_SECONDS,
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ARENA_PULSE_INTERVAL_SECONDS
    return max(1.0, value)


def clamp_send_interval(
    seconds: float | int | None,
    *,
    default: float = DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
    max_seconds: float | None = None,
) -> float:
    """Normalize a station send interval to >= 1 second (optionally capped)."""
    try:
        value = float(seconds) if seconds is not None else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if value <= 0:
        value = float(default)
    value = max(1.0, value)
    cap = max_arena_pulse_interval_seconds() if max_seconds is None else float(max_seconds)
    if cap > 0:
        value = min(value, max(1.0, cap))
    return value


def simulate_iot_pulse_meters(
    *,
    motion_mps: float,
    interval_s: float,
    jitter: float = 0.15,
) -> float:
    """
    Meters ridden during one station send window (like ESP32 before update-data).

    Real devices accumulate distance for send_interval_seconds, then POST once.
    """
    base = max(0.0, float(motion_mps)) * max(1e-6, float(interval_s))
    if base <= 0:
        return 0.0
    noise = 1.0 + random.uniform(-abs(jitter), abs(jitter))
    return max(0.0, base * noise)


def mps_from_pulse_meters(meters: float, interval_s: float) -> float:
    """Average m/s implied by one update-data distance packet."""
    return max(0.0, float(meters)) / max(1e-6, float(interval_s))


def pulse_timed_out(
    *,
    now: float,
    last_pulse_at: float,
    interval_s: float,
    factor: float = PULSE_HOLD_TIMEOUT_FACTOR,
) -> bool:
    """True if Motion should coast to stop after missing an IoT update."""
    if last_pulse_at <= 0:
        return False
    return now > (last_pulse_at + max(1e-6, interval_s) * max(1.0, factor))
