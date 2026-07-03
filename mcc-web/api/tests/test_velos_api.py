# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from api.models import HourlyMetric
from api.tests.conftest import CyclistFactory, DeviceFactory, GroupFactory


def _device_with_standard_velos_config(group):
    device = DeviceFactory(group=group)
    config = device.configuration
    config.wheel_size = 2300.0
    config.paedagogischer_bonus = 0.0
    config.save()
    return device


@pytest.mark.unit
@pytest.mark.django_db
class TestVelosApiEndpoints:
    def test_get_cyclist_velos(self, api_key):
        group = GroupFactory()
        cyclist = CyclistFactory(user_id='velos-api-user', velos_balance=150)
        cyclist.groups.add(group)
        device = DeviceFactory(group=group)
        HourlyMetric.objects.create(
            cyclist=cyclist,
            device=device,
            timestamp=timezone.now().replace(minute=0, second=0, microsecond=0),
            distance_km=Decimal('2.0'),
            velos=200,
            group_at_time=group,
        )

        client = Client()
        response = client.get(
            reverse('get_cyclist_velos', args=['velos-api-user']),
            HTTP_X_API_KEY=api_key,
        )

        assert response.status_code == 200
        data = response.json()
        assert data['cyclist_id'] == cyclist.id
        assert data['velos_balance'] == 150
        assert data['velos_total'] >= 200
        assert 'session_velos' in data
        assert 'velos_daily' in data

    def test_get_cyclist_distance_includes_velos(self, api_key):
        cyclist = CyclistFactory(user_id='velos-dist-user', velos_balance=50)
        client = Client()
        response = client.get(
            reverse('get_cyclist_distance', args=['velos-dist-user']),
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['velos_balance'] == 50
        assert 'velos_total' in data
        assert 'session_velos' in data

    def test_get_group_velos(self, api_key):
        group = GroupFactory(name='Velos API Group', velos_total=1200, velos_spendable=400)
        client = Client()
        response = client.get(
            reverse('get_group_velos', args=[str(group.id)]),
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['velos_total'] == 1200
        assert data['velos_spendable'] == 400

    def test_redeem_cyclist_velos_api(self, api_key):
        group = GroupFactory()
        cyclist = CyclistFactory(user_id='redeem-api-user', velos_balance=80)
        cyclist.groups.add(group)

        client = Client()
        response = client.post(
            reverse('redeem_cyclist_velos'),
            data=json.dumps({'identifier': 'redeem-api-user', 'note': 'Wuhlis'}),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['velos_redeemed'] == 80

        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 0

    def test_get_leaderboard_cyclists_includes_velos(self, api_key):
        cyclist = CyclistFactory(user_id='lb-velos-user', velos_balance=10, is_visible=True)
        client = Client()
        response = client.get(
            reverse('get_leaderboard_cyclists'),
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['cyclists']
        entry = next(c for c in data['cyclists'] if c['user_id'] == 'lb-velos-user')
        assert 'velos_total' in entry
        assert 'velos_balance' in entry

    def test_update_data_returns_session_velos_fields(self, api_key, complete_test_scenario):
        from api.models import CyclistDeviceCurrentMileage
        from api.velos import calculate_session_velos, format_velos_de

        cyclist = complete_test_scenario['cyclist']
        device = complete_test_scenario['device']
        client = Client()
        response = client.post(
            reverse('update_data'),
            data=json.dumps({
                'id_tag': cyclist.id_tag,
                'device_id': device.name,
                'distance': '0.5',
            }),
            content_type='application/json',
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        session = CyclistDeviceCurrentMileage.objects.get(cyclist=cyclist)
        expected_velos = calculate_session_velos(session.cumulative_mileage, device)
        assert data['session_velos'] == expected_velos
        assert data['session_velos_display'] == format_velos_de(expected_velos)
        assert data['session_epoch'] == session.start_time.isoformat()
        assert data['session_km'] == str(session.cumulative_mileage)

    def test_get_active_cyclists_includes_session_velos(self, api_key):
        cyclist = CyclistFactory(
            user_id='active-velos-user',
            is_visible=True,
            last_active=timezone.now(),
        )
        client = Client()
        response = client.get(
            reverse('get_active_cyclists'),
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        entry = next(c for c in data['cyclists'] if c['user_id'] == 'active-velos-user')
        assert 'session_velos' in entry
        assert 'velos_total' in entry

    def test_get_group_rewards_includes_reached_velos(self, api_key):
        from api.models import GroupMilestoneAchievement
        from api.tests.conftest import MilestoneFactory, TravelTrackFactory

        group = GroupFactory()
        track = TravelTrackFactory()
        milestone = MilestoneFactory(track=track, distance_km=Decimal('10.0'), name='Test MS')
        achievement = GroupMilestoneAchievement.objects.create(
            group=group,
            milestone=milestone,
            track=track,
            reached_distance=Decimal('10.0'),
            reached_at=timezone.now(),
            reward_text='Belohnung',
        )

        client = Client()
        response = client.get(
            reverse('get_group_rewards'),
            {'group_id': group.id},
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        assert data['rewards'][0]['reached_velos'] == 1000

    def test_get_leaderboard_groups_velos_total_from_metrics(self, api_key):
        parent = GroupFactory(name='LB Metrics Parent', is_visible=True)
        group = GroupFactory(name='LB Metrics Group', parent=parent, velos_total=9999, is_visible=True)
        device = _device_with_standard_velos_config(group)
        metric = HourlyMetric.objects.create(
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('1.50000'),
            group_at_time=group,
        )

        client = Client()
        response = client.get(
            reverse('get_leaderboard_groups'),
            {'sort': 'total', 'limit': 50, 'parent_group_id': parent.id},
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        entry = next(g for g in response.json()['groups'] if g['group_id'] == group.id)
        assert entry['velos_total'] == metric.velos
        assert entry['velos_total'] == 150
        assert entry['velos_spendable'] == int(group.velos_spendable or 0)

    def test_list_groups_velos_total_from_metrics(self, api_key):
        group = GroupFactory(name='List Metrics Group', velos_total=8888, is_visible=True)
        device = _device_with_standard_velos_config(group)
        metric = HourlyMetric.objects.create(
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('2.50000'),
            group_at_time=group,
        )

        client = Client()
        response = client.get(
            reverse('list_groups'),
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        entry = next(g for g in response.json()['groups'] if g['group_id'] == group.id)
        assert entry['velos_total'] == metric.velos
        assert entry['velos_total'] == 250

    def test_get_statistics_top_groups_from_metrics(self, api_key):
        parent = GroupFactory(name='Stats Metrics Parent', is_visible=True)
        group = GroupFactory(name='Stats Metrics Group', parent=parent, velos_total=7777, is_visible=True)
        device = _device_with_standard_velos_config(group)
        metric = HourlyMetric.objects.create(
            device=device,
            timestamp=timezone.now(),
            distance_km=Decimal('3.00000'),
            group_at_time=group,
        )

        client = Client()
        response = client.get(
            reverse('get_statistics'),
            {'group_id': parent.id},
            HTTP_X_API_KEY=api_key,
        )
        assert response.status_code == 200
        data = response.json()
        entry = next(g for g in data['top_groups'] if g['group_id'] == group.id)
        assert entry['velos_total'] == metric.velos
        assert entry['velos_total'] == 300
