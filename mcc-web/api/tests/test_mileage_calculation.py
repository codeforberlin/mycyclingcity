# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_mileage_calculation.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Unit tests for mileage calculation logic.

Tests cover:
- Midnight resets and date boundary handling
- Cumulative sums and session management
- HourlyMetric aggregation
- CyclistDeviceCurrentMileage updates
"""

import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from api.models import (
    Cyclist, Group, HourlyMetric, CyclistDeviceCurrentMileage
)
from iot.models import Device
from api.tests.conftest import (
    CyclistFactory, DeviceFactory, GroupFactory, HourlyMetricFactory,
    CyclistDeviceCurrentMileageFactory
)


@pytest.mark.unit
@pytest.mark.mileage
@pytest.mark.django_db
class TestMidnightResets:
    """Tests for midnight reset logic and date boundary handling."""
    
    def test_hourly_metric_timestamp_rounding(self, today_start):
        """Test that HourlyMetric timestamps can be rounded to the hour for aggregation."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        group = GroupFactory()
        
        # Create metrics at different minutes in the same hour
        # Note: Factory uses LazyFunction which rounds to hour, so we create directly
        hour_timestamp = today_start.replace(hour=10, minute=0, second=0, microsecond=0)
        
        metric1 = HourlyMetric.objects.create(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=hour_timestamp.replace(minute=15, second=30),
            distance_km=Decimal('5.00000')
        )
        
        metric2 = HourlyMetric.objects.create(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=hour_timestamp.replace(minute=45, second=0),
            distance_km=Decimal('3.00000')
        )
        
        # Query all metrics for this player/device (they have different timestamps)
        metrics = HourlyMetric.objects.filter(
            cyclist = cyclist,
            device=device
        )
        
        # Should have 2 separate entries
        assert metrics.count() == 2
        
        # Manual aggregation should sum to 8.0
        total = sum(float(m.distance_km) for m in metrics)
        assert total == 8.0
    
    def test_daily_km_calculation_across_midnight(self, today_start, yesterday_start):
        """Test daily kilometer calculation handles midnight boundary correctly."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        group = GroupFactory()
        
        # Create metrics on different days
        yesterday_metric = HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=yesterday_start.replace(hour=23, minute=0),
            distance_km=Decimal('10.00000')
        )
        
        today_metric = HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=today_start.replace(hour=1, minute=0),
            distance_km=Decimal('5.00000')
        )
        
        # Query today's metrics
        today_metrics = HourlyMetric.objects.filter(
            timestamp__gte=today_start,
            group_at_time=group
        )
        
        today_total = sum(float(m.distance_km) for m in today_metrics)
        assert today_total == 5.0
        
        # Query yesterday's metrics
        yesterday_metrics = HourlyMetric.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=today_start,
            group_at_time=group
        )
        
        yesterday_total = sum(float(m.distance_km) for m in yesterday_metrics)
        assert yesterday_total == 10.0
    
    def test_session_continues_across_midnight(self, today_start, yesterday_start):
        """Test that active sessions continue across midnight boundary."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        
        # Create session that started yesterday
        session = CyclistDeviceCurrentMileageFactory(
            cyclist = cyclist,
            device=device,
            start_time=yesterday_start.replace(hour=22, minute=0),
            cumulative_mileage=Decimal('15.00000'),
            last_activity=yesterday_start.replace(hour=23, minute=59)
        )
        
        # Update session today (simulating continuation)
        session.cumulative_mileage += Decimal('5.00000')
        session.last_activity = today_start.replace(hour=1, minute=0)
        session.save()
        
        # Session should still exist
        assert CyclistDeviceCurrentMileage.objects.filter(cyclist = cyclist).exists()
        assert session.cumulative_mileage == Decimal('20.00000')
        
        # Daily calculation should include this session for today
        active_sessions_today = CyclistDeviceCurrentMileage.objects.filter(
            last_activity__gte=today_start,
            cumulative_mileage__gt=0
        )
        assert active_sessions_today.filter(cyclist = cyclist).exists()


@pytest.mark.unit
@pytest.mark.mileage
@pytest.mark.django_db
class TestCumulativeSums:
    """Tests for cumulative sum calculations."""
    
    def test_cyclist_distance_cumulative(self, cyclist_with_group):
        """Test that cyclist distance_total accumulates correctly."""
        cyclist = cyclist_with_group['cyclist']
        device = DeviceFactory()
        
        # Initial distance
        assert cyclist.distance_total == Decimal('0.00000')
        
        # Simulate multiple updates
        cyclist.distance_total += Decimal('5.00000')
        cyclist.save()
        
        cyclist.distance_total += Decimal('3.50000')
        cyclist.save()
        
        cyclist.refresh_from_db()
        assert cyclist.distance_total == Decimal('8.50000')
    
    def test_device_distance_cumulative(self, device_with_group):
        """Test that device distance_total accumulates correctly."""
        device = device_with_group['device']
        
        # Initial distance
        assert device.distance_total == Decimal('0.00000')
        
        # Simulate multiple updates
        device.distance_total += Decimal('10.00000')
        device.save()
        
        device.distance_total += Decimal('7.25000')
        device.save()
        
        device.refresh_from_db()
        assert device.distance_total == Decimal('17.25000')
    
    def test_group_distance_cumulative(self, group_hierarchy):
        """Test that group distance_total accumulates correctly."""
        child = group_hierarchy['child1']
        parent = group_hierarchy['parent']
        
        # Initial distances
        assert child.distance_total == Decimal('0.00000')
        assert parent.distance_total == Decimal('0.00000')
        
        # Add to child
        child.add_to_totals(Decimal('10.00000'), 0)
        child.refresh_from_db()
        parent.refresh_from_db()
        
        assert child.distance_total == Decimal('10.00000')
        assert parent.distance_total == Decimal('10.00000')
        
        # Add more to child
        child.add_to_totals(Decimal('5.00000'), 0)
        child.refresh_from_db()
        parent.refresh_from_db()
        
        assert child.distance_total == Decimal('15.00000')
        assert parent.distance_total == Decimal('15.00000')
    
    def test_session_cumulative_mileage(self, complete_test_scenario):
        """Test that session cumulative_mileage accumulates correctly."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        # Create session
        session = CyclistDeviceCurrentMileageFactory(
            cyclist = cyclist,
            device=device,
            cumulative_mileage=Decimal('0.00000')
        )
        
        # Simulate multiple updates
        session.cumulative_mileage += Decimal('2.50000')
        session.save()
        
        session.cumulative_mileage += Decimal('1.75000')
        session.save()
        
        session.refresh_from_db()
        assert session.cumulative_mileage == Decimal('4.25000')


@pytest.mark.unit
@pytest.mark.mileage
@pytest.mark.django_db
class TestHourlyMetricAggregation:
    """Tests for HourlyMetric aggregation logic."""
    
    def test_hourly_metric_aggregation_same_hour(self, today_start):
        """Test that multiple metrics in same hour can be aggregated."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        group = GroupFactory()
        
        hour_timestamp = today_start.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create multiple metrics in same hour
        HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=hour_timestamp,
            distance_km=Decimal('5.00000')
        )
        
        HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=hour_timestamp,
            distance_km=Decimal('3.00000')
        )
        
        # Aggregate using Django ORM
        from django.db.models import Sum
        aggregated = HourlyMetric.objects.filter(
            cyclist = cyclist,
            device=device,
            timestamp=hour_timestamp
        ).aggregate(total=Sum('distance_km'))
        
        assert float(aggregated['total']) == 8.0
    
    def test_hourly_metric_group_by_hour(self, today_start):
        """Test grouping HourlyMetrics by hour."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        group = GroupFactory()
        
        # Create metrics in different hours
        HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=today_start.replace(hour=10, minute=0),
            distance_km=Decimal('5.00000')
        )
        
        HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=today_start.replace(hour=11, minute=0),
            distance_km=Decimal('3.00000')
        )
        
        HourlyMetricFactory(
            cyclist = cyclist,
            device=device,
            group_at_time=group,
            timestamp=today_start.replace(hour=12, minute=0),
            distance_km=Decimal('7.00000')
        )
        
        # Group by hour
        from django.db.models import Sum
        from django.db.models.functions import TruncHour
        
        hourly_totals = HourlyMetric.objects.filter(
            cyclist = cyclist,
            device=device,
            timestamp__date=today_start.date()
        ).annotate(
            hour=TruncHour('timestamp')
        ).values('hour').annotate(
            total=Sum('distance_km')
        ).order_by('hour')
        
        totals = list(hourly_totals)
        assert len(totals) == 3
        assert float(totals[0]['total']) == 5.0
        assert float(totals[1]['total']) == 3.0
        assert float(totals[2]['total']) == 7.0
    
    def test_hourly_metric_daily_sum(self, today_start):
        """Test summing all HourlyMetrics for a day."""
        cyclist = CyclistFactory()
        device = DeviceFactory()
        group = GroupFactory()
        
        # Create metrics throughout the day
        for hour in range(8, 18):  # 8 AM to 5 PM
            HourlyMetricFactory(
                cyclist = cyclist,
                device=device,
                group_at_time=group,
                timestamp=today_start.replace(hour=hour, minute=0),
                distance_km=Decimal('1.00000')
            )
        
        # Sum all metrics for today
        from django.db.models import Sum
        daily_total = HourlyMetric.objects.filter(
            cyclist = cyclist,
            device=device,
            timestamp__date=today_start.date()
        ).aggregate(total=Sum('distance_km'))
        
        assert float(daily_total['total']) == 10.0  # 10 hours * 1.0 km


@pytest.mark.unit
@pytest.mark.mileage
@pytest.mark.django_db
class TestSessionManagement:
    """Tests for CyclistDeviceCurrentMileage session management."""
    
    def test_session_creation_on_first_update(self, complete_test_scenario):
        """Test that session is created on first update."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        # No session should exist initially
        assert not CyclistDeviceCurrentMileage.objects.filter(cyclist = cyclist).exists()
        
        # Create session
        session = CyclistDeviceCurrentMileageFactory(
            cyclist = cyclist,
            device=device,
            cumulative_mileage=Decimal('1.00000')
        )
        
        # Session should exist
        assert CyclistDeviceCurrentMileage.objects.filter(cyclist = cyclist).exists()
        assert session.cumulative_mileage == Decimal('1.00000')
        assert session.start_time is not None
    
    def test_session_update_cumulative(self, complete_test_scenario):
        """Test that session cumulative_mileage updates correctly."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        session = CyclistDeviceCurrentMileageFactory(
            cyclist = cyclist,
            device=device,
            cumulative_mileage=Decimal('5.00000')
        )
        
        # Update cumulative mileage
        session.cumulative_mileage += Decimal('2.50000')
        session.save()
        
        session.refresh_from_db()
        assert session.cumulative_mileage == Decimal('7.50000')
    
    def test_session_last_activity_auto_update(self, complete_test_scenario):
        """Test that last_activity is auto-updated on save."""
        scenario = complete_test_scenario
        cyclist = scenario['cyclist']
        device = scenario['device']
        
        old_time = timezone.now() - timedelta(minutes=10)
        session = CyclistDeviceCurrentMileageFactory(
            cyclist = cyclist,
            device=device,
            last_activity=old_time
        )
        
        # Save should update last_activity (auto_now=True)
        session.cumulative_mileage += Decimal('1.00000')
        session.save()
        
        session.refresh_from_db()
        assert session.last_activity > old_time

