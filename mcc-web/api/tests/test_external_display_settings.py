# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from decimal import Decimal

from api.helpers import (
    get_external_display_settings_context,
    sum_display_totals_from_groups_data,
    _group_km_for_ranking,
    build_hierarchy_from_parent_groups,
)
from api.models import ExternalDisplaySettings, Group
from api.tests.conftest import GroupFactory, CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestExternalDisplaySettings:
    def test_singleton_get_settings(self):
        settings_a = ExternalDisplaySettings.get_settings()
        settings_b = ExternalDisplaySettings.get_settings()
        assert settings_a.pk == settings_b.pk == 1

    def test_get_external_display_settings_context(self):
        settings_obj = ExternalDisplaySettings.get_settings()
        settings_obj.show_km_in_leaderboard_footer = False
        settings_obj.show_km_in_ranking_headers = True
        settings_obj.show_km_in_eventboard = False
        settings_obj.km_display_decimals = 2
        settings_obj.save()

        ctx = get_external_display_settings_context()
        assert ctx['show_km_in_leaderboard_footer'] is False
        assert ctx['show_km_in_ranking_headers'] is True
        assert ctx['show_km_in_eventboard'] is False
        assert ctx['km_display_decimals'] == 2

    def test_leaderboard_footer_km_default_off(self):
        settings_obj = ExternalDisplaySettings.get_settings()
        assert settings_obj.show_km_in_leaderboard_footer is False

    def test_eventboard_km_default_on(self):
        settings_obj = ExternalDisplaySettings.get_settings()
        assert settings_obj.show_km_in_eventboard is True


@pytest.mark.unit
class TestSumDisplayTotals:
    def test_sum_display_totals_from_groups_data(self):
        groups_data = [
            {'velos_total': 100, 'distance_total': 1.5, 'ranking_km': 10.0},
            {'velos_total': 50, 'distance_total': 0.25, 'ranking_km': 2.5},
        ]
        totals = sum_display_totals_from_groups_data(groups_data)
        assert totals['total_velos'] == 150
        assert totals['total_km'] == 12.5

    def test_sum_display_totals_km_fallback_to_distance_total(self):
        groups_data = [
            {'velos_total': 10, 'distance_total': 3.0},
        ]
        totals = sum_display_totals_from_groups_data(groups_data)
        assert totals['total_km'] == 3.0


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildEventsData:
    def test_build_events_data_includes_total_km(self):
        from decimal import Decimal

        from api.helpers import build_events_data
        from api.tests.conftest import EventFactory, GroupEventStatusFactory, GroupFactory

        top = GroupFactory(parent=None)
        event = EventFactory(top_group=top, is_active=True, is_visible_on_map=True)
        group = GroupFactory(parent=top)
        GroupEventStatusFactory(
            event=event,
            group=group,
            current_velos=100,
            current_event_km=Decimal('12.50000'),
        )

        events = build_events_data()
        match = [entry for entry in events if entry['id'] == event.id]
        assert len(match) == 1
        assert match[0]['total_km'] == pytest.approx(12.5)
        assert match[0]['groups'][0]['km'] == pytest.approx(12.5)


@pytest.mark.unit
@pytest.mark.django_db
class TestGroupKmForRanking:
    def test_parent_sums_children_km(self):
        parent = GroupFactory(name='Parent', distance_total=Decimal('10.00000'))
        child_entries = [{'km': 1.2, 'velos': 10}, {'km': 0.8, 'velos': 5}]
        total = _group_km_for_ranking(parent, child_entries=child_entries)
        assert total == pytest.approx(2.0)

    def test_leaf_uses_group_distance_total(self):
        group = GroupFactory(name='Leaf', distance_total=Decimal('12.50000'))
        total = _group_km_for_ranking(group)
        assert total == pytest.approx(12.5)


@pytest.mark.unit
@pytest.mark.django_db
class TestRankingHierarchyKmSource:
    def test_hierarchy_km_from_group_distance_total(self):
        top = GroupFactory(name='Top School', distance_total=Decimal('100.00000'))
        leaf = GroupFactory(name='Class 1a', parent=top, distance_total=Decimal('42.50000'))
        cyclist = CyclistFactory(user_id='Rider1', distance_total=Decimal('5.00000'))
        cyclist.groups.add(leaf)

        hierarchy = build_hierarchy_from_parent_groups(Group.objects.filter(id=top.id))
        assert len(hierarchy) == 1
        assert hierarchy[0]['km'] == pytest.approx(42.5)
        assert hierarchy[0]['subgroups'][0]['km'] == pytest.approx(42.5)
