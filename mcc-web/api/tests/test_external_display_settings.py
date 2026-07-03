# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.helpers import (
    get_external_display_settings_context,
    sum_display_totals_from_groups_data,
    _group_km_for_ranking,
)
from api.models import ExternalDisplaySettings, Group
from api.tests.conftest import GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestExternalDisplaySettings:
    def test_singleton_get_settings(self):
        settings_a = ExternalDisplaySettings.get_settings()
        settings_b = ExternalDisplaySettings.get_settings()
        assert settings_a.pk == settings_b.pk == 1

    def test_get_external_display_settings_context(self):
        settings_obj = ExternalDisplaySettings.get_settings()
        settings_obj.show_km_in_leaderboard_footer = True
        settings_obj.show_km_in_ranking_headers = False
        settings_obj.km_display_decimals = 2
        settings_obj.save()

        ctx = get_external_display_settings_context()
        assert ctx['show_km_in_leaderboard_footer'] is True
        assert ctx['show_km_in_ranking_headers'] is False
        assert ctx['km_display_decimals'] == 2


@pytest.mark.unit
class TestSumDisplayTotals:
    def test_sum_display_totals_from_groups_data(self):
        groups_data = [
            {'velos_total': 100, 'distance_total': 1.5},
            {'velos_total': 50, 'distance_total': 0.25},
        ]
        totals = sum_display_totals_from_groups_data(groups_data)
        assert totals['total_velos'] == 150
        assert totals['total_km'] == 1.75


@pytest.mark.unit
@pytest.mark.django_db
class TestGroupKmForRanking:
    def test_parent_sums_children_km(self):
        parent = GroupFactory(name='Parent')
        child_entries = [{'km': 1.2, 'velos': 10}, {'km': 0.8, 'velos': 5}]
        total = _group_km_for_ranking(parent, [], child_entries=child_entries)
        assert total == pytest.approx(2.0)

    def test_leaf_uses_metric_km(self):
        group = GroupFactory(name='Leaf')
        total = _group_km_for_ranking(group, [{'km': 0.5, 'velos': 3}], group_metric_km=2.0)
        assert total == pytest.approx(2.0)
