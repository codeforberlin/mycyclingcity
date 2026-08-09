# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_services.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Tests for dynamo aggregation and live API."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from api.models import CyclistDeviceCurrentMileage, HourlyMetric
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory
from dynamo.models import DynamoBatteryTarget, DynamoDisplaySettings
from dynamo.services import (
    battery_progress,
    build_live_payload,
    daily_energy_wh,
    resolve_top_group_filter,
)


@pytest.mark.django_db
class TestGroupFilter:
    def test_resolve_top_group(self):
        top = GroupFactory(name='SchuleNord', parent=None)
        leaf = GroupFactory(name='Klasse1a', parent=top)
        group, ids = resolve_top_group_filter('schulenord')
        assert group == top
        assert top.id in ids
        assert leaf.id in ids

    def test_group_filter_catalog_includes_leaves(self):
        top = GroupFactory(name='SchuleSued', parent=None)
        leaf = GroupFactory(name='Klasse2b', parent=top)
        from dynamo.services import build_group_filter_catalog

        catalog = build_group_filter_catalog(leaf)
        assert catalog['current'] == 'Klasse2b'
        assert catalog['top'] == 'SchuleSued'
        assert catalog['is_leaf'] is True
        names = [o['name'] for o in catalog['options']]
        assert 'SchuleSued' in names
        top_opt = next(o for o in catalog['options'] if o['name'] == 'SchuleSued')
        assert any(l['name'] == 'Klasse2b' for l in top_opt['leaves'])

    def test_resolve_leaf_group(self):
        top = GroupFactory(name='SchuleOst', parent=None)
        leaf = GroupFactory(name='Klasse3c', parent=top)
        group, ids = resolve_top_group_filter('klasse3c')
        assert group == leaf
        assert ids == {leaf.id}
        assert top.id not in ids

    def test_unknown_group_empty_scope(self):
        group, ids = resolve_top_group_filter('DoesNotExist')
        assert group is None
        assert ids == set()


@pytest.mark.django_db
class TestEnergyAggregation:
    def test_daily_energy_from_metrics(self):
        top = GroupFactory(name='TopA')
        leaf = GroupFactory(name='LeafA', parent=top)
        device = DeviceFactory()
        cyclist = CyclistFactory()
        cyclist.groups.add(leaf)
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        HourlyMetric.objects.create(
            device=device,
            cyclist=cyclist,
            timestamp=now,
            distance_km=Decimal('1.00000'),
            group_at_time=leaf,
            energy_wh=Decimal('0.50000'),
        )
        _, ids = resolve_top_group_filter('TopA')
        assert daily_energy_wh(ids) == Decimal('0.50000')

    def test_battery_progress(self):
        DynamoBatteryTarget.objects.create(
            name='Handy',
            capacity_wh=Decimal('15.00'),
            icon_key='phone',
            sort_order=1,
            is_active=True,
        )
        progress = battery_progress(Decimal('7.50'))
        assert len(progress) == 1
        assert progress[0]['fill_percent'] == 50.0


@pytest.mark.django_db
class TestLivePayloadAndViews:
    def test_build_live_payload_with_session(self):
        top = GroupFactory(name='TopB')
        leaf = GroupFactory(name='LeafB', parent=top)
        device = DeviceFactory()
        cyclist = CyclistFactory(user_id='kid1')
        cyclist.groups.add(leaf)
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('0.50000'),
            session_energy_wh=Decimal('0.05000'),
            last_power_w=3.0,
            last_rpm=120.0,
            last_speed_kmh=15.0,
        )
        DynamoDisplaySettings.get_settings()
        payload = build_live_payload('TopB')
        assert payload['totals']['active_cyclists'] == 1
        assert payload['totals']['power_w'] == 3.0
        assert 'yearly_energy_wh' in payload['totals']
        assert payload['energy_periods']['session'] == pytest.approx(0.05)
        assert payload['show_cyclist_ride_stats'] is True
        assert payload['charger_profile'] == 'direct'
        assert payload['enable_charger_compare'] is True
        assert len(payload['charger_profiles']) == 4
        assert 'usable_power_w' in payload['totals']
        assert payload['cyclists'][0]['user_id'] == 'kid1'
        assert 'session_velos' in payload['cyclists'][0]
        assert 'session_km' in payload['cyclists'][0]
        assert payload['cyclists'][0]['session_km'] == pytest.approx(0.5)

    def test_dynamo_page_and_api(self, client):
        GroupFactory(name='FilterMe')
        DynamoDisplaySettings.get_settings()
        url = reverse('dynamo:dynamo_page')
        resp = client.get(url, {'group': 'FilterMe'})
        assert resp.status_code == 200
        assert b'Dynamo' in resp.content

        api = client.get(reverse('dynamo:dynamo_live_api'), {'group': 'FilterMe'})
        assert api.status_code == 200
        data = api.json()
        assert data['filter_group'] == 'FilterMe'
        assert 'history' in data
        assert 'batteries' in data

    def test_history_partial(self, client):
        DynamoDisplaySettings.get_settings()
        resp = client.get(reverse('dynamo:dynamo_history_partial'))
        assert resp.status_code == 200
