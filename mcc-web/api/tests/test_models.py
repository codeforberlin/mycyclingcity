"""
Unit tests for all Django models.

Tests cover:
- Model creation and validation
- Model methods and properties
- Model relationships
- Business logic in models
"""

import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from api.models import (
    Group, Cyclist, HourlyMetric, CyclistDeviceCurrentMileage,
    TravelTrack, Milestone, GroupTravelStatus, Event, GroupEventStatus,
    EventHistory, TravelHistory
)
from iot.models import Device
from api.tests.conftest import (
    GroupFactory, CyclistFactory, DeviceFactory, HourlyMetricFactory,
    CyclistDeviceCurrentMileageFactory, TravelTrackFactory, MilestoneFactory,
    GroupTravelStatusFactory, EventFactory, GroupEventStatusFactory
)


@pytest.mark.unit
@pytest.mark.django_db
class TestGroupModel:
    """Tests for Group model."""
    
    def test_group_creation(self, group_hierarchy):
        """Test basic group creation."""
        group = group_hierarchy['parent']
        assert group.name == 'Parent Group'
        assert group.group_type.name == 'Schule'
        assert group.distance_total == Decimal('0.00000')
        assert group.is_visible is True
    
    def test_group_str_representation(self, group_hierarchy):
        """Test Group __str__ method."""
        group = group_hierarchy['parent']
        assert str(group) == 'Schule: Parent Group'
    
    def test_group_add_to_totals(self, group_hierarchy):
        """Test add_to_totals method propagates to parent."""
        child = group_hierarchy['child1']
        parent = group_hierarchy['parent']
        
        initial_child_total = child.distance_total
        initial_parent_total = parent.distance_total
        
        child.add_to_totals(Decimal('10.50000'), 5)
        
        child.refresh_from_db()
        parent.refresh_from_db()
        
        assert child.distance_total == initial_child_total + Decimal('10.50000')
        assert child.coins_total == 5
        assert parent.distance_total == initial_parent_total + Decimal('10.50000')
        assert parent.coins_total == 5
    
    def test_group_recalculate_totals(self, group_hierarchy):
        """Test recalculate_totals method."""
        child = group_hierarchy['child1']
        parent = group_hierarchy['parent']
        
        # Create a cyclist and add to child group
        cyclist = CyclistFactory()
        cyclist.distance_total = Decimal('25.00000')
        cyclist.save()
        cyclist.groups.add(child)
        
        # Recalculate child group
        child.recalculate_totals()
        child.refresh_from_db()
        
        # Child should have cyclist's distance
        assert child.distance_total == Decimal('25.00000')
        
        # Recalculate parent
        parent.recalculate_totals()
        parent.refresh_from_db()
        
        # Parent should have child's distance
        assert parent.distance_total == Decimal('25.00000')
    
    def test_group_get_kiosk_label(self, group_hierarchy):
        """Test get_kiosk_label method."""
        child = group_hierarchy['child1']
        
        # Without short_name, should return name
        assert child.get_kiosk_label() == 'Child Group 1'
        
        # With short_name, should return short_name
        child.short_name = '1a'
        child.save()
        assert child.get_kiosk_label() == '1a'
    
    def test_group_top_parent_name(self, group_hierarchy):
        """Test top_parent_name property."""
        child = group_hierarchy['child1']
        parent = group_hierarchy['parent']
        
        assert child.top_parent_name == 'Parent Group'
        assert parent.top_parent_name == 'Parent Group'
    
    def test_group_unique_together(self, db):
        """Test that group_type and name must be unique together."""
        from api.models import GroupType
        school_type, _ = GroupType.objects.get_or_create(name='Schule', defaults={'is_active': True})
        Group.objects.create(group_type=school_type, name='Test School')
        
        # Creating another with same type and name should fail
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            Group.objects.create(group_type=school_type, name='Test School')


@pytest.mark.unit
@pytest.mark.django_db
class TestCyclistModel:
    """Tests for Cyclist model."""
    
    def test_cyclist_creation(self, cyclist_with_group):
        """Test basic cyclist creation."""
        cyclist = cyclist_with_group['cyclist']
        assert cyclist.user_id is not None
        assert cyclist.id_tag is not None
        assert cyclist.distance_total == Decimal('0.00000')
        assert cyclist.is_visible is True
        assert cyclist.is_km_collection_enabled is True
    
    def test_cyclist_str_representation(self, cyclist_with_group):
        """Test Cyclist __str__ method."""
        cyclist = cyclist_with_group['cyclist']
        expected = f"{cyclist.user_id} ({cyclist.id_tag})"
        assert str(cyclist) == expected
    
    def test_cyclist_unique_id_tag(self, db):
        """Test that id_tag must be unique."""
        Cyclist.objects.create(
            user_id='cyclist1',
            id_tag='unique-tag-001',
            distance_total=Decimal('0.00000')
        )
        
        # Creating another with same id_tag should fail
        with pytest.raises(Exception):  # IntegrityError
            Cyclist.objects.create(
                user_id='cyclist2',
                id_tag='unique-tag-001',
                distance_total=Decimal('0.00000')
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceModel:
    """Tests for Device model."""
    
    def test_device_creation(self, device_with_group):
        """Test basic device creation."""
        device = device_with_group['device']
        assert device.name is not None
        assert device.distance_total == Decimal('0.00000')
        assert device.is_visible is True
        assert device.is_km_collection_enabled is True
    
    def test_device_str_representation(self, device_with_group):
        """Test Device __str__ method."""
        device = device_with_group['device']
        # Should use display_name if available
        assert str(device) == device.display_name
    
    def test_device_unique_name(self, db):
        """Test that device name must be unique."""
        Device.objects.create(
            name='unique-device-001',
            distance_total=Decimal('0.00000')
        )
        
        # Creating another with same name should fail
        with pytest.raises(Exception):  # IntegrityError
            Device.objects.create(
                name='unique-device-001',
                distance_total=Decimal('0.00000')
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestTravelTrackModel:
    """Tests for TravelTrack model."""
    
    def test_travel_track_creation(self, active_travel_track):
        """Test basic travel track creation."""
        track = active_travel_track
        assert track.name == 'Test Track'
        assert track.total_length_km == Decimal('100.00000')
        assert track.is_active is True
    
    def test_travel_track_is_currently_active(self, db):
        """Test is_currently_active method."""
        now = timezone.now()
        
        # Active track (within time range)
        track1 = TravelTrackFactory(
            is_active=True,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1)
        )
        assert track1.is_currently_active() is True
        
        # Inactive track (not started yet)
        track2 = TravelTrackFactory(
            is_active=True,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2)
        )
        assert track2.is_currently_active() is False
        
        # Inactive track (already ended)
        track3 = TravelTrackFactory(
            is_active=True,
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1)
        )
        assert track3.is_currently_active() is False
        
        # Note: is_currently_active() only checks time, not is_active flag
        # So a track with is_active=False but valid time range will return True
        # This is by design - the method checks if trip is currently active based on time
        # The is_active flag is checked separately in queries
        track4 = TravelTrack.objects.create(
            name='Track4',
            is_active=False,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            total_length_km=Decimal('100.00000')
        )
        # The method only checks time, not is_active flag
        # So it returns True if time range is valid, regardless of is_active
        result = track4.is_currently_active()
        assert result is True  # Method checks time only, not is_active flag
    
    def test_travel_track_restart_trip(self, active_travel_track, group_hierarchy):
        """Test restart_trip method resets statuses."""
        track = active_travel_track
        group = group_hierarchy['child1']
        
        # Create travel status
        status = GroupTravelStatusFactory(
            group=group,
            track=track,
            current_travel_distance=Decimal('50.00000')
        )
        
        # Create milestone
        milestone = MilestoneFactory(
            track=track,
            distance_km=Decimal('25.00000'),
            winner_group=group
        )
        
        # Restart trip
        track.restart_trip()
        
        status.refresh_from_db()
        milestone.refresh_from_db()
        
        assert status.current_travel_distance == Decimal('0.00000')
        assert milestone.winner_group is None
        assert milestone.reached_at is None


@pytest.mark.unit
@pytest.mark.django_db
class TestEventModel:
    """Tests for Event model."""
    
    def test_event_creation(self, active_event):
        """Test basic event creation."""
        event = active_event
        assert event.name == 'Test Event'
        assert event.is_active is True
    
    def test_event_is_currently_active(self, db):
        """Test is_currently_active method."""
        now = timezone.now()
        
        # Active event
        event1 = EventFactory(
            is_active=True,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1)
        )
        assert event1.is_currently_active() is True
        
        # Inactive event (not started)
        event2 = EventFactory(
            is_active=True,
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=2)
        )
        assert event2.is_currently_active() is False
        
        # Inactive event (ended)
        event3 = EventFactory(
            is_active=True,
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1)
        )
        assert event3.is_currently_active() is False
    
    def test_event_should_be_displayed(self, db):
        """Test should_be_displayed method."""
        now = timezone.now()
        
        # Should be displayed
        event1 = EventFactory(
            is_active=True,
            is_visible_on_map=True,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1)
        )
        assert event1.should_be_displayed() is True
        
        # Should not be displayed (not visible)
        event2 = EventFactory(
            is_active=True,
            is_visible_on_map=False,
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1)
        )
        assert event2.should_be_displayed() is False
        
        # Should not be displayed (hide_after_date passed)
        event3 = EventFactory(
            is_active=True,
            is_visible_on_map=True,
            start_time=now - timedelta(days=2),
            end_time=now - timedelta(days=1),
            hide_after_date=now - timedelta(hours=1)
        )
        assert event3.should_be_displayed() is False


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyMetricModel:
    """Tests for HourlyMetric model."""
    
    def test_hourly_metric_creation(self, complete_test_scenario):
        """Test basic hourly metric creation."""
        scenario = complete_test_scenario
        metric = HourlyMetricFactory(
            cyclist=scenario['cyclist'],
            device=scenario['device'],
            group_at_time=scenario['child_group'],
            distance_km=Decimal('5.50000')
        )
        
        assert metric.distance_km == Decimal('5.50000')
        assert metric.cyclist == scenario['cyclist']
        assert metric.device == scenario['device']
        assert metric.group_at_time == scenario['child_group']


@pytest.mark.unit
@pytest.mark.django_db
class TestCyclistDeviceCurrentMileageModel:
    """Tests for CyclistDeviceCurrentMileage model."""
    
    def test_session_creation(self, complete_test_scenario):
        """Test basic session creation."""
        scenario = complete_test_scenario
        session = CyclistDeviceCurrentMileageFactory(
            cyclist=scenario['cyclist'],
            device=scenario['device'],
            cumulative_mileage=Decimal('10.00000')
        )
        
        assert session.cumulative_mileage == Decimal('10.00000')
        assert session.cyclist == scenario['cyclist']
        assert session.device == scenario['device']
        assert session.start_time is not None
        assert session.last_activity is not None
    
    def test_session_one_to_one_cyclist(self, db):
        """Test that one cyclist can only have one active session."""
        cyclist = CyclistFactory()
        device1 = DeviceFactory()
        device2 = DeviceFactory()
        
        # Create first session
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device1,
            cumulative_mileage=Decimal('0.00000')
        )
        
        # Creating another session for same cyclist should fail
        with pytest.raises(Exception):  # IntegrityError
            CyclistDeviceCurrentMileage.objects.create(
                cyclist=cyclist,
                device=device2,
                cumulative_mileage=Decimal('0.00000')
            )

