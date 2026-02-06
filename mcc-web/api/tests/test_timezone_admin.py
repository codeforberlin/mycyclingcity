# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_timezone_admin.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Tests for timezone handling in Django Admin for TravelTrack model.

This test verifies that:
1. DateTime values entered in local timezone are correctly saved as UTC
2. DateTime values loaded from database are correctly displayed in local timezone
3. The timezone middleware correctly activates the user's timezone
"""

import pytest
from decimal import Decimal
from django.utils import timezone as tz_utils
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from api.models import TravelTrack
from api.tests.conftest import TravelTrackFactory
from mgmt.admin import TravelTrackAdmin, TravelTrackAdminForm


User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestTimezoneAdmin:
    """Tests for timezone handling in Django Admin."""
    
    def test_timezone_save_and_load_cycle(self, db):
        """
        Test that datetime values are correctly saved and loaded with timezone conversion.
        
        Scenario:
        1. User in Europe/Berlin timezone enters 15:00 local time via Admin form
        2. This should be saved as 14:00 UTC (winter time, UTC+1)
        3. When loaded, it should be displayed as 15:00 local time again
        
        This test uses the Admin form to simulate the real user flow.
        """
        # Create a test user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create a TravelTrack object
        track = TravelTrackFactory(
            name='Test Timezone Track',
            total_length_km=Decimal('50.00000'),
            is_active=True
        )
        
        # Activate Europe/Berlin timezone (simulating middleware)
        berlin_tz = ZoneInfo('Europe/Berlin')
        tz_utils.activate(berlin_tz)
        
        try:
            # Simulate user entering 15:00 local time (Berlin) via Admin form
            # This is 14:00 UTC in winter (UTC+1)
            local_time = datetime(2026, 2, 6, 15, 0, 0)  # 15:00 local time
            expected_utc = datetime(2026, 2, 6, 14, 0, 0)  # 14:00 UTC
            
            # Make the local time timezone-aware (as AdminSplitDateTime would provide)
            local_time_aware = tz_utils.make_aware(local_time, berlin_tz)
            
            # Create form with the timezone-aware datetime (simulating Admin form submission)
            request = RequestFactory().post('/admin/api/traveltrack/1/change/')
            request.user = user
            
            form_data = {
                'name': track.name,
                'total_length_km': str(track.total_length_km),
                'is_active': True,
                'is_visible_on_map': True,
                'auto_start': False,
                'end_time': local_time_aware,  # Timezone-aware datetime from form
            }
            
            form = TravelTrackAdminForm(data=form_data, instance=track, request=request)
            
            # The form should be valid
            assert form.is_valid(), f"Form errors: {form.errors}"
            
            # Save via Admin (this will call save_model with timezone handling)
            admin = TravelTrackAdmin(TravelTrack, None)
            admin.save_model(request, track, form, change=True)
            
            # Reload from database
            track.refresh_from_db()
            
            # Check that the time in DB is correct (should be 14:00 UTC)
            # Django will return it as timezone-aware UTC
            db_time_utc = track.end_time
            if db_time_utc.tzinfo is None:
                # Make it aware as UTC
                db_time_utc = tz_utils.make_aware(db_time_utc, dt_timezone.utc)
            
            # Convert to Berlin timezone for display
            db_time_berlin = db_time_utc.astimezone(berlin_tz)
            
            # Verify: The time in DB should be 14:00 UTC
            assert db_time_utc.hour == 14, f"Expected 14:00 UTC in DB, got {db_time_utc.hour}:{db_time_utc.minute:02d} UTC"
            assert db_time_utc.minute == 0
            
            # Verify: When displayed in Berlin timezone, it should be 15:00
            assert db_time_berlin.hour == 15, f"Expected 15:00 Berlin time, got {db_time_berlin.hour}:{db_time_berlin.minute:02d} Berlin time"
            assert db_time_berlin.minute == 0
            
        finally:
            # Always deactivate timezone after test
            tz_utils.deactivate()
    
    def test_admin_form_timezone_conversion(self, db):
        """
        Test that TravelTrackAdminForm correctly converts datetime values.
        
        This test simulates the form processing:
        1. Form receives timezone-aware datetime in local timezone
        2. Form converts it to naive UTC in clean()
        3. Admin saves it correctly
        """
        # Create a test user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create a TravelTrack object
        track = TravelTrackFactory(
            name='Test Form Timezone Track',
            total_length_km=Decimal('50.00000'),
            is_active=True
        )
        
        # Activate Europe/Berlin timezone
        berlin_tz = ZoneInfo('Europe/Berlin')
        tz_utils.activate(berlin_tz)
        
        try:
            # Simulate form data: user enters 15:00 local time
            local_time = datetime(2026, 2, 6, 15, 0, 0)
            local_time_aware = tz_utils.make_aware(local_time, berlin_tz)
            
            # Create form with the timezone-aware datetime
            request = RequestFactory().get('/admin/api/traveltrack/1/change/')
            request.user = user
            
            form_data = {
                'name': track.name,
                'total_length_km': str(track.total_length_km),
                'is_active': True,
                'is_visible_on_map': True,
                'auto_start': False,
                'end_time': local_time_aware,  # Timezone-aware datetime
            }
            
            form = TravelTrackAdminForm(data=form_data, instance=track, request=request)
            
            # The form should be valid
            assert form.is_valid(), f"Form errors: {form.errors}"
            
            # Get cleaned data
            cleaned_data = form.cleaned_data
            
            # The cleaned end_time should be naive UTC
            cleaned_end_time = cleaned_data.get('end_time')
            assert cleaned_end_time is not None, "end_time should be in cleaned_data"
            assert cleaned_end_time.tzinfo is None, "end_time should be naive after clean()"
            
            # Verify it's 14:00 UTC (15:00 Berlin = 14:00 UTC in winter)
            assert cleaned_end_time.hour == 14, f"Expected 14:00 UTC, got {cleaned_end_time.hour}:{cleaned_end_time.minute:02d}"
            assert cleaned_end_time.minute == 0
            
        finally:
            tz_utils.deactivate()
    
    def test_timezone_middleware_simulation(self, db):
        """
        Test that simulates the full flow with timezone middleware.
        
        This test simulates:
        1. Middleware activates timezone from cookie
        2. User views form - times are displayed in local timezone
        3. User saves form - times are converted to UTC
        4. User views form again - times are displayed in local timezone
        """
        # Create a test user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create a TravelTrack with a UTC time in the database
        # This simulates an existing object with UTC time
        # We need to save it directly in the DB to bypass Django's timezone conversion
        utc_time = datetime(2026, 2, 6, 14, 0, 0)  # 14:00 UTC
        track = TravelTrackFactory(
            name='Test Middleware Track',
            total_length_km=Decimal('50.00000'),
            is_active=True
        )
        
        # Save the initial UTC time directly in the database to bypass Django's conversion
        from django.db import connection
        with connection.cursor() as cursor:
            # Django uses %s as placeholder for all databases (it handles conversion internally)
            cursor.execute(
                "UPDATE api_traveltrack SET end_time = %s WHERE id = %s",
                [utc_time, track.pk]
            )
        track.refresh_from_db()
        
        # Activate Europe/Berlin timezone (simulating middleware)
        berlin_tz = ZoneInfo('Europe/Berlin')
        tz_utils.activate(berlin_tz)
        
        try:
            # Simulate loading the form (get_form)
            # The time should be converted to Berlin timezone for display
            track.refresh_from_db()
            
            # Get the time from database (Django returns it as timezone-aware UTC)
            db_time = track.end_time
            if db_time.tzinfo is None:
                db_time = tz_utils.make_aware(db_time, dt_timezone.utc)
            
            # Convert to Berlin timezone (simulating what get_form does)
            display_time = db_time.astimezone(berlin_tz)
            
            # Verify: 14:00 UTC should be displayed as 15:00 Berlin time
            assert display_time.hour == 15, f"Expected 15:00 Berlin time, got {display_time.hour}:{display_time.minute:02d}"
            assert display_time.minute == 0
            
            # Now simulate saving a new time: user enters 16:00 Berlin time via Admin form
            new_local_time = datetime(2026, 2, 6, 16, 0, 0)  # 16:00 Berlin
            new_local_time_aware = tz_utils.make_aware(new_local_time, berlin_tz)
            
            # Create form with the new timezone-aware datetime (simulating Admin form submission)
            request = RequestFactory().post('/admin/api/traveltrack/1/change/')
            request.user = user
            
            form_data = {
                'name': track.name,
                'total_length_km': str(track.total_length_km),
                'is_active': True,
                'is_visible_on_map': True,
                'auto_start': False,
                'end_time': new_local_time_aware,  # Timezone-aware datetime from form
            }
            
            form = TravelTrackAdminForm(data=form_data, instance=track, request=request)
            
            # The form should be valid
            assert form.is_valid(), f"Form errors: {form.errors}"
            
            # Save via Admin (this will call save_model with timezone handling)
            admin = TravelTrackAdmin(TravelTrack, None)
            admin.save_model(request, track, form, change=True)
            
            # Reload and verify
            track.refresh_from_db()
            saved_time = track.end_time
            if saved_time.tzinfo is None:
                saved_time = tz_utils.make_aware(saved_time, dt_timezone.utc)
            
            # Should be 15:00 UTC (16:00 Berlin = 15:00 UTC)
            assert saved_time.hour == 15, f"Expected 15:00 UTC in DB, got {saved_time.hour}:{saved_time.minute:02d} UTC"
            assert saved_time.minute == 0
            
            # When displayed in Berlin timezone, should be 16:00
            display_time_after_save = saved_time.astimezone(berlin_tz)
            assert display_time_after_save.hour == 16, f"Expected 16:00 Berlin time, got {display_time_after_save.hour}:{display_time_after_save.minute:02d}"
            assert display_time_after_save.minute == 0
            
        finally:
            tz_utils.deactivate()
