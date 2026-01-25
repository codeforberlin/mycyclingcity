# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_worker.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Minecraft worker service.

Tests cover:
- process_next_event
- _handle_update_player_coins
- _handle_sync_all
"""

import pytest
from unittest.mock import patch, MagicMock
from django.conf import settings

from minecraft.models import MinecraftOutboxEvent
from minecraft.services.worker import process_next_event
from api.tests.conftest import CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestWorkerService:
    """Tests for worker service functions."""
    
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_scoreboards')
    @patch('minecraft.services.worker.update_snapshot')
    def test_process_update_player_coins_event(self, mock_update_snapshot, mock_ensure, mock_rcon):
        """Test processing an UPDATE_PLAYER_COINS event."""
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None
        
        cyclist = CyclistFactory(mc_username="testplayer")
        
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={
                "player": "testplayer",
                "coins_total": 1000,
                "coins_spendable": 500,
                "reason": "test",
            },
        )
        
        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()
        
        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        assert mock_rcon.set_player_score.call_count == 2
        mock_update_snapshot.assert_called_once()
    
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_scoreboards')
    @patch('minecraft.services.worker.update_snapshot')
    def test_process_update_player_coins_with_add_action(self, mock_update_snapshot, mock_ensure, mock_rcon):
        """Test processing UPDATE_PLAYER_COINS with add action."""
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None
        mock_rcon.add_player_score.return_value = None
        
        cyclist = CyclistFactory(mc_username="testplayer")
        
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={
                "player": "testplayer",
                "coins_total": 1000,
                "coins_spendable": 500,
                "spendable_action": "add",
                "spendable_delta": 100,
                "reason": "test",
            },
        )
        
        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()
        
        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        # Should call set_player_score for total, and add_player_score for spendable
        assert mock_rcon.set_player_score.call_count == 1
        assert mock_rcon.add_player_score.call_count == 1
    
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_scoreboards')
    @patch('minecraft.services.worker.update_snapshot')
    def test_process_sync_all_event(self, mock_update_snapshot, mock_ensure, mock_rcon):
        """Test processing a SYNC_ALL event."""
        mock_ensure.return_value = None
        mock_rcon.set_player_score.return_value = None
        
        cyclist1 = CyclistFactory(mc_username="player1", coins_total=1000, coins_spendable=500)
        cyclist2 = CyclistFactory(mc_username="player2", coins_total=2000, coins_spendable=1000)
        
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_SYNC_ALL,
            payload={"reason": "test_sync"},
        )
        
        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()
        
        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_DONE
        # Should call set_player_score twice per player (total and spendable)
        assert mock_rcon.set_player_score.call_count == 4
        assert mock_update_snapshot.call_count == 2
    
    def test_process_next_event_no_pending(self):
        """Test process_next_event when no pending events exist."""
        result = process_next_event()
        assert result is False
    
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_scoreboards')
    def test_process_next_event_handles_error(self, mock_ensure, mock_rcon):
        """Test that process_next_event marks event as failed on error."""
        mock_ensure.return_value = None
        mock_rcon.set_player_score.side_effect = Exception("Connection failed")
        
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={
                "player": "testplayer",
                "coins_total": 1000,
                "coins_spendable": 500,
                "reason": "test",
            },
        )
        
        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()
        
        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
        assert "Connection failed" in event.last_error
        assert event.attempts == 1
    
    @patch('minecraft.services.worker.rcon_client')
    @patch('minecraft.services.worker.ensure_scoreboards')
    @patch('minecraft.services.worker.update_snapshot')
    def test_process_update_player_coins_missing_player(self, mock_update_snapshot, mock_ensure, mock_rcon):
        """Test that missing player in payload raises error."""
        mock_ensure.return_value = None
        
        event = MinecraftOutboxEvent.objects.create(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS,
            payload={
                "coins_total": 1000,
                "coins_spendable": 500,
            },
        )
        
        with patch('minecraft.services.worker.rcon_client', mock_rcon):
            result = process_next_event()
        
        assert result is True
        event.refresh_from_db()
        assert event.status == MinecraftOutboxEvent.STATUS_FAILED
        assert "Missing player" in event.last_error
