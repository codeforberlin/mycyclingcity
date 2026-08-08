# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.services.arena_motion.iot_update_sim import (
    clamp_send_interval,
    mps_from_pulse_meters,
    pulse_timed_out,
    simulate_iot_pulse_meters,
)


@pytest.mark.unit
class TestIotUpdateSim:
    def test_clamp_send_interval_defaults(self):
        assert clamp_send_interval(None) == 5.0
        assert clamp_send_interval(0) == 5.0
        assert clamp_send_interval(0.5) == 1.0
        # Device may report 60s — arena motion caps to keep HUD/Motion alive.
        assert clamp_send_interval(60) == 5.0
        assert clamp_send_interval(10) == 5.0
        assert clamp_send_interval(10, max_seconds=30) == 10.0
        assert clamp_send_interval(60, max_seconds=0) == 60.0

    def test_pulse_meters_scale_with_interval(self):
        # No jitter edge: monkey via fixed by checking average bounds
        meters = simulate_iot_pulse_meters(motion_mps=2.0, interval_s=5.0, jitter=0.0)
        assert meters == pytest.approx(10.0)
        assert mps_from_pulse_meters(meters, 5.0) == pytest.approx(2.0)

    def test_pulse_timeout(self):
        assert not pulse_timed_out(now=10.0, last_pulse_at=10.0, interval_s=5.0)
        assert not pulse_timed_out(now=17.0, last_pulse_at=10.0, interval_s=5.0)
        assert pulse_timed_out(now=18.0, last_pulse_at=10.0, interval_s=5.0)
