# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from decimal import Decimal
from django.utils import timezone

from api.helpers import (
    _calculate_cyclist_velos_from_metrics,
    _calculate_group_velos_from_metrics,
    _calculate_group_velos_periods,
    _cyclist_member_entry,
    build_group_hierarchy,
    get_group_velos_ledger,
    _get_cyclist_velos_balance,
)
from api.models import HourlyMetric, CyclistDeviceCurrentMileage
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosHelpers:
    def test_get_group_velos_ledger_uses_group_field(self):
        group = GroupFactory(velos_total=500, velos_spendable=120)
        cyclist = CyclistFactory(velos_balance=999)
        cyclist.groups.add(group)

        ledger = get_group_velos_ledger([group])
        assert ledger[group.id] == 500

    def test_cyclist_velos_from_metrics(self):
        group = GroupFactory()
        cyclist = CyclistFactory()
        cyclist.groups.add(group)
        device = DeviceFactory(group=group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        metric = HourlyMetric.objects.create(
            cyclist=cyclist,
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('1.50000'),
            group_at_time=group,
        )

        totals = _calculate_cyclist_velos_from_metrics([cyclist], use_cache=False)
        assert totals[cyclist.id] == metric.velos
        assert totals[cyclist.id] == 150
        assert _get_cyclist_velos_balance(cyclist) == 0

    def test_group_velos_from_metrics_by_group_at_time(self):
        parent = GroupFactory(name='Parent')
        leaf = GroupFactory(name='Leaf', parent=parent)
        cyclist = CyclistFactory()
        cyclist.groups.add(leaf)
        device = DeviceFactory(group=leaf)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        metric = HourlyMetric.objects.create(
            cyclist=cyclist,
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('2.00000'),
            group_at_time=leaf,
        )

        totals = _calculate_group_velos_from_metrics([parent, leaf], use_cache=False)
        assert totals[leaf.id] == metric.velos
        assert totals[leaf.id] == 200
        assert totals[parent.id] == 200

    def test_cyclist_ranking_uses_metrics_not_session_double_count(self):
        """Ranking total is HourlyMetric sum; session_velos is informational only."""
        group = GroupFactory()
        cyclist = CyclistFactory(velos_balance=65)
        cyclist.groups.add(group)
        device = DeviceFactory(group=group)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        hour_timestamp = timezone.now().replace(minute=0, second=0, microsecond=0)
        metric = HourlyMetric.objects.create(
            cyclist=cyclist,
            device=device,
            timestamp=hour_timestamp,
            distance_km=Decimal('0.65000'),
            group_at_time=group,
        )

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.65000'),
        )

        metric_totals = _calculate_cyclist_velos_from_metrics([cyclist], use_cache=False)
        entry = _cyclist_member_entry(cyclist, {}, metric_totals)
        assert metric_totals[cyclist.id] == metric.velos == 65
        assert entry['session_velos'] == 65
        assert entry['velos'] == 65  # metrics only — must not add session again

    def test_parent_group_ranking_sums_leaf_children(self):
        parent = GroupFactory(name='School', velos_total=0)
        leaf_a = GroupFactory(name='ClassA', parent=parent, velos_total=999)
        leaf_b = GroupFactory(name='ClassB', parent=parent, velos_total=888)

        device_a = DeviceFactory(group=leaf_a)
        device_b = DeviceFactory(group=leaf_b)
        for device in (device_a, device_b):
            config = device.configuration
            config.wheel_size = 2300.0
            config.paedagogischer_bonus = 0.0
            config.save()

        HourlyMetric.objects.create(
            device=device_a,
            timestamp=timezone.now(),
            distance_km=Decimal('1.20000'),
            group_at_time=leaf_a,
        )
        HourlyMetric.objects.create(
            device=device_b,
            timestamp=timezone.now(),
            distance_km=Decimal('0.80000'),
            group_at_time=leaf_b,
        )

        hierarchy = build_group_hierarchy(target_group=parent, show_cyclists=False)
        assert len(hierarchy) == 1
        assert hierarchy[0]['velos'] == 200
        subgroup_velos = sorted(sg['velos'] for sg in hierarchy[0]['subgroups'])
        assert subgroup_velos == [80, 120]

    def test_group_velos_periods_propagates_to_parent(self):
        parent = GroupFactory(name='SchoolPeriod')
        leaf = GroupFactory(name='ClassPeriod', parent=parent)
        device = DeviceFactory(group=leaf)
        config = device.configuration
        config.wheel_size = 2300.0
        config.paedagogischer_bonus = 0.0
        config.save()

        HourlyMetric.objects.create(
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('3.50000'),
            group_at_time=leaf,
        )

        periods = _calculate_group_velos_periods([parent, leaf], use_cache=False)
        assert periods[leaf.id]['total'] == 350
        assert periods[parent.id]['total'] == 350
