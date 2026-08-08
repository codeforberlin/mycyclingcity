# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    child_speed_guide.py
# @note    Typical child cycling speeds by wheel size (station / leisure).

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Common wheel circumferences (mm) — see mcc-web/test/mcc_api_test.py
WHEEL_SIZE_20_MM = 1596
WHEEL_SIZE_24_MM = 1916
WHEEL_SIZE_26_MM = 2075
WHEEL_MATCH_TOLERANCE_MM = 40


@dataclass(frozen=True)
class ChildSpeedGuide:
    """Orientation values for operators and children (not hard limits)."""

    wheel_label: str
    typical_kmh_min: float
    typical_kmh_max: float
    default_mps: float
    presets: tuple[tuple[str, float], ...]

    def typical_kmh_range(self) -> str:
        return f"{self.typical_kmh_min:.0f}–{self.typical_kmh_max:.0f}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "wheel_label": self.wheel_label,
            "typical_kmh_min": self.typical_kmh_min,
            "typical_kmh_max": self.typical_kmh_max,
            "typical_kmh_range": self.typical_kmh_range(),
            "default_mps": self.default_mps,
            "default_kmh": mps_to_kmh(self.default_mps),
            "presets": [
                {"label": label, "mps": mps, "kmh": mps_to_kmh(mps)}
                for label, mps in self.presets
            ],
        }


def mps_to_kmh(mps: float) -> float:
    return round(max(0.0, float(mps)) * 3.6, 1)


def classify_wheel_inches(wheel_mm: int) -> int | None:
    """Map circumference (mm) to nominal wheel size in inches."""
    mm = int(wheel_mm or 0)
    if mm <= 0:
        return None
    for inches, ref_mm in ((20, WHEEL_SIZE_20_MM), (24, WHEEL_SIZE_24_MM), (26, WHEEL_SIZE_26_MM)):
        if abs(mm - ref_mm) <= WHEEL_MATCH_TOLERANCE_MM:
            return inches
    return None


def child_speed_guide_for_wheel(
    wheel_mm: int,
    *,
    fallback_mps: float = 3.0,
) -> ChildSpeedGuide:
    """
    Typical sustained speeds on MCC stations (leisure / motivated children).

    Aligns with test simulator ranges in mcc_api_test.py (20″: 8–15 km/h, 24″: 10–18 km/h).
    """
    inches = classify_wheel_inches(wheel_mm)
    if inches == 20:
        return ChildSpeedGuide(
            wheel_label='20″',
            typical_kmh_min=8.0,
            typical_kmh_max=15.0,
            default_mps=3.0,
            presets=(
                ("gemütlich", 2.2),
                ("normal", 3.0),
                ("schnell", 4.2),
            ),
        )
    if inches == 24:
        return ChildSpeedGuide(
            wheel_label='24″',
            typical_kmh_min=10.0,
            typical_kmh_max=18.0,
            default_mps=4.0,
            presets=(
                ("gemütlich", 2.8),
                ("normal", 4.0),
                ("schnell", 5.0),
            ),
        )
    if inches == 26:
        return ChildSpeedGuide(
            wheel_label='26″',
            typical_kmh_min=12.0,
            typical_kmh_max=22.0,
            default_mps=4.5,
            presets=(
                ("gemütlich", 3.3),
                ("normal", 4.5),
                ("schnell", 6.0),
            ),
        )
    return ChildSpeedGuide(
        wheel_label="",
        typical_kmh_min=8.0,
        typical_kmh_max=18.0,
        default_mps=float(fallback_mps),
        presets=(
            ("gemütlich", 2.5),
            ("normal", float(fallback_mps)),
            ("schnell", 5.0),
        ),
    )


def default_sim_rate_mps(wheel_mm: int, *, fallback_mps: float = 3.0) -> float:
    """Default sim rate when assigning a lane (bike m/s, 1:1 arena motion)."""
    return child_speed_guide_for_wheel(wheel_mm, fallback_mps=fallback_mps).default_mps
