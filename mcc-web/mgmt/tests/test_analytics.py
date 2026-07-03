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
class TestAnalyticsTotalDistance:
    def _api_url(self, start_date: str, end_date: str, metric_mode: str = 'velos') -> str:
        return (
            f"{reverse('admin:api_analytics_data_api')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&report_type=aggregated"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
            f"&metric_mode={metric_mode}"
        )

    def test_total_distance_respects_date_filter(self, client):
        admin = User.objects.create_superuser(
            username='analytics_admin',
            email='analytics@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Analytics Top School', parent=None)
        leaf_group = GroupFactory(name='Analytics Class 1a', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        in_range_ts = now - timedelta(days=5)
        out_of_range_ts = now - timedelta(days=200)

        in_range_metric = HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=in_range_ts,
            distance_km=Decimal('2.50000'),
        )
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=out_of_range_ts,
            distance_km=Decimal('99.00000'),
        )

        start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')

        velos_response = client.get(self._api_url(start_date, end_date, metric_mode='velos'))
        assert velos_response.status_code == 200
        velos_aggregated = velos_response.json()['aggregated']
        assert velos_aggregated['metric_mode'] == 'velos'
        assert velos_aggregated['total_distance'] == pytest.approx(float(in_range_metric.velos), abs=0.001)

        default_response = client.get(
            f"{reverse('admin:api_analytics_data_api')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&report_type=aggregated"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
        )
        assert default_response.json()['metric_mode'] == 'velos'

        km_response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        assert km_response.status_code == 200
        km_aggregated = km_response.json()['aggregated']
        assert km_aggregated['metric_mode'] == 'km'
        assert km_aggregated['total_distance'] == pytest.approx(2.5, abs=0.001)

        top_groups = km_aggregated['top_groups']
        assert len(top_groups) >= 1
        top_names = {g['name'] for g in top_groups}
        assert top_group.name in top_names or leaf_group.name in top_names
        max_top_distance = max(g['distance'] for g in top_groups)
        assert max_top_distance == pytest.approx(2.5, abs=0.001)

    def test_groups_table_top_vs_leaf_filter(self, client):
        admin = User.objects.create_superuser(
            username='analytics_admin2',
            email='analytics2@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Filter Top School', parent=None)
        mid_group = GroupFactory(name='Filter Grade 5', parent=top_group)
        leaf_group = GroupFactory(name='Filter Class 5a', parent=mid_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('4.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        base = (
            f"{reverse('admin:api_analytics_data_api')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&report_type=aggregated"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
            f"&metric_mode=km"
        )

        top_response = client.get(f"{base}&group_type=top_groups")
        leaf_response = client.get(f"{base}&group_type=subgroups")

        top_names = {g['name'] for g in top_response.json()['aggregated']['top_groups']}
        leaf_names = {g['name'] for g in leaf_response.json()['aggregated']['top_groups']}

        assert top_group.name in top_names
        assert leaf_group.name not in top_names
        assert mid_group.name not in top_names

        assert leaf_group.name in leaf_names
        assert top_group.name not in leaf_names
        assert mid_group.name not in leaf_names

        assert not top_names & leaf_names
