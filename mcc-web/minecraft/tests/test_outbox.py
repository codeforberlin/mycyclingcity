# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_outbox.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Minecraft outbox service.

Tests cover:
- queue_player_coins_update
- queue_full_sync
"""

import pytest
from django.utils import timezone

from minecraft.models import MinecraftOutboxEvent
from minecraft.services.outbox import queue_player_coins_update, queue_full_sync
from api.tests.conftest import CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestOutboxService:
    """Tests for outbox service functions."""
    
    def test_queue_player_coins_update(self):
        """Test queueing a player coins update event."""
        event = queue_player_coins_update(
            player="testplayer",
            coins_total=1000,
            coins_spendable=500,
            reason="test_reason",
        )
        
        assert event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.payload["player"] == "testplayer"
        assert event.payload["coins_total"] == 1000
        assert event.payload["coins_spendable"] == 500
        assert event.payload["reason"] == "test_reason"
        assert event.payload["spendable_action"] == "set"
        assert "queued_at" in event.payload
    
    def test_queue_player_coins_update_with_delta(self):
        """Test queueing a player coins update with spendable delta."""
        event = queue_player_coins_update(
            player="testplayer",
            coins_total=1000,
            coins_spendable=500,
            reason="test_reason",
            spendable_action="add",
            spendable_delta=100,
        )
        
        assert event.payload["spendable_action"] == "add"
        assert event.payload["spendable_delta"] == 100
    
    def test_queue_player_coins_update_coerces_to_int(self):
        """Test that coins values are coerced to int."""
        event = queue_player_coins_update(
            player="testplayer",
            coins_total=1000.7,  # Float
            coins_spendable=500.3,  # Float
            reason="test_reason",
        )
        
        assert isinstance(event.payload["coins_total"], int)
        assert isinstance(event.payload["coins_spendable"], int)
        assert event.payload["coins_total"] == 1000
        assert event.payload["coins_spendable"] == 500
    
    def test_queue_full_sync(self):
        """Test queueing a full sync event."""
        event = queue_full_sync(reason="test_sync")
        
        assert event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL
        assert event.status == MinecraftOutboxEvent.STATUS_PENDING
        assert event.payload["reason"] == "test_sync"
        assert "queued_at" in event.payload
    
    def test_queue_player_coins_update_creates_event_in_db(self):
        """Test that queue_player_coins_update creates event in database."""
        initial_count = MinecraftOutboxEvent.objects.count()
        
        queue_player_coins_update(
            player="testplayer",
            coins_total=1000,
            coins_spendable=500,
            reason="test",
        )
        
        assert MinecraftOutboxEvent.objects.count() == initial_count + 1
        event = MinecraftOutboxEvent.objects.latest("created_at")
        assert event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS
