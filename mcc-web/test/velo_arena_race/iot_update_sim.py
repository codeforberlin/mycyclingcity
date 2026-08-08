# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    iot_update_sim.py
# @note    Standalone copy of arena_motion pulse timing (no Django import).

from __future__ import annotations

import random

DEFAULT_SIM_UPDATE_INTERVAL_SECONDS = 5.0
PULSE_HOLD_TIMEOUT_FACTOR = 1.5


def clamp_send_interval(
    seconds: float | int | None,
    *,
    default: float = DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
) -> float:
    try:
        value = float(seconds) if seconds is not None else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if value <= 0:
        value = float(default)
    return max(1.0, value)


def simulate_iot_pulse_meters(
    *,
    motion_mps: float,
    interval_s: float,
    jitter: float = 0.15,
) -> float:
    base = max(0.0, float(motion_mps)) * max(1e-6, float(interval_s))
    if base <= 0:
        return 0.0
    noise = 1.0 + random.uniform(-abs(jitter), abs(jitter))
    return max(0.0, base * noise)


def mps_from_pulse_meters(meters: float, interval_s: float) -> float:
    return max(0.0, float(meters)) / max(1e-6, float(interval_s))


def pulse_timed_out(
    *,
    now: float,
    last_pulse_at: float,
    interval_s: float,
    factor: float = PULSE_HOLD_TIMEOUT_FACTOR,
) -> bool:
    if last_pulse_at <= 0:
        return False
    return now > (last_pulse_at + max(1e-6, interval_s) * max(1.0, factor))
