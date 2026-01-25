# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Kiosk views.

Tests cover:
- kiosk_playlist_page view
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.http import Http404

from kiosk.models import KioskDevice, KioskPlaylistEntry
from api.tests.conftest import EventFactory, GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestKioskViews:
    """Tests for Kiosk views."""
    
    def test_kiosk_playlist_page_active_device_with_entries(self):
        """Test kiosk playlist page for active device with playlist entries."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            is_active=True,
        )
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            order=1,
            is_active=True,
        )
        
        client = Client()
        response = client.get(f'/de/kiosk/playlist/{device.uid}/')
        
        assert response.status_code == 200
        assert 'device' in response.context
        assert response.context['device'] == device
    
    def test_kiosk_playlist_page_inactive_device(self):
        """Test kiosk playlist page for inactive device shows maintenance."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            is_active=False,
        )
        
        client = Client()
        response = client.get(f'/de/kiosk/playlist/{device.uid}/')
        
        assert response.status_code == 503
        assert 'device_name' in response.context
        assert response.context['device_name'] == device.name
    
    def test_kiosk_playlist_page_no_playlist_entries(self):
        """Test kiosk playlist page for device without active entries."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            is_active=True,
        )
        # No playlist entries
        
        client = Client()
        response = client.get(f'/de/kiosk/playlist/{device.uid}/')
        
        assert response.status_code == 200
        assert 'device_name' in response.context
        assert 'admin_url' in response.context
    
    def test_kiosk_playlist_page_only_inactive_entries(self):
        """Test kiosk playlist page when only inactive entries exist."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            is_active=True,
        )
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            order=1,
            is_active=False,  # Inactive entry
        )
        
        client = Client()
        response = client.get(f'/de/kiosk/playlist/{device.uid}/')
        
        # Should show no playlist page since no active entries
        assert response.status_code == 200
        assert 'device_name' in response.context
    
    def test_kiosk_playlist_page_device_not_found(self):
        """Test kiosk playlist page for non-existent device raises 404."""
        client = Client()
        
        response = client.get('/de/kiosk/playlist/nonexistent-uid/')
        assert response.status_code == 404
    
    def test_kiosk_playlist_page_multiple_entries(self):
        """Test kiosk playlist page with multiple playlist entries."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            is_active=True,
        )
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            order=1,
            is_active=True,
        )
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="eventboard",
            order=2,
            is_active=True,
        )
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="map",
            order=3,
            is_active=True,
        )
        
        client = Client()
        response = client.get(f'/de/kiosk/playlist/{device.uid}/')
        
        assert response.status_code == 200
        assert response.context['device'].playlist_entries.filter(is_active=True).count() == 3
