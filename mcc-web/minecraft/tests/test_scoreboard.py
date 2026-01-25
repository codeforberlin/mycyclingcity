# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_scoreboard.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Unit tests for Minecraft scoreboard service.

Tests cover:
- update_snapshot
- refresh_scoreboard_snapshot (with mocking)
"""

import pytest
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.utils import timezone

from minecraft.models import MinecraftPlayerScoreboardSnapshot
from minecraft.services.scoreboard import update_snapshot, refresh_scoreboard_snapshot
from api.tests.conftest import CyclistFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestScoreboardService:
    """Tests for scoreboard service functions."""
    
    def test_update_snapshot_creates_new(self):
        """Test updating snapshot creates new entry."""
        cyclist = CyclistFactory(mc_username="testplayer")
        
        update_snapshot("testplayer", 1000, 500, cyclist.id)
        
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.coins_total == 1000
        assert snapshot.coins_spendable == 500
        assert snapshot.cyclist == cyclist
        assert snapshot.source == "rcon"
    
    def test_update_snapshot_updates_existing(self):
        """Test updating snapshot updates existing entry."""
        cyclist = CyclistFactory(mc_username="testplayer")
        
        # Create initial snapshot
        update_snapshot("testplayer", 1000, 500, cyclist.id)
        
        # Update snapshot
        update_snapshot("testplayer", 2000, 1000, cyclist.id)
        
        # Should only have one snapshot
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 1
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.coins_total == 2000
        assert snapshot.coins_spendable == 1000
    
    def test_update_snapshot_handles_negative_values(self):
        """Test that update_snapshot clamps negative values to 0."""
        cyclist = CyclistFactory(mc_username="testplayer")
        
        update_snapshot("testplayer", -100, -50, cyclist.id)
        
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.coins_total == 0
        assert snapshot.coins_spendable == 0
    
    def test_update_snapshot_without_cyclist(self):
        """Test updating snapshot without cyclist."""
        update_snapshot("orphanplayer", 1000, 500, None)
        
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="orphanplayer")
        assert snapshot.cyclist is None
        assert snapshot.coins_total == 1000
    
    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_scoreboards')
    def test_refresh_scoreboard_snapshot(self, mock_ensure, mock_rcon):
        """Test refreshing scoreboard snapshot."""
        # Setup mocks
        mock_ensure.return_value = None
        mock_rcon_client = MagicMock()
        mock_rcon_client.get_player_score.side_effect = lambda player, objective: {
            (settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL, "player1"): 1000,
            (settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE, "player1"): 500,
            (settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL, "player2"): 2000,
            (settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE, "player2"): 1000,
        }.get((objective, player), None)
        
        mock_rcon.get_player_score = mock_rcon_client.get_player_score
        
        # Create cyclists with mc_username
        cyclist1 = CyclistFactory(mc_username="player1")
        cyclist2 = CyclistFactory(mc_username="player2")
        
        # Refresh snapshot
        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            updated = refresh_scoreboard_snapshot()
        
        assert updated == 2
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 2
        
        snapshot1 = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="player1")
        assert snapshot1.coins_total == 1000
        assert snapshot1.coins_spendable == 500
        
        snapshot2 = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="player2")
        assert snapshot2.coins_total == 2000
        assert snapshot2.coins_spendable == 1000
    
    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_scoreboards')
    def test_refresh_scoreboard_snapshot_skips_players_without_scores(self, mock_ensure, mock_rcon):
        """Test that refresh skips players without scores."""
        mock_ensure.return_value = None
        mock_rcon.get_player_score.return_value = None
        
        cyclist = CyclistFactory(mc_username="noscoreplayer")
        
        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            updated = refresh_scoreboard_snapshot()
        
        assert updated == 0
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 0
    
    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_scoreboards')
    @patch('minecraft.services.scoreboard.settings')
    def test_refresh_scoreboard_snapshot_updates_db_spendable(self, mock_settings, mock_ensure, mock_rcon):
        """Test that refresh can update DB spendable if enabled."""
        mock_settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE = True
        mock_settings.MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL = "coins_total"
        mock_settings.MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE = "coins_spendable"
        
        mock_ensure.return_value = None
        mock_rcon.get_player_score.side_effect = lambda player, objective: {
            "coins_total": 1000,
            "coins_spendable": 750,
        }.get(objective, None)
        
        cyclist = CyclistFactory(mc_username="testplayer", coins_spendable=500)
        
        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            with patch('minecraft.services.scoreboard.settings', mock_settings):
                updated = refresh_scoreboard_snapshot()
        
        assert updated == 1
        cyclist.refresh_from_db()
        assert cyclist.coins_spendable == 750
