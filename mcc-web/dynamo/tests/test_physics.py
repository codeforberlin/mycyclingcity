# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_physics.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Unit tests for virtual hub dynamo physics."""

from decimal import Decimal

import pytest

from dynamo.physics import (
    DEFAULT_POWER_CAP_W,
    compute_interval_energy,
    energy_wh_from_power,
    estimate_energy_from_distance,
    interpolate_power,
    parse_power_curve,
    resolve_interval_seconds,
    revolutions_from_distance,
    rpm_from_distance,
    speed_kmh_from_distance,
)


class TestInterpolatePower:
    def test_zero_speed(self):
        assert interpolate_power(0) == 0.0

    def test_curve_anchor_points(self):
        assert interpolate_power(5) == pytest.approx(0.5)
        assert interpolate_power(10) == pytest.approx(1.5)
        assert interpolate_power(15) == pytest.approx(3.0)
        assert interpolate_power(20) == pytest.approx(4.5)
        assert interpolate_power(25) == pytest.approx(6.0)

    def test_midpoint_interpolation(self):
        # Halfway between 10 km/h (1.5 W) and 15 km/h (3.0 W)
        assert interpolate_power(12.5) == pytest.approx(2.25)

    def test_power_cap(self):
        assert interpolate_power(40) == pytest.approx(DEFAULT_POWER_CAP_W)
        assert interpolate_power(40, power_cap_w=5.0) == pytest.approx(5.0)

    def test_negative_speed_treated_as_zero(self):
        assert interpolate_power(-3) == 0.0


class TestKinematics:
    def test_speed_from_distance(self):
        # 0.25 km in 60 s → 15 km/h
        assert speed_kmh_from_distance(0.25, 60) == pytest.approx(15.0)

    def test_speed_zero_interval(self):
        assert speed_kmh_from_distance(1.0, 0) == 0.0

    def test_revolutions(self):
        # 2075 mm circumference → 1 km = 1e6/2075 revolutions
        revs = revolutions_from_distance(1.0, 2075)
        assert revs == pytest.approx(1_000_000 / 2075)

    def test_revolutions_invalid_wheel_uses_default(self):
        revs = revolutions_from_distance(1.0, 0)
        assert revs == pytest.approx(1_000_000 / 2075)

    def test_rpm(self):
        # At 15 km/h with 2075 mm wheel over 60 s
        distance_km = 15.0 / 60.0  # 0.25 km
        rpm = rpm_from_distance(distance_km, 60, 2075)
        expected_revs = (0.25 * 1_000_000) / 2075
        assert rpm == pytest.approx(expected_revs)


class TestEnergy:
    def test_energy_from_power(self):
        # 3 W for 1 hour = 3 Wh; for 60 s = 3/60 Wh
        assert energy_wh_from_power(3.0, 3600) == pytest.approx(3.0)
        assert energy_wh_from_power(3.0, 60) == pytest.approx(0.05)

    def test_compute_interval_at_15_kmh(self):
        # 0.25 km / 60 s → 15 km/h → 3 W → 0.05 Wh
        result = compute_interval_energy(Decimal('0.25'), 60, 2075)
        assert result.speed_kmh == pytest.approx(15.0)
        assert result.power_w == pytest.approx(3.0)
        assert result.energy_wh == pytest.approx(0.05)
        assert result.rpm > 0

    def test_compute_interval_zero_distance(self):
        result = compute_interval_energy(0, 60, 2075)
        assert result.power_w == 0.0
        assert result.energy_wh == 0.0
        assert result.rpm == 0.0

    def test_estimate_from_distance(self):
        # 1 km at 12 km/h → duration 5 min; power at 12 km/h interpolated
        # 10→1.5, 15→3.0 → 12 km/h → 1.5 + 0.4*(1.5)=2.1 W
        # energy = 2.1 * (300/3600) = 0.175 Wh
        energy = estimate_energy_from_distance(1.0, assumed_speed_kmh=12.0)
        assert energy == pytest.approx(0.175)


class TestResolveInterval:
    def test_uses_configured_when_no_elapsed(self):
        assert resolve_interval_seconds(60, None) == 60.0

    def test_uses_elapsed_when_plausible(self):
        assert resolve_interval_seconds(60, 55) == 55.0

    def test_rejects_elapsed_outside_band(self):
        assert resolve_interval_seconds(60, 5) == 60.0
        assert resolve_interval_seconds(60, 400) == 60.0


class TestParsePowerCurve:
    def test_from_dicts(self):
        curve = parse_power_curve([
            {'speed_kmh': 10, 'power_w': 1.5},
            {'speed_kmh': 5, 'power_w': 0.5},
        ])
        assert curve[0] == (5.0, 0.5)
        assert curve[1] == (10.0, 1.5)

    def test_empty_falls_back_to_default(self):
        from dynamo.physics import DEFAULT_POWER_CURVE
        assert parse_power_curve([]) == DEFAULT_POWER_CURVE
