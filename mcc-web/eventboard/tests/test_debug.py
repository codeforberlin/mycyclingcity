# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_debug.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Debug tests for Eventboard to identify why active cyclists are not detected.
These tests check the actual database state.
"""

import pytest
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from api.models import Cyclist, CyclistDeviceCurrentMileage, Event, GroupEventStatus, Group
from eventboard.views import eventboard_ticker
from eventboard.utils import get_active_cyclists_for_eventboard


@pytest.mark.unit
@pytest.mark.django_db
class TestEventboardDebug:
    """Debug tests to identify why active cyclists are not detected."""
    
    def test_debug_all_cyclists(self):
        """Debug: Check all cyclists in database."""
        all_cyclists = Cyclist.objects.all()
        print(f"\n=== DEBUG: Total cyclists in DB: {all_cyclists.count()} ===")
        
        for cyclist in all_cyclists[:10]:  # First 10
            print(f"  Cyclist: {cyclist.user_id}, is_visible={cyclist.is_visible}, last_active={cyclist.last_active}")
    
    def test_debug_active_cyclists_criteria(self):
        """Debug: Check which cyclists meet the active criteria."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        print(f"\n=== DEBUG: Active cutoff time: {active_cutoff} ===")
        print(f"Current time: {now}")
        
        # Check all visible cyclists
        visible_cyclists = Cyclist.objects.filter(is_visible=True)
        print(f"Visible cyclists: {visible_cyclists.count()}")
        
        # Check cyclists with last_active
        with_last_active = visible_cyclists.filter(last_active__isnull=False)
        print(f"Cyclists with last_active: {with_last_active.count()}")
        
        # Check active cyclists (last_active >= cutoff)
        active_by_time = with_last_active.filter(last_active__gte=active_cutoff)
        print(f"Cyclists active by time (last_active >= {active_cutoff}): {active_by_time.count()}")
        
        for cyclist in active_by_time[:5]:
            print(f"  Active cyclist: {cyclist.user_id}, last_active={cyclist.last_active}")
            try:
                session = cyclist.cyclistdevicecurrentmileage
                print(f"    Session exists: cumulative_mileage={session.cumulative_mileage}")
            except CyclistDeviceCurrentMileage.DoesNotExist:
                print(f"    No session (CyclistDeviceCurrentMileage)")
    
    def test_debug_sessions(self):
        """Debug: Check all active sessions."""
        all_sessions = CyclistDeviceCurrentMileage.objects.all()
        print(f"\n=== DEBUG: Total sessions in DB: {all_sessions.count()} ===")
        
        for session in all_sessions[:10]:
            cyclist = session.cyclist
            print(f"  Session: cyclist={cyclist.user_id}, "
                  f"is_visible={cyclist.is_visible}, "
                  f"last_active={cyclist.last_active}, "
                  f"cumulative_mileage={session.cumulative_mileage}")
    
    def test_debug_eventboard_ticker_query(self):
        """Debug: Test the actual query used by eventboard_ticker."""
        now = timezone.now()
        active_cutoff = now - timedelta(seconds=60)
        
        from api.models import Cyclist, CyclistDeviceCurrentMileage
        
        base_cyclists = Cyclist.objects.filter(
            is_visible=True,
            last_active__isnull=False,
            last_active__gte=active_cutoff
        ).select_related('cyclistdevicecurrentmileage').prefetch_related('groups')
        
        print(f"\n=== DEBUG: Base query result: {base_cyclists.count()} cyclists ===")
        
        for cyclist in base_cyclists[:5]:
            print(f"  Cyclist: {cyclist.user_id}")
            print(f"    last_active: {cyclist.last_active}")
            print(f"    is_visible: {cyclist.is_visible}")
            try:
                session = cyclist.cyclistdevicecurrentmileage
                print(f"    session_km: {session.cumulative_mileage}")
            except CyclistDeviceCurrentMileage.DoesNotExist:
                print(f"    session_km: No session")
            groups = cyclist.groups.all()
            print(f"    groups: {[g.name for g in groups]}")
    
    def test_debug_eventboard_ticker_with_event(self):
        """Debug: Test eventboard_ticker with a specific event."""
        # Get first event
        event = Event.objects.first()
        if not event:
            print("\n=== DEBUG: No events in database ===")
            return
        
        print(f"\n=== DEBUG: Testing with event_id={event.id} ({event.name}) ===")
        
        # Get groups in event
        event_groups = GroupEventStatus.objects.filter(event=event).values_list('group_id', flat=True)
        print(f"Groups in event: {list(event_groups)}")
        
        # Test the utility function
        result = get_active_cyclists_for_eventboard(event_id=event.id)
        print(f"Active cyclists for event: {result.count()}")
        
        for cyclist in result[:5]:
            print(f"  Cyclist: {cyclist.user_id}, groups: {[g.id for g in cyclist.groups.all()]}")
        
        # Test the view
        from django.test import RequestFactory
        rf = RequestFactory()
        request = rf.get(f'/de/eventboard/ticker/?event_id={event.id}')
        response = eventboard_ticker(request)
        
        print(f"View response status: {response.status_code}")
        if hasattr(response, 'context'):
            active_cyclists = response.context.get('active_cyclists', [])
            print(f"Active cyclists in response: {len(active_cyclists)}")
            for cyclist_data in active_cyclists[:5]:
                print(f"  {cyclist_data}")
