# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Kiosk models.

Tests cover:
- KioskDevice model methods
- KioskPlaylistEntry model
"""

import pytest
from django.core.exceptions import ValidationError

from kiosk.models import KioskDevice, KioskPlaylistEntry
from api.tests.conftest import GroupFactory, EventFactory, TravelTrackFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestKioskDevice:
    """Tests for KioskDevice model."""
    
    def test_create_device(self):
        """Test creating a kiosk device."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            brightness=75,
            is_active=True,
        )
        
        assert device.name == "Test Kiosk"
        assert device.uid == "kiosk-001"
        assert device.brightness == 75
        assert device.is_active is True
        assert device.command_queue == []
    
    def test_device_str_representation(self):
        """Test string representation of device."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        assert str(device) == "Test Kiosk"
    
    def test_device_unique_uid(self):
        """Test that UID must be unique."""
        KioskDevice.objects.create(name="Kiosk 1", uid="unique-uid")
        
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            KioskDevice.objects.create(name="Kiosk 2", uid="unique-uid")
    
    def test_add_command(self):
        """Test adding a command to the queue."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        device.add_command("RELOAD")
        device.refresh_from_db()
        
        assert "RELOAD" in device.command_queue
        assert len(device.command_queue) == 1
    
    def test_add_multiple_commands(self):
        """Test adding multiple commands."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        device.add_command("RELOAD")
        device.add_command("SET_BRIGHTNESS:50")
        device.refresh_from_db()
        
        assert len(device.command_queue) == 2
        assert device.command_queue[0] == "RELOAD"
        assert device.command_queue[1] == "SET_BRIGHTNESS:50"
    
    def test_clear_commands(self):
        """Test clearing all commands."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        device.add_command("RELOAD")
        device.add_command("SET_BRIGHTNESS:50")
        device.clear_commands()
        device.refresh_from_db()
        
        assert device.command_queue == []
    
    def test_pop_command(self):
        """Test popping a command from the queue."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        device.add_command("RELOAD")
        device.add_command("SET_BRIGHTNESS:50")
        
        command = device.pop_command()
        device.refresh_from_db()
        
        assert command == "RELOAD"
        assert len(device.command_queue) == 1
        assert device.command_queue[0] == "SET_BRIGHTNESS:50"
    
    def test_pop_command_empty_queue(self):
        """Test popping from empty queue returns None."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        command = device.pop_command()
        
        assert command is None
    
    def test_brightness_validation(self):
        """Test brightness validation (0-100)."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
            brightness=50,
        )
        
        # Valid values
        device.brightness = 0
        device.save()
        device.brightness = 100
        device.save()
        
        # Invalid values should raise ValidationError
        device.brightness = -1
        with pytest.raises(ValidationError):
            device.full_clean()
        
        device.brightness = 101
        with pytest.raises(ValidationError):
            device.full_clean()


@pytest.mark.unit
@pytest.mark.django_db
class TestKioskPlaylistEntry:
    """Tests for KioskPlaylistEntry model."""
    
    def test_create_playlist_entry(self):
        """Test creating a playlist entry."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        entry = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            display_duration=30,
            order=1,
            is_active=True,
        )
        
        assert entry.device == device
        assert entry.view_type == "leaderboard"
        assert entry.display_duration == 30
        assert entry.order == 1
        assert entry.is_active is True
    
    def test_playlist_entry_with_event_filter(self):
        """Test playlist entry with event filter."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        event = EventFactory()
        
        entry = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="eventboard",
            event_filter=event,
            order=1,
        )
        
        assert entry.event_filter == event
    
    def test_playlist_entry_with_group_filter(self):
        """Test playlist entry with group filter."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        group = GroupFactory()
        
        entry = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            group_filter=group,
            order=1,
        )
        
        assert entry.group_filter == group
    
    def test_playlist_entry_with_track_filter(self):
        """Test playlist entry with track filter."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        track1 = TravelTrackFactory()
        track2 = TravelTrackFactory()
        
        entry = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="map",
            order=1,
        )
        entry.track_filter.add(track1, track2)
        
        assert entry.track_filter.count() == 2
        assert track1 in entry.track_filter.all()
        assert track2 in entry.track_filter.all()
    
    def test_playlist_entry_unique_together_device_order(self):
        """Test that device and order combination must be unique."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            order=1,
        )
        
        # Creating another entry with same device and order should fail
        with pytest.raises(Exception):  # IntegrityError
            KioskPlaylistEntry.objects.create(
                device=device,
                view_type="eventboard",
                order=1,
            )
    
    def test_playlist_entry_ordering(self):
        """Test that entries are ordered by device, order, id."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        entry1 = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            order=2,
        )
        entry2 = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="eventboard",
            order=1,
        )
        entry3 = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="map",
            order=3,
        )
        
        entries = list(KioskPlaylistEntry.objects.filter(device=device))
        assert entries[0] == entry2  # order=1
        assert entries[1] == entry1  # order=2
        assert entries[2] == entry3  # order=3
    
    def test_playlist_entry_display_duration_validation(self):
        """Test display duration validation (minimum 1)."""
        device = KioskDevice.objects.create(
            name="Test Kiosk",
            uid="kiosk-001",
        )
        
        entry = KioskPlaylistEntry.objects.create(
            device=device,
            view_type="leaderboard",
            display_duration=1,
            order=1,
        )
        
        # Valid value
        entry.display_duration = 30
        entry.save()
        
        # Invalid value should raise ValidationError
        entry.display_duration = 0
        with pytest.raises(ValidationError):
            entry.full_clean()
