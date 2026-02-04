# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Eventboard views.

Tests cover:
- eventboard_page view
- eventboard_ticker view (Activity Toasts)
- get_active_cyclists_for_eventboard utility function
- Event and group filtering
"""

import pytest
from django.test import Client, RequestFactory
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from eventboard.views import eventboard_page, eventboard_ticker, eventboard_api
from eventboard.utils import get_active_cyclists_for_eventboard, get_all_subgroup_ids
from api.models import update_group_hierarchy_progress, GroupEventStatus
from api.tests.conftest import (
    GroupFactory, CyclistFactory, DeviceFactory, EventFactory,
    GroupEventStatusFactory, CyclistDeviceCurrentMileageFactory,
    TravelTrackFactory, GroupTravelStatusFactory
)


@pytest.mark.unit
@pytest.mark.django_db
class TestEventboardViews:
    """Tests for Eventboard views."""
    
    def test_eventboard_page_no_event(self):
        """Test eventboard page without event_id (shows event selection)."""
        client = Client()
        response = client.get('/de/eventboard/')
        
        assert response.status_code == 200
        assert 'show_event_selection' in response.context
        assert response.context['show_event_selection'] is True
    
    def test_eventboard_page_with_event(self):
        """Test eventboard page with event_id."""
        event = EventFactory()
        group = GroupFactory()
        GroupEventStatusFactory(event=event, group=group)
        
        client = Client()
        response = client.get(f'/de/eventboard/?event_id={event.id}')
        
        assert response.status_code == 200
        assert 'event' in response.context
        assert response.context['event'].id == event.id
    
    def test_eventboard_ticker_no_active_cyclists(self):
        """Test eventboard ticker with no active cyclists."""
        client = Client()
        response = client.get('/de/eventboard/ticker/')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        assert len(response.context['active_cyclists']) == 0
    
    def test_eventboard_ticker_with_active_cyclist(self):
        """Test eventboard ticker with active cyclist (last_active < 60s ago)."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)  # 30 seconds ago (active)
        
        cyclist = CyclistFactory(last_active=active_cutoff)
        device = DeviceFactory()
        session = CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('5.50000')
        )
        group = GroupFactory()
        cyclist.groups.add(group)
        
        client = Client()
        response = client.get('/de/eventboard/ticker/')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        assert len(response.context['active_cyclists']) == 1
        assert response.context['active_cyclists'][0]['user_id'] == cyclist.user_id
        assert response.context['active_cyclists'][0]['session_km'] == 5.5
    
    def test_eventboard_ticker_with_inactive_cyclist(self):
        """Test eventboard ticker with inactive cyclist (last_active > 60s ago)."""
        now = timezone.now()
        inactive_cutoff = now - timedelta(seconds=120)  # 120 seconds ago (inactive)
        
        cyclist = CyclistFactory(last_active=inactive_cutoff)
        device = DeviceFactory()
        session = CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('5.50000')
        )
        group = GroupFactory()
        cyclist.groups.add(group)
        
        client = Client()
        response = client.get('/de/eventboard/ticker/')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        assert len(response.context['active_cyclists']) == 0
    
    def test_eventboard_ticker_with_event_filter(self):
        """Test eventboard ticker with event_id filter."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        event = EventFactory()
        group1 = GroupFactory()
        group2 = GroupFactory()
        
        # Add groups to event
        GroupEventStatusFactory(event=event, group=group1)
        GroupEventStatusFactory(event=event, group=group2)
        
        # Create cyclists in different groups
        cyclist1 = CyclistFactory(last_active=active_cutoff)
        cyclist1.groups.add(group1)
        device1 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist1,
            device=device1,
            cumulative_mileage=Decimal('10.00000')
        )
        
        cyclist2 = CyclistFactory(last_active=active_cutoff)
        cyclist2.groups.add(group2)
        device2 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist2,
            device=device2,
            cumulative_mileage=Decimal('15.00000')
        )
        
        # Create cyclist in group not part of event
        group3 = GroupFactory()
        cyclist3 = CyclistFactory(last_active=active_cutoff)
        cyclist3.groups.add(group3)
        device3 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist3,
            device=device3,
            cumulative_mileage=Decimal('20.00000')
        )
        
        client = Client()
        response = client.get(f'/de/eventboard/ticker/?event_id={event.id}')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        # Should only include cyclists from groups in the event
        active_cyclists = response.context['active_cyclists']
        assert len(active_cyclists) == 2
        user_ids = [c['user_id'] for c in active_cyclists]
        assert cyclist1.user_id in user_ids
        assert cyclist2.user_id in user_ids
        assert cyclist3.user_id not in user_ids
    
    def test_eventboard_ticker_with_group_filter(self):
        """Test eventboard ticker with group_filter_id (TOP-group filter)."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        # Create TOP-group with subgroup
        top_group = GroupFactory(parent=None)
        subgroup = GroupFactory(parent=top_group)
        
        # Create cyclists in different groups
        cyclist1 = CyclistFactory(last_active=active_cutoff)
        cyclist1.groups.add(top_group)
        device1 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist1,
            device=device1,
            cumulative_mileage=Decimal('10.00000')
        )
        
        cyclist2 = CyclistFactory(last_active=active_cutoff)
        cyclist2.groups.add(subgroup)
        device2 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist2,
            device=device2,
            cumulative_mileage=Decimal('15.00000')
        )
        
        # Create cyclist in different TOP-group
        other_top_group = GroupFactory(parent=None)
        cyclist3 = CyclistFactory(last_active=active_cutoff)
        cyclist3.groups.add(other_top_group)
        device3 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist3,
            device=device3,
            cumulative_mileage=Decimal('20.00000')
        )
        
        client = Client()
        response = client.get(f'/de/eventboard/ticker/?group_filter_id={top_group.id}')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        # Should only include cyclists from top_group and its subgroups
        active_cyclists = response.context['active_cyclists']
        assert len(active_cyclists) == 2
        user_ids = [c['user_id'] for c in active_cyclists]
        assert cyclist1.user_id in user_ids
        assert cyclist2.user_id in user_ids
        assert cyclist3.user_id not in user_ids
    
    def test_eventboard_ticker_with_event_and_group_filter(self):
        """Test eventboard ticker with both event_id and group_filter_id."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        event = EventFactory()
        top_group = GroupFactory(parent=None)
        subgroup = GroupFactory(parent=top_group)
        
        # Add groups to event
        GroupEventStatusFactory(event=event, group=top_group)
        GroupEventStatusFactory(event=event, group=subgroup)
        
        # Create active cyclist in subgroup
        cyclist = CyclistFactory(last_active=active_cutoff)
        cyclist.groups.add(subgroup)
        device = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal('10.00000')
        )
        
        client = Client()
        response = client.get(f'/de/eventboard/ticker/?event_id={event.id}&group_filter_id={top_group.id}')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        active_cyclists = response.context['active_cyclists']
        assert len(active_cyclists) == 1
        assert active_cyclists[0]['user_id'] == cyclist.user_id
    
    def test_eventboard_ticker_cyclist_without_session(self):
        """Test eventboard ticker with cyclist without active session (should still be included with 0 km)."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        cyclist = CyclistFactory(last_active=active_cutoff)
        group = GroupFactory()
        cyclist.groups.add(group)
        # No CyclistDeviceCurrentMileage created
        
        client = Client()
        response = client.get('/de/eventboard/ticker/')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        # Should include cyclist even without session (with 0 km)
        active_cyclists = response.context['active_cyclists']
        assert len(active_cyclists) == 1
        assert active_cyclists[0]['user_id'] == cyclist.user_id
        assert active_cyclists[0]['session_km'] == 0.0
    
    def test_eventboard_ticker_sorts_by_session_km(self):
        """Test that eventboard ticker sorts cyclists by session_km (descending)."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        cyclist1 = CyclistFactory(last_active=active_cutoff)
        group = GroupFactory()
        cyclist1.groups.add(group)
        device1 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist1,
            device=device1,
            cumulative_mileage=Decimal('5.00000')
        )
        
        cyclist2 = CyclistFactory(last_active=active_cutoff)
        cyclist2.groups.add(group)
        device2 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist2,
            device=device2,
            cumulative_mileage=Decimal('15.00000')
        )
        
        cyclist3 = CyclistFactory(last_active=active_cutoff)
        cyclist3.groups.add(group)
        device3 = DeviceFactory()
        CyclistDeviceCurrentMileageFactory(
            cyclist=cyclist3,
            device=device3,
            cumulative_mileage=Decimal('10.00000')
        )
        
        client = Client()
        response = client.get('/de/eventboard/ticker/')
        
        assert response.status_code == 200
        assert 'active_cyclists' in response.context
        active_cyclists = response.context['active_cyclists']
        assert len(active_cyclists) == 3
        # Should be sorted by session_km descending
        assert active_cyclists[0]['session_km'] == 15.0
        assert active_cyclists[1]['session_km'] == 10.0
        assert active_cyclists[2]['session_km'] == 5.0


@pytest.mark.unit
@pytest.mark.django_db
class TestEventboardUtils:
    """Tests for Eventboard utility functions."""
    
    def test_get_active_cyclists_for_eventboard_no_filters(self):
        """Test get_active_cyclists_for_eventboard without filters."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        cyclist = CyclistFactory(last_active=active_cutoff)
        group = GroupFactory()
        cyclist.groups.add(group)
        
        result = get_active_cyclists_for_eventboard()
        
        assert result.count() >= 1
        assert cyclist in result
    
    def test_get_active_cyclists_for_eventboard_with_event_filter(self):
        """Test get_active_cyclists_for_eventboard with event_id filter."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        event = EventFactory()
        group1 = GroupFactory()
        group2 = GroupFactory()
        
        GroupEventStatusFactory(event=event, group=group1)
        
        cyclist1 = CyclistFactory(last_active=active_cutoff)
        cyclist1.groups.add(group1)
        
        cyclist2 = CyclistFactory(last_active=active_cutoff)
        cyclist2.groups.add(group2)
        
        result = get_active_cyclists_for_eventboard(event_id=event.id)
        
        assert result.count() == 1
        assert cyclist1 in result
        assert cyclist2 not in result
    
    def test_get_active_cyclists_for_eventboard_with_group_filter(self):
        """Test get_active_cyclists_for_eventboard with group_filter_id."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=30)
        
        top_group = GroupFactory(parent=None)
        subgroup = GroupFactory(parent=top_group)
        other_top_group = GroupFactory(parent=None)
        
        cyclist1 = CyclistFactory(last_active=active_cutoff)
        cyclist1.groups.add(top_group)
        
        cyclist2 = CyclistFactory(last_active=active_cutoff)
        cyclist2.groups.add(subgroup)
        
        cyclist3 = CyclistFactory(last_active=active_cutoff)
        cyclist3.groups.add(other_top_group)
        
        result = get_active_cyclists_for_eventboard(group_filter_id=top_group.id)
        
        assert result.count() == 2
        assert cyclist1 in result
        assert cyclist2 in result
        assert cyclist3 not in result
    
    def test_get_active_cyclists_for_eventboard_inactive_cyclist(self):
        """Test that inactive cyclists (last_active > 60s ago) are not included."""
        now = timezone.now()
        inactive_cutoff = now - timedelta(seconds=120)
        
        cyclist = CyclistFactory(last_active=inactive_cutoff)
        group = GroupFactory()
        cyclist.groups.add(group)
        
        result = get_active_cyclists_for_eventboard()
        
        assert cyclist not in result
    
    def test_update_group_hierarchy_progress_adds_kilometers_to_event(self):
        """Test that update_group_hierarchy_progress adds kilometers to event status."""
        event = EventFactory(is_active=True)
        group = GroupFactory()
        
        # Create event status for group
        event_status = GroupEventStatusFactory(
            event=event,
            group=group,
            current_distance_km=Decimal('10.00000')
        )
        
        # Call update_group_hierarchy_progress
        delta_km = Decimal('5.00000')
        update_group_hierarchy_progress(group, delta_km)
        
        # Refresh from database
        event_status.refresh_from_db()
        
        # Check that kilometers were added
        assert float(event_status.current_distance_km) == 15.0
    
    def test_update_group_hierarchy_progress_skips_inactive_event(self):
        """Test that update_group_hierarchy_progress skips inactive events."""
        event = EventFactory(is_active=False)  # Inactive event
        group = GroupFactory()
        
        # Create event status for group
        event_status = GroupEventStatusFactory(
            event=event,
            group=group,
            current_distance_km=Decimal('10.00000')
        )
        
        # Call update_group_hierarchy_progress
        delta_km = Decimal('5.00000')
        update_group_hierarchy_progress(group, delta_km)
        
        # Refresh from database
        event_status.refresh_from_db()
        
        # Check that kilometers were NOT added (event is inactive)
        assert float(event_status.current_distance_km) == 10.0
    
    def test_update_group_hierarchy_progress_handles_multiple_events(self):
        """Test that update_group_hierarchy_progress updates all active events for a group."""
        event1 = EventFactory(is_active=True, name='Event 1')
        event2 = EventFactory(is_active=True, name='Event 2')
        event3 = EventFactory(is_active=False, name='Event 3')  # Inactive
        group = GroupFactory()
        
        # Create event statuses for all events
        status1 = GroupEventStatusFactory(
            event=event1,
            group=group,
            current_distance_km=Decimal('10.00000')
        )
        status2 = GroupEventStatusFactory(
            event=event2,
            group=group,
            current_distance_km=Decimal('20.00000')
        )
        status3 = GroupEventStatusFactory(
            event=event3,
            group=group,
            current_distance_km=Decimal('30.00000')
        )
        
        # Call update_group_hierarchy_progress
        delta_km = Decimal('5.00000')
        update_group_hierarchy_progress(group, delta_km)
        
        # Refresh from database
        status1.refresh_from_db()
        status2.refresh_from_db()
        status3.refresh_from_db()
        
        # Check that kilometers were added to active events only
        assert float(status1.current_distance_km) == 15.0  # Active event
        assert float(status2.current_distance_km) == 25.0  # Active event
        assert float(status3.current_distance_km) == 30.0  # Inactive event - no change
    
    def test_update_group_hierarchy_progress_with_leaf_group(self):
        """Test that update_group_hierarchy_progress works with leaf groups."""
        event = EventFactory(is_active=True)
        parent_group = GroupFactory(parent=None)
        leaf_group = GroupFactory(parent=parent_group)
        
        # Create event status only for leaf group (not parent)
        event_status = GroupEventStatusFactory(
            event=event,
            group=leaf_group,
            current_distance_km=Decimal('10.00000')
        )
        
        # Call update_group_hierarchy_progress for leaf group
        delta_km = Decimal('2.50000')
        update_group_hierarchy_progress(leaf_group, delta_km)
        
        # Refresh from database
        event_status.refresh_from_db()
        
        # Check that kilometers were added
        assert float(event_status.current_distance_km) == 12.5
        
        # Check that parent group has no event status (should not be updated)
        parent_status = GroupEventStatus.objects.filter(event=event, group=parent_group).first()
        assert parent_status is None
    
    def test_update_group_hierarchy_progress_with_reached_goal(self):
        """Test that update_group_hierarchy_progress still updates events even if travel goal is reached."""
        from api.models import TravelTrack, GroupTravelStatus
        
        # Create event and group
        event = EventFactory(is_active=True)
        group = GroupFactory()
        
        # Create event status
        event_status = GroupEventStatusFactory(
            event=event,
            group=group,
            current_distance_km=Decimal('10.00000')
        )
        
        # Create travel track and status with goal already reached
        track = TravelTrackFactory(
            total_length_km=Decimal('2.00000'),
            is_active=True
        )
        travel_status = GroupTravelStatusFactory(
            group=group,
            track=track,
            current_travel_distance=Decimal('2.00000')  # Goal reached
        )
        
        # Manually set the travel distance to ensure it's at the goal
        travel_status.current_travel_distance = Decimal('2.00000')
        travel_status.save()
        
        # Call update_group_hierarchy_progress - should still update events
        delta_km = Decimal('1.00000')
        update_group_hierarchy_progress(group, delta_km)
        
        # Refresh from database
        event_status.refresh_from_db()
        travel_status.refresh_from_db()
        
        # Check that event kilometers were added (even though goal is reached)
        assert float(event_status.current_distance_km) == 11.0
        
        # Check that travel distance was NOT increased (goal already reached)
        # The function should skip travel distance update but still update events
        assert float(travel_status.current_travel_distance) == 2.0
    
    def test_get_all_subgroup_ids(self):
        """Test get_all_subgroup_ids recursive function."""
        top_group = GroupFactory(parent=None, name='Top')
        child1 = GroupFactory(parent=top_group, name='Child1')
        child2 = GroupFactory(parent=top_group, name='Child2')
        grandchild = GroupFactory(parent=child1, name='Grandchild')
        
        result = get_all_subgroup_ids(top_group)
        
        # Should include top_group, child1, child2, and grandchild
        assert top_group.id in result
        assert child1.id in result
        assert child2.id in result
        assert grandchild.id in result
        assert len(result) == 4
