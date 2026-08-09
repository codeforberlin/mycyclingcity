# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    physics.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Virtual hub dynamo physics: speed → power → energy and RPM helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple, Union

Number = Union[int, float, Decimal]

# Pedagogical hub-dynamo curve (speed km/h → watts), capped at 6 W.
DEFAULT_POWER_CURVE: Tuple[Tuple[float, float], ...] = (
    (0.0, 0.0),
    (5.0, 0.5),
    (10.0, 1.5),
    (15.0, 3.0),
    (20.0, 4.5),
    (25.0, 6.0),
)
DEFAULT_POWER_CAP_W = 6.0
DEFAULT_WHEEL_SIZE_MM = 2075
DEFAULT_ASSUMED_SPEED_KMH = 12.0
DEFAULT_SEND_INTERVAL_S = 60.0

# Generic USB-charger classes (no brand names). Efficiency η(v) includes
# rectifier + regulation + typical matching-capacitor behaviour.
CHARGER_PROFILE_DIRECT = 'direct'
CHARGER_PROFILE_SIMPLE = 'simple'
CHARGER_PROFILE_STANDARD = 'standard'
CHARGER_PROFILE_OPTIMIZED = 'optimized'

CHARGER_PROFILE_KEYS = (
    CHARGER_PROFILE_DIRECT,
    CHARGER_PROFILE_SIMPLE,
    CHARGER_PROFILE_STANDARD,
    CHARGER_PROFILE_OPTIMIZED,
)

# speed_kmh → efficiency (0..1). "direct" is always 1.0 (raw dynamo).
DEFAULT_CHARGER_EFFICIENCY: dict[str, Tuple[Tuple[float, float], ...]] = {
    CHARGER_PROFILE_DIRECT: (
        (0.0, 1.0),
        (25.0, 1.0),
    ),
    # Little / no reactive matching: usable USB power only at higher speed.
    CHARGER_PROFILE_SIMPLE: (
        (0.0, 0.0),
        (5.0, 0.05),
        (8.0, 0.15),
        (12.0, 0.35),
        (15.0, 0.50),
        (20.0, 0.55),
        (25.0, 0.55),
    ),
    # Typical modern dynamo→USB converter with average matching.
    CHARGER_PROFILE_STANDARD: (
        (0.0, 0.0),
        (5.0, 0.25),
        (8.0, 0.45),
        (12.0, 0.65),
        (15.0, 0.72),
        (20.0, 0.75),
        (25.0, 0.75),
    ),
    # Well-matched network (incl. good capacitive matching) + efficient regulation.
    CHARGER_PROFILE_OPTIMIZED: (
        (0.0, 0.0),
        (5.0, 0.45),
        (8.0, 0.65),
        (12.0, 0.78),
        (15.0, 0.82),
        (20.0, 0.85),
        (25.0, 0.85),
    ),
}

CHARGER_PROFILE_META = {
    CHARGER_PROFILE_DIRECT: {
        'label': 'Dynamo (Default)',
        'description': 'Rohleistung des virtuellen Nabendynamos ohne Ladegerät-Stufe.',
    },
    CHARGER_PROFILE_SIMPLE: {
        'label': 'Einfach',
        'description': 'Wenig Anpassung – nutzbarer Strom erst bei höherer Geschwindigkeit.',
    },
    CHARGER_PROFILE_STANDARD: {
        'label': 'Standard',
        'description': 'Typische Dynamo→USB-Wandlung mit durchschnittlicher Anpassung.',
    },
    CHARGER_PROFILE_OPTIMIZED: {
        'label': 'Optimiert',
        'description': 'Gute Blindleistungsanpassung und effizientere Regelung.',
    },
}


@dataclass(frozen=True)
class IntervalEnergy:
    """Derived metrics for one distance reporting interval."""

    speed_kmh: float
    power_w: float
    energy_wh: float
    revolutions: float
    rpm: float
    interval_s: float
    wheel_size_mm: int


def _as_float(value: Number) -> float:
    return float(value)


def interpolate_power(
    speed_kmh: Number,
    curve: Sequence[Tuple[float, float]] = DEFAULT_POWER_CURVE,
    power_cap_w: float = DEFAULT_POWER_CAP_W,
) -> float:
    """
    Return dynamo electrical power (W) for a given speed via linear interpolation.

    Speeds at or below the first curve point yield 0 W. Speeds above the last
    point use the last power value, then apply ``power_cap_w``.
    """
    speed = max(0.0, _as_float(speed_kmh))
    if not curve:
        return 0.0

    points = sorted((float(v), float(p)) for v, p in curve)
    if speed <= points[0][0]:
        return min(max(0.0, points[0][1]), power_cap_w)

    for (v0, p0), (v1, p1) in zip(points, points[1:]):
        if speed <= v1:
            if v1 == v0:
                return min(max(0.0, p1), power_cap_w)
            ratio = (speed - v0) / (v1 - v0)
            power = p0 + ratio * (p1 - p0)
            return min(max(0.0, power), power_cap_w)

    return min(max(0.0, points[-1][1]), power_cap_w)


def speed_kmh_from_distance(distance_km: Number, interval_s: Number) -> float:
    """Average speed in km/h from distance and interval duration."""
    seconds = _as_float(interval_s)
    if seconds <= 0:
        return 0.0
    return (_as_float(distance_km) * 3600.0) / seconds


def revolutions_from_distance(
    distance_km: Number,
    wheel_size_mm: Number = DEFAULT_WHEEL_SIZE_MM,
) -> float:
    """Wheel revolutions for a distance given circumference in mm."""
    circumference_mm = _as_float(wheel_size_mm)
    if circumference_mm <= 0:
        circumference_mm = float(DEFAULT_WHEEL_SIZE_MM)
    distance_mm = _as_float(distance_km) * 1_000_000.0
    return distance_mm / circumference_mm


def rpm_from_distance(
    distance_km: Number,
    interval_s: Number,
    wheel_size_mm: Number = DEFAULT_WHEEL_SIZE_MM,
) -> float:
    """Average RPM for an interval."""
    seconds = _as_float(interval_s)
    if seconds <= 0:
        return 0.0
    return revolutions_from_distance(distance_km, wheel_size_mm) / (seconds / 60.0)


def energy_wh_from_power(power_w: Number, interval_s: Number) -> float:
    """Energy in watt-hours for constant power over an interval."""
    seconds = _as_float(interval_s)
    if seconds <= 0:
        return 0.0
    return _as_float(power_w) * (seconds / 3600.0)


def compute_interval_energy(
    distance_km: Number,
    interval_s: Number,
    wheel_size_mm: Number = DEFAULT_WHEEL_SIZE_MM,
    curve: Sequence[Tuple[float, float]] = DEFAULT_POWER_CURVE,
    power_cap_w: float = DEFAULT_POWER_CAP_W,
) -> IntervalEnergy:
    """
    Derive speed, power, energy and RPM for one reported distance interval.

    Zero or negative distance / interval yields zeros.
    """
    distance = max(0.0, _as_float(distance_km))
    seconds = max(0.0, _as_float(interval_s))
    wheel = int(wheel_size_mm) if _as_float(wheel_size_mm) > 0 else DEFAULT_WHEEL_SIZE_MM

    if distance <= 0 or seconds <= 0:
        return IntervalEnergy(
            speed_kmh=0.0,
            power_w=0.0,
            energy_wh=0.0,
            revolutions=0.0,
            rpm=0.0,
            interval_s=seconds,
            wheel_size_mm=wheel,
        )

    speed = speed_kmh_from_distance(distance, seconds)
    power = interpolate_power(speed, curve=curve, power_cap_w=power_cap_w)
    energy = energy_wh_from_power(power, seconds)
    revolutions = revolutions_from_distance(distance, wheel)
    rpm = revolutions / (seconds / 60.0)

    return IntervalEnergy(
        speed_kmh=speed,
        power_w=power,
        energy_wh=energy,
        revolutions=revolutions,
        rpm=rpm,
        interval_s=seconds,
        wheel_size_mm=wheel,
    )


def estimate_energy_from_distance(
    distance_km: Number,
    assumed_speed_kmh: Number = DEFAULT_ASSUMED_SPEED_KMH,
    curve: Sequence[Tuple[float, float]] = DEFAULT_POWER_CURVE,
    power_cap_w: float = DEFAULT_POWER_CAP_W,
) -> float:
    """
    Rough Wh estimate when only distance is known (e.g. legacy HourlyMetric rows).

    Derives an implied duration from assumed average speed, then applies the curve.
    """
    distance = max(0.0, _as_float(distance_km))
    speed = max(0.0, _as_float(assumed_speed_kmh))
    if distance <= 0 or speed <= 0:
        return 0.0
    interval_s = (distance / speed) * 3600.0
    power = interpolate_power(speed, curve=curve, power_cap_w=power_cap_w)
    return energy_wh_from_power(power, interval_s)


def resolve_interval_seconds(
    configured_interval_s: Optional[Number] = None,
    elapsed_s: Optional[Number] = None,
    default_s: float = DEFAULT_SEND_INTERVAL_S,
) -> float:
    """
    Choose interval length for energy calculation.

    Prefer measured elapsed time between updates when it is positive and
    plausible (0.5×–3× configured); otherwise use configured/default.
    """
    configured = _as_float(configured_interval_s) if configured_interval_s else default_s
    if configured <= 0:
        configured = default_s

    if elapsed_s is None:
        return configured

    elapsed = _as_float(elapsed_s)
    if elapsed <= 0:
        return configured

    lo = configured * 0.5
    hi = configured * 3.0
    if lo <= elapsed <= hi:
        return elapsed
    return configured


def parse_power_curve(raw: Iterable) -> Tuple[Tuple[float, float], ...]:
    """Normalize admin/JSON curve points to sorted (speed, power) tuples."""
    points = []
    for item in raw:
        if isinstance(item, dict):
            points.append((float(item['speed_kmh']), float(item['power_w'])))
        else:
            points.append((float(item[0]), float(item[1])))
    if not points:
        return DEFAULT_POWER_CURVE
    return tuple(sorted(points, key=lambda p: p[0]))


def parse_efficiency_curve(raw: Iterable) -> Tuple[Tuple[float, float], ...]:
    """Normalize (speed_kmh, efficiency) points; efficiency clamped to 0..1."""
    points = []
    for item in raw:
        if isinstance(item, dict):
            speed = float(item.get('speed_kmh', item.get('v', 0)))
            eta = float(item.get('efficiency', item.get('eta', 0)))
        else:
            speed = float(item[0])
            eta = float(item[1])
        points.append((speed, max(0.0, min(1.0, eta))))
    if not points:
        return DEFAULT_CHARGER_EFFICIENCY[CHARGER_PROFILE_DIRECT]
    return tuple(sorted(points, key=lambda p: p[0]))


def interpolate_efficiency(
    speed_kmh: Number,
    curve: Sequence[Tuple[float, float]],
) -> float:
    """Linear interpolation of charger efficiency η(v) in 0..1."""
    speed = max(0.0, _as_float(speed_kmh))
    if not curve:
        return 1.0
    points = sorted((float(v), max(0.0, min(1.0, float(e)))) for v, e in curve)
    if speed <= points[0][0]:
        return points[0][1]
    for (v0, e0), (v1, e1) in zip(points, points[1:]):
        if speed <= v1:
            if v1 == v0:
                return e1
            ratio = (speed - v0) / (v1 - v0)
            return max(0.0, min(1.0, e0 + ratio * (e1 - e0)))
    return points[-1][1]


def normalize_charger_profile(key: Optional[str]) -> str:
    """Return a valid charger profile key; unknown → direct."""
    if not key:
        return CHARGER_PROFILE_DIRECT
    value = str(key).strip().lower()
    aliases = {
        'default': CHARGER_PROFILE_DIRECT,
        'dynamo': CHARGER_PROFILE_DIRECT,
        'raw': CHARGER_PROFILE_DIRECT,
        'einfach': CHARGER_PROFILE_SIMPLE,
        'optimiert': CHARGER_PROFILE_OPTIMIZED,
    }
    value = aliases.get(value, value)
    if value in CHARGER_PROFILE_KEYS:
        return value
    return CHARGER_PROFILE_DIRECT


def get_charger_efficiency_curve(
    profile_key: str,
    overrides: Optional[dict] = None,
) -> Tuple[Tuple[float, float], ...]:
    """Resolve efficiency curve for a profile, optionally from admin JSON overrides."""
    key = normalize_charger_profile(profile_key)
    if overrides and isinstance(overrides, dict):
        raw = overrides.get(key)
        if raw:
            return parse_efficiency_curve(raw)
    return DEFAULT_CHARGER_EFFICIENCY[key]


def usable_power_w(
    dynamo_power_w: Number,
    speed_kmh: Number,
    profile_key: str = CHARGER_PROFILE_DIRECT,
    overrides: Optional[dict] = None,
) -> float:
    """USB-usable power after applying charger efficiency at the given speed."""
    power = max(0.0, _as_float(dynamo_power_w))
    if power <= 0:
        return 0.0
    key = normalize_charger_profile(profile_key)
    if key == CHARGER_PROFILE_DIRECT:
        return power
    eta = interpolate_efficiency(
        speed_kmh,
        get_charger_efficiency_curve(key, overrides),
    )
    return power * eta


def charger_profile_catalog(overrides: Optional[dict] = None) -> list[dict]:
    """Public catalog of charger profiles for the GUI (no brand names)."""
    catalog = []
    for key in CHARGER_PROFILE_KEYS:
        meta = CHARGER_PROFILE_META[key]
        curve = get_charger_efficiency_curve(key, overrides)
        catalog.append({
            'key': key,
            'label': meta['label'],
            'description': meta['description'],
            'efficiency_curve': [
                {'speed_kmh': v, 'efficiency': e} for v, e in curve
            ],
        })
    return catalog


def compare_chargers_at_speed(
    dynamo_power_w: Number,
    speed_kmh: Number,
    overrides: Optional[dict] = None,
) -> list[dict]:
    """Side-by-side usable power for all charger classes at one operating point."""
    rows = []
    for key in CHARGER_PROFILE_KEYS:
        usable = usable_power_w(dynamo_power_w, speed_kmh, key, overrides)
        eta = (
            1.0
            if key == CHARGER_PROFILE_DIRECT
            else interpolate_efficiency(
                speed_kmh,
                get_charger_efficiency_curve(key, overrides),
            )
        )
        rows.append({
            'key': key,
            'label': CHARGER_PROFILE_META[key]['label'],
            'efficiency': round(eta, 3),
            'usable_power_w': round(usable, 2),
        })
    return rows
