# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_charger_profiles.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Tests for generic charger efficiency profiles."""

import pytest

from dynamo.physics import (
    CHARGER_PROFILE_DIRECT,
    CHARGER_PROFILE_OPTIMIZED,
    CHARGER_PROFILE_SIMPLE,
    CHARGER_PROFILE_STANDARD,
    compare_chargers_at_speed,
    interpolate_efficiency,
    normalize_charger_profile,
    usable_power_w,
)


class TestChargerProfiles:
    def test_normalize_aliases(self):
        assert normalize_charger_profile('default') == CHARGER_PROFILE_DIRECT
        assert normalize_charger_profile('einfach') == CHARGER_PROFILE_SIMPLE
        assert normalize_charger_profile('optimiert') == CHARGER_PROFILE_OPTIMIZED
        assert normalize_charger_profile('unknown') == CHARGER_PROFILE_DIRECT

    def test_direct_equals_dynamo(self):
        assert usable_power_w(3.0, 15.0, CHARGER_PROFILE_DIRECT) == pytest.approx(3.0)

    def test_simple_worse_than_optimized_at_low_speed(self):
        simple = usable_power_w(1.5, 8.0, CHARGER_PROFILE_SIMPLE)
        optimized = usable_power_w(1.5, 8.0, CHARGER_PROFILE_OPTIMIZED)
        assert optimized > simple

    def test_standard_between_simple_and_optimized(self):
        p = 3.0
        v = 12.0
        simple = usable_power_w(p, v, CHARGER_PROFILE_SIMPLE)
        standard = usable_power_w(p, v, CHARGER_PROFILE_STANDARD)
        optimized = usable_power_w(p, v, CHARGER_PROFILE_OPTIMIZED)
        assert simple < standard < optimized

    def test_efficiency_bounds(self):
        eta = interpolate_efficiency(15.0, ((0, 0), (20, 0.8)))
        assert 0.0 <= eta <= 1.0

    def test_compare_rows(self):
        rows = compare_chargers_at_speed(3.0, 15.0)
        keys = [r['key'] for r in rows]
        assert keys == [
            CHARGER_PROFILE_DIRECT,
            CHARGER_PROFILE_SIMPLE,
            CHARGER_PROFILE_STANDARD,
            CHARGER_PROFILE_OPTIMIZED,
        ]
        assert rows[0]['usable_power_w'] == pytest.approx(3.0)
