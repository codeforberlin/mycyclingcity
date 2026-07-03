# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from api.tests.conftest import (
    CyclistFactory,
    DeviceFactory,
    GroupFactory,
    HourlyMetricFactory,
)

User = get_user_model()


@pytest.mark.django_db
class TestAnalyticsChartsByGroup:
    def test_daily_by_group_top_level(self, client):
        admin = User.objects.create_superuser(
            username='chart_admin',
            email='chart@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_a = GroupFactory(name='Chart School A', parent=None)
        top_b = GroupFactory(name='Chart School B', parent=None)
        leaf_a = GroupFactory(name='Chart Class A1', parent=top_a)
        leaf_b = GroupFactory(name='Chart Class B1', parent=top_b)
        device_a = DeviceFactory(group=leaf_a)
        device_b = DeviceFactory(group=leaf_b)
        cyclist = CyclistFactory()

        now = timezone.now()
        day_one = (now - timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        day_two = (now - timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)

        HourlyMetricFactory(
            device=device_a,
            cyclist=cyclist,
            group_at_time=leaf_a,
            timestamp=day_one,
            distance_km=Decimal('2.00000'),
        )
        HourlyMetricFactory(
            device=device_b,
            cyclist=cyclist,
            group_at_time=leaf_b,
            timestamp=day_one,
            distance_km=Decimal('1.00000'),
        )
        HourlyMetricFactory(
            device=device_a,
            cyclist=cyclist,
            group_at_time=leaf_a,
            timestamp=day_two,
            distance_km=Decimal('4.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        url = (
            f"{reverse('admin:api_analytics_data_api')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&report_type=daily_by_group&group_type=top_groups"
            f"&metric_mode=km"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
        )

        response = client.get(url)
        assert response.status_code == 200
        payload = response.json()['daily_by_group']
        assert len(payload['labels']) >= 2
        assert len(payload['total']) == len(payload['labels'])

        top_totals = dict(zip(payload['labels'], payload['total']))
        first_label = sorted(top_totals.keys())[0]
        assert top_totals[first_label] == pytest.approx(3.0, abs=0.01)

        names = {g['name'] for g in payload['groups']}
        assert top_a.name in names
        assert top_b.name in names
        assert leaf_a.name not in names

        school_a = next(g for g in payload['groups'] if g['name'] == top_a.name)
        assert school_a['data'][0] == pytest.approx(2.0, abs=0.01)
        assert len(payload['default_visible_group_ids']) <= 5

    def test_daily_by_group_leaf_level(self, client):
        admin = User.objects.create_superuser(
            username='chart_admin2',
            email='chart2@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Leaf Chart Top', parent=None)
        leaf_group = GroupFactory(name='Leaf Chart Class', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=1),
            distance_km=Decimal('5.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        url = (
            f"{reverse('admin:api_analytics_data_api')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&report_type=daily_by_group&group_type=subgroups"
            f"&metric_mode=km"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
        )

        response = client.get(url)
        payload = response.json()['daily_by_group']
        names = {g['name'] for g in payload['groups']}
        assert leaf_group.name in names
        assert top_group.name not in names
