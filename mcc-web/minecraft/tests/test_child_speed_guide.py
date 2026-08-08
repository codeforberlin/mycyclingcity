# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.services.arena_motion.child_speed_guide import (
    WHEEL_SIZE_20_MM,
    WHEEL_SIZE_24_MM,
    child_speed_guide_for_wheel,
    classify_wheel_inches,
    default_sim_rate_mps,
    mps_to_kmh,
)


@pytest.mark.unit
class TestChildSpeedGuide:
    def test_classify_wheels(self):
        assert classify_wheel_inches(WHEEL_SIZE_20_MM) == 20
        assert classify_wheel_inches(1600) == 20
        assert classify_wheel_inches(WHEEL_SIZE_24_MM) == 24
        assert classify_wheel_inches(1916) == 24
        assert classify_wheel_inches(0) is None

    def test_defaults_by_wheel(self):
        assert default_sim_rate_mps(WHEEL_SIZE_20_MM) == pytest.approx(3.0)
        assert default_sim_rate_mps(WHEEL_SIZE_24_MM) == pytest.approx(4.0)
        assert default_sim_rate_mps(999, fallback_mps=2.5) == pytest.approx(2.5)

    def test_mps_to_kmh(self):
        assert mps_to_kmh(3.0) == pytest.approx(10.8)
        assert mps_to_kmh(4.0) == pytest.approx(14.4)

    def test_guide_presets(self):
        g20 = child_speed_guide_for_wheel(WHEEL_SIZE_20_MM)
        assert g20.wheel_label == '20″'
        assert g20.typical_kmh_range() == "8–15"
        assert len(g20.presets) == 3
        data = g20.as_dict()
        assert data["default_mps"] == 3.0
        assert data["presets"][1]["label"] == "normal"
