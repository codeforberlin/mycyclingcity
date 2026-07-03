# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import date, timedelta

import pytest
from django.utils import timezone

from api.helpers import get_leaderboard_footer_period_context
from api.models import YearEndSnapshot
from api.tests.conftest import GroupFactory


def _create_snapshot(group, snapshot_date):
    return YearEndSnapshot.objects.create(
        group=group,
        snapshot_date=snapshot_date,
        period_start_date=snapshot_date - timedelta(days=180),
        period_end_date=snapshot_date,
        period_type='calendar_year',
        is_undone=False,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestLeaderboardFooterPeriod:
    def test_all_time_when_no_snapshot(self):
        group = GroupFactory()
        ctx = get_leaderboard_footer_period_context([{'id': group.id}])
        assert ctx['footer_totals_period_mode'] == 'all_time'

    def test_single_period_after_snapshot(self):
        top = GroupFactory(name='Period Top', parent=None)
        leaf = GroupFactory(name='Period Leaf', parent=top)
        snapshot_date = timezone.make_aware(
            timezone.datetime(2025, 12, 31, 23, 59, 59)
        )
        _create_snapshot(top, snapshot_date)

        ctx = get_leaderboard_footer_period_context([{'id': leaf.id}])
        assert ctx['footer_totals_period_mode'] == 'single'
        assert ctx['footer_totals_period_since'] == date(2026, 1, 1)

    def test_multiple_periods_for_different_top_groups(self):
        top_a = GroupFactory(name='Period School A', parent=None)
        top_b = GroupFactory(name='Period School B', parent=None)
        leaf_a = GroupFactory(name='Period Class A', parent=top_a)
        leaf_b = GroupFactory(name='Period Class B', parent=top_b)

        _create_snapshot(top_a, timezone.make_aware(timezone.datetime(2025, 6, 30, 12, 0, 0)))
        _create_snapshot(top_b, timezone.make_aware(timezone.datetime(2025, 12, 31, 23, 59, 59)))

        ctx = get_leaderboard_footer_period_context([
            {'id': leaf_a.id},
            {'id': leaf_b.id},
        ])
        assert ctx['footer_totals_period_mode'] == 'multiple'
        assert ctx['footer_totals_period_dates'] == [date(2025, 7, 1), date(2026, 1, 1)]

    def test_empty_groups_returns_none_mode(self):
        ctx = get_leaderboard_footer_period_context([])
        assert ctx['footer_totals_period_mode'] == 'none'
