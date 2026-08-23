# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from api.models import Group, Cyclist
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
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('2.50000'))
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
        assert km_aggregated.get('group_km_source') == 'ledger'
        # Group km uses ledger (Group.distance_total), not HourlyMetric date-range sums.
        assert km_aggregated['total_distance'] == pytest.approx(2.5, abs=0.001)

        top_groups = km_aggregated['top_groups']
        assert len(top_groups) >= 1
        top_names = {g['name'] for g in top_groups}
        assert top_group.name in top_names or leaf_group.name in top_names
        max_top_distance = max(g['distance'] for g in top_groups)
        assert max_top_distance == pytest.approx(2.5, abs=0.001)

    def test_group_km_uses_ledger_not_hourly_metric_sum(self, client):
        """Group km in analytics must match Group.distance_total, not HourlyMetric sums."""
        admin = User.objects.create_superuser(
            username='analytics_ledger_admin',
            email='ledger@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Ledger Top School', parent=None)
        leaf_group = GroupFactory(name='Ledger Class 1a', parent=top_group)
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('42.00000'))
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('1.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        aggregated = response.json()['aggregated']

        assert aggregated['total_distance'] == pytest.approx(42.0, abs=0.001)
        top_entry = next(g for g in aggregated['top_groups'] if g['name'] == top_group.name)
        assert top_entry['distance'] == pytest.approx(42.0, abs=0.001)

    def test_top_group_km_sums_children_not_parent_ledger(self, client):
        """Parent row km must match ranking (children sum), not inflated parent.distance_total."""
        admin = User.objects.create_superuser(
            username='analytics_parent_admin',
            email='parent@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Parent Ledger School', parent=None)
        leaf_group = GroupFactory(name='Parent Ledger Class', parent=top_group)
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('100.00000'))
        Group.objects.filter(pk=top_group.pk).update(distance_total=Decimal('150.00000'))

        now = timezone.now()
        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        aggregated = response.json()['aggregated']

        assert aggregated['total_distance'] == pytest.approx(100.0, abs=0.001)
        top_entry = next(g for g in aggregated['top_groups'] if g['name'] == top_group.name)
        assert top_entry['distance'] == pytest.approx(100.0, abs=0.001)

    def test_cyclist_km_uses_ledger_not_hourly_metric_sum(self, client):
        """Cyclist km in analytics must use Cyclist.distance_total, not HourlyMetric."""
        admin = User.objects.create_superuser(
            username='analytics_cyclist_ledger',
            email='cyclist_ledger@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Cyclist Ledger School', parent=None)
        leaf_group = GroupFactory(name='Cyclist Ledger Class', parent=top_group)
        cyclist = CyclistFactory(user_id='LedgerRider')
        cyclist.groups.add(leaf_group)
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('0'))
        Cyclist.objects.filter(pk=cyclist.pk).update(distance_total=Decimal('88.00000'))

        now = timezone.now()
        HourlyMetricFactory(
            device=DeviceFactory(group=leaf_group),
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('12.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        aggregated = response.json()['aggregated']

        assert aggregated.get('cyclist_km_source') == 'ledger'
        rider = next(c for c in aggregated['top_cyclists'] if c['user_id'] == 'LedgerRider')
        assert rider['distance'] == pytest.approx(88.0, abs=0.001)

    def test_daily_peak_uses_best_single_day_not_period_sum(self, client):
        """Historical daily peak must reflect best calendar day, not the whole filter range."""
        admin = User.objects.create_superuser(
            username='analytics_daily_record',
            email='daily_record@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Daily Record School', parent=None)
        leaf_group = GroupFactory(name='Daily Record Class', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        day_a = (now - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        day_b = (now - timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=day_a,
            distance_km=Decimal('40.00000'),
        )
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=day_b,
            distance_km=Decimal('25.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        aggregated = response.json()['aggregated']

        assert aggregated['daily_peak_value'] == pytest.approx(40.0, abs=0.001)
        assert aggregated['daily_peak_value'] != pytest.approx(65.0, abs=0.001)
        assert aggregated['daily_peak_holder']['name'] == top_group.name
        assert aggregated['daily_record_value'] == aggregated['daily_peak_value']

    def test_yearly_current_km_uses_ledger_like_top_groups(self, client):
        """Current yearly km tile must match ranking ledger, not HourlyMetric calendar year."""
        admin = User.objects.create_superuser(
            username='analytics_yearly_ledger',
            email='yearly@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Yearly Ledger School', parent=None)
        leaf_group = GroupFactory(name='Yearly Ledger Class', parent=top_group)
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('1503.34000'))
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('1288.68000'),
        )

        start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='km'))
        aggregated = response.json()['aggregated']

        assert aggregated.get('yearly_km_source') == 'ledger'
        assert aggregated['yearly_current_value'] == pytest.approx(1503.34, abs=0.01)
        assert aggregated['yearly_current_holder']['name'] == top_group.name
        assert aggregated['yearly_peak_value'] == pytest.approx(1288.68, abs=0.01)
        assert aggregated['total_distance'] == pytest.approx(1503.34, abs=0.01)

    def test_current_and_peak_period_tiles_are_exposed(self, client):
        """API exposes separate current (leaderboard) and peak (historical) fields."""
        admin = User.objects.create_superuser(
            username='analytics_period_tiles',
            email='period@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='Period Tile School', parent=None)
        leaf_group = GroupFactory(name='Period Tile Class', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now.replace(hour=12, minute=0, second=0, microsecond=0),
            velos=50,
            distance_km=Decimal('5.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        response = client.get(self._api_url(start_date, end_date, metric_mode='velos'))
        aggregated = response.json()['aggregated']

        for prefix in ('daily', 'weekly', 'monthly', 'yearly'):
            assert f'{prefix}_current_value' in aggregated
            assert f'{prefix}_peak_value' in aggregated
            assert aggregated[f'{prefix}_current_value'] >= 0
            assert aggregated[f'{prefix}_peak_value'] >= aggregated[f'{prefix}_current_value']

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
        Group.objects.filter(pk=leaf_group.pk).update(distance_total=Decimal('4.00000'))
        Group.objects.filter(pk=mid_group.pk).update(distance_total=Decimal('4.00000'))
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


@pytest.mark.django_db
class TestAnalyticsPdfExport:
    def test_pdf_export_returns_pdf(self, client):
        admin = User.objects.create_superuser(
            username='analytics_pdf_admin',
            email='pdf@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='PDF Top School', parent=None)
        leaf_group = GroupFactory(name='PDF Class 1a', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('3.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        url = (
            f"{reverse('admin:api_analytics_export')}"
            f"?start_date={start_date}&end_date={end_date}"
            f"&format=pdf&metric_mode=velos"
            f"&use_group_filter=false&use_cyclist_filter=false"
            f"&use_event_filter=false&use_track_filter=false"
            f"&group_type=top_groups"
        )

        response = client.get(url)
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert response.content[:4] == b'%PDF'
        assert len(response.content) > 500
        assert 'attachment' in response['Content-Disposition']
        assert '.pdf' in response['Content-Disposition']

    def test_pdf_export_post_with_chart_images(self, client):
        admin = User.objects.create_superuser(
            username='analytics_pdf_post_admin',
            email='pdfpost@example.com',
            password='testpass123',
        )
        client.force_login(admin)

        top_group = GroupFactory(name='PDF POST Top School', parent=None)
        leaf_group = GroupFactory(name='PDF POST Class 1a', parent=top_group)
        device = DeviceFactory(group=leaf_group)
        cyclist = CyclistFactory()

        now = timezone.now()
        HourlyMetricFactory(
            device=device,
            cyclist=cyclist,
            group_at_time=leaf_group,
            timestamp=now - timedelta(days=2),
            distance_km=Decimal('3.00000'),
        )

        start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        tiny_png = (
            'data:image/png;base64,'
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
        )
        response = client.post(
            reverse('admin:api_analytics_export'),
            data={
                'format': 'pdf',
                'start_date': start_date,
                'end_date': end_date,
                'metric_mode': 'velos',
                'use_group_filter': 'false',
                'use_cyclist_filter': 'false',
                'use_event_filter': 'false',
                'use_track_filter': 'false',
                'group_type': 'top_groups',
                'daily_chart_image': tiny_png,
                'hourly_chart_image': tiny_png,
            },
        )
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert response.content[:4] == b'%PDF'
        assert len(response.content) > 800
