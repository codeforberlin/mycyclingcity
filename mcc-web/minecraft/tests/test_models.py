# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_models.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Minecraft models.

Tests cover:
- MinecraftOutboxEvent model methods
- MinecraftPlayerScoreboardSnapshot model
- MinecraftWorkerState singleton pattern
"""

import pytest
from django.utils import timezone
from datetime import timedelta

from minecraft.models import (
    MinecraftOutboxEvent,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftWorkerState,
)
from api.tests.conftest import CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestMinecraftOutboxEvent:
    """Tests for MinecraftOutboxEvent model."""
    
    def test_create_update_player_coins_event(self):
        """Test creating an UPDATE_PLAYER_COINS event."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "testplayer", "coins_total": 100, "coins_spendable": 50},
        )
        
        assert event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.attempts == 0
        assert event.payload["player"] == "testplayer"
        assert event.payload["coins_total"] == 100
    
    def test_create_sync_all_event(self):
        """Test creating a SYNC_ALL event."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_SYNC_ALL,
            payload={"reason": "test_sync"},
        )
        
        assert event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.payload["reason"] == "test_sync"
    
    def test_mark_done(self):
        """Test marking an event as done."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "testplayer"},
            status=MinecraftOutboxEvent.STATUS_PROCESSING,
            last_error="Some error",
        )
        
        event.mark_done()
        event.refresh_from_db()
        
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        assert event.processed_at is not None
        assert event.last_error == ""
    
    def test_mark_failed(self):
        """Test marking an event as failed."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "testplayer"},
        )
        
        error_message = "Connection failed"
        event.mark_failed(error_message)
        event.refresh_from_db()
        
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
        assert event.processed_at is not None
        assert error_message in event.last_error
    
    def test_mark_failed_truncates_long_error(self):
        """Test that mark_failed truncates very long error messages."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "testplayer"},
        )
        
        long_error = "x" * 10000
        event.mark_failed(long_error)
        event.refresh_from_db()
        
        assert len(event.last_error) <= 5000
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
    
    def test_mark_processing(self):
        """Test marking an event as processing."""
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={"player": "testplayer"},
            attempts=2,
        )
        
        event.mark_processing()
        event.refresh_from_db()
        
        assert event.status == MinecraftOutboxEvent.STATUS_PROCESSING
        assert event.attempts == 3
    
    def test_ordering(self):
        """Test that events are ordered by created_at descending."""
        event1 = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={},
        )
        event2 = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={},
        )
        
        events = list(MinecraftOutboxEvent.objects.all())
        assert events[0].id == event2.id
        assert events[1].id == event1.id


@pytest.mark.unit
@pytest.mark.django_db
class TestMinecraftPlayerScoreboardSnapshot:
    """Tests for MinecraftPlayerScoreboardSnapshot model."""
    
    def test_create_snapshot(self):
        """Test creating a scoreboard snapshot."""
        cyclist = CyclistFactory(mc_username="testplayer")
        
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="testplayer",
            cyclist=cyclist,
            coins_total=1000,
            coins_spendable=500,
            source="rcon",
        )
        
        assert snapshot.player_name == "testplayer"
        assert snapshot.cyclist == cyclist
        assert snapshot.coins_total == 1000
        assert snapshot.coins_spendable == 500
        assert snapshot.source == "rcon"
    
    def test_snapshot_str_representation(self):
        """Test string representation of snapshot."""
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="testplayer",
            coins_total=1000,
            coins_spendable=500,
        )
        
        assert str(snapshot) == "testplayer (500/1000)"
    
    def test_unique_together_player_name(self):
        """Test that player_name is unique."""
        MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="testplayer",
            coins_total=1000,
            coins_spendable=500,
        )
        
        # Creating another with same player_name should update, not create
        snapshot2 = MinecraftPlayerScoreboardSnapshot.objects.update_or_create(
            player_name="testplayer",
            defaults={"coins_total": 2000, "coins_spendable": 1000},
        )[0]
        
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 1
        assert snapshot2.coins_total == 2000
        assert snapshot2.coins_spendable == 1000
    
    def test_snapshot_without_cyclist(self):
        """Test creating a snapshot without a cyclist."""
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="orphanplayer",
            coins_total=100,
            coins_spendable=50,
        )
        
        assert snapshot.cyclist is None
        assert snapshot.player_name == "orphanplayer"


@pytest.mark.unit
@pytest.mark.django_db
class TestMinecraftWorkerState:
    """Tests for MinecraftWorkerState model."""
    
    def test_get_state_creates_singleton(self):
        """Test that get_state creates a singleton instance."""
        # Clear any existing state
        MinecraftWorkerState.objects.all().delete()
        
        # Get state (should create new instance)
        state1 = MinecraftWorkerState.get_state()
        assert state1.pk == 1
        assert state1.is_running is False
        
        # Get state again (should return same instance)
        state2 = MinecraftWorkerState.get_state()
        assert state2.pk == state1.pk
        assert state2.is_running == state1.is_running
        
        # Verify only one instance exists
        assert MinecraftWorkerState.objects.count() == 1
    
    def test_worker_state_fields(self):
        """Test worker state fields."""
        state = MinecraftWorkerState.get_state()
        
        state.is_running = True
        state.pid = "12345"
        state.started_at = timezone.now()
        state.last_heartbeat = timezone.now()
        state.last_error = "Test error"
        state.save()
        
        state.refresh_from_db()
        assert state.is_running is True
        assert state.pid == "12345"
        assert state.started_at is not None
        assert state.last_heartbeat is not None
        assert state.last_error == "Test error"
