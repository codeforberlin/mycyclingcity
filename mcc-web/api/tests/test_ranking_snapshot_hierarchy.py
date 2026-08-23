# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from api.helpers import (
    build_group_hierarchy_from_snapshot,
    format_ranking_snapshot_label,
    get_ranking_period_options,
    get_ranking_snapshot_for_view,
    snapshot_matches_group_filter,
)
from api.models import YearEndSnapshot, YearEndSnapshotDetail
from api.tests.conftest import GroupFactory, CyclistFactory


def _create_snapshot(top_group, *, period_type='school_year'):
    now = timezone.now()
    return YearEndSnapshot.objects.create(
        group=top_group,
        snapshot_date=now,
        period_start_date=now - timedelta(days=200),
        period_end_date=now,
        period_type=period_type,
        group_total_km=Decimal('100.00000'),
        group_total_velos=500,
        is_undone=False,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestRankingSnapshotHelpers:
    def test_format_school_year_label(self):
        top = GroupFactory(name='Archive School', parent=None)
        start = timezone.make_aware(timezone.datetime(2025, 9, 1, 0, 0, 0))
        end = timezone.make_aware(timezone.datetime(2026, 7, 31, 23, 59, 59))
        snapshot = YearEndSnapshot.objects.create(
            group=top,
            snapshot_date=end,
            period_start_date=start,
            period_end_date=end,
            period_type='school_year',
            is_undone=False,
        )
        label = format_ranking_snapshot_label(snapshot)
        assert label.startswith('Periode ')
        assert '01.09.2025' in label
        assert '31.07.2026' in label
        assert 'Schuljahr' not in label

    def test_format_short_summer_period_label(self):
        top = GroupFactory(name='FEZitty', parent=None)
        start = timezone.make_aware(timezone.datetime(2026, 6, 15, 0, 0, 0))
        end = timezone.make_aware(timezone.datetime(2026, 7, 27, 23, 59, 59))
        snapshot = YearEndSnapshot.objects.create(
            group=top,
            snapshot_date=end,
            period_start_date=start,
            period_end_date=end,
            period_type='school_year',
            is_undone=False,
        )
        label = format_ranking_snapshot_label(snapshot)
        assert label == 'Periode 15.06.2026 – 27.07.2026'

    def test_format_full_calendar_year_label(self):
        top = GroupFactory(name='Calendar Org', parent=None)
        start = timezone.make_aware(timezone.datetime(2025, 1, 1, 0, 0, 0))
        end = timezone.make_aware(timezone.datetime(2025, 12, 31, 23, 59, 59))
        snapshot = YearEndSnapshot.objects.create(
            group=top,
            snapshot_date=end,
            period_start_date=start,
            period_end_date=end,
            period_type='calendar_year',
            is_undone=False,
        )
        label = format_ranking_snapshot_label(snapshot)
        assert 'Kalenderjahr 2025' in label
        assert '01.01.2025' in label
        assert '31.12.2025' in label

    def test_get_ranking_period_options_filters_top_group(self):
        top_a = GroupFactory(name='School A', parent=None)
        top_b = GroupFactory(name='School B', parent=None)
        snap_a = _create_snapshot(top_a)
        _create_snapshot(top_b)

        options = get_ranking_period_options([top_a.id])
        assert len(options) == 1
        assert options[0]['id'] == snap_a.id

    def test_get_ranking_snapshot_ignores_undone(self):
        top = GroupFactory(parent=None)
        snapshot = _create_snapshot(top)
        snapshot.is_undone = True
        snapshot.save(update_fields=['is_undone'])
        assert get_ranking_snapshot_for_view(snapshot.id) is None

    def test_snapshot_matches_group_filter(self):
        top = GroupFactory(name='Top', parent=None)
        leaf = GroupFactory(name='Leaf', parent=top)
        other_top = GroupFactory(name='Other', parent=None)
        snapshot = _create_snapshot(top)

        assert snapshot_matches_group_filter(snapshot, [leaf]) is True
        assert snapshot_matches_group_filter(snapshot, [other_top]) is False


@pytest.mark.unit
@pytest.mark.django_db
class TestBuildGroupHierarchyFromSnapshot:
    def test_archive_hierarchy_uses_snapshot_totals(self):
        top = GroupFactory(name='Archive Top', parent=None)
        leaf = GroupFactory(name='Archive Class', parent=top)
        cyclist = CyclistFactory(user_id='RiderArchive')
        cyclist.groups.add(leaf)

        snapshot = _create_snapshot(top)
        YearEndSnapshotDetail.objects.create(
            snapshot=snapshot,
            group=leaf,
            distance_total=Decimal('42.50000'),
            velos_total=120,
        )
        YearEndSnapshotDetail.objects.create(
            snapshot=snapshot,
            cyclist=cyclist,
            distance_total=Decimal('5.00000'),
            velos_total=30,
        )

        hierarchy = build_group_hierarchy_from_snapshot(snapshot)
        assert len(hierarchy) == 1
        assert hierarchy[0]['km'] == pytest.approx(42.5)
        assert hierarchy[0]['velos'] == 120
        assert len(hierarchy[0]['subgroups']) == 1
        assert hierarchy[0]['subgroups'][0]['km'] == pytest.approx(42.5)
        assert hierarchy[0]['subgroups'][0]['members'][0]['velos'] == 30
        assert hierarchy[0]['subgroups'][0]['members'][0]['session_velos'] == 0
