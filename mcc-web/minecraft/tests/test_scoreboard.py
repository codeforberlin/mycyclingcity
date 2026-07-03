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

from minecraft.models import MinecraftPlayerScoreboardSnapshot
from minecraft.services.scoreboard import update_snapshot, refresh_scoreboard_snapshot
from api.tests.conftest import GroupFactory


@pytest.mark.unit
@pytest.mark.django_db
class TestScoreboardService:
    """Tests for scoreboard service functions."""

    def test_update_snapshot_creates_new(self):
        """Test updating snapshot creates new entry."""
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", 1000, 500, group_id=group.id)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 1000
        assert snapshot.velos_spendable == 500
        assert snapshot.group == group
        assert snapshot.source == "rcon"

    def test_update_snapshot_updates_existing(self):
        """Test updating snapshot updates existing entry."""
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", 1000, 500, group_id=group.id)
        update_snapshot("testplayer", 2000, 1000, group_id=group.id)

        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 1
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 2000
        assert snapshot.velos_spendable == 1000

    def test_update_snapshot_handles_negative_values(self):
        """Test that update_snapshot clamps negative values to 0."""
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", -100, -50, group_id=group.id)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 0
        assert snapshot.velos_spendable == 0

    def test_update_snapshot_without_group(self):
        """Test updating snapshot without group."""
        update_snapshot("orphanplayer", 1000, 500)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="orphanplayer")
        assert snapshot.group is None
        assert snapshot.velos_total == 1000

    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_group_velos_scoreboards')
    def test_refresh_scoreboard_snapshot(self, mock_ensure, mock_rcon):
        """Test refreshing scoreboard snapshot for groups."""
        mock_ensure.return_value = None
        mock_rcon_client = MagicMock()
        mock_rcon_client.get_player_score.side_effect = lambda player, objective: {
            (settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL, "player1"): 1000,
            (settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE, "player1"): 500,
            (settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL, "player2"): 2000,
            (settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE, "player2"): 1000,
        }.get((objective, player), None)

        mock_rcon.get_player_score = mock_rcon_client.get_player_score

        group1 = GroupFactory(mc_username="player1")
        group2 = GroupFactory(mc_username="player2")

        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            updated = refresh_scoreboard_snapshot()

        assert updated == 2
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 2

        snapshot1 = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="player1")
        assert snapshot1.velos_total == 1000
        assert snapshot1.velos_spendable == 500
        assert snapshot1.group == group1

        snapshot2 = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="player2")
        assert snapshot2.velos_total == 2000
        assert snapshot2.velos_spendable == 1000
        assert snapshot2.group == group2

    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_group_velos_scoreboards')
    def test_refresh_scoreboard_snapshot_skips_groups_without_scores(self, mock_ensure, mock_rcon):
        """Test that refresh skips groups without scores."""
        mock_ensure.return_value = None
        mock_rcon.get_player_score.return_value = None

        GroupFactory(mc_username="noscoreplayer")

        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            updated = refresh_scoreboard_snapshot()

        assert updated == 0
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 0

    @patch('minecraft.services.scoreboard.rcon_client')
    @patch('minecraft.services.scoreboard.ensure_group_velos_scoreboards')
    @patch('minecraft.services.scoreboard.settings')
    def test_refresh_scoreboard_snapshot_updates_db_spendable(self, mock_settings, mock_ensure, mock_rcon):
        """Test that refresh can update DB spendable if enabled."""
        mock_settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE = True
        mock_settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL = "group_velos_total"
        mock_settings.MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE = "group_velos_spendable"

        mock_ensure.return_value = None
        mock_rcon.get_player_score.side_effect = lambda player, objective: {
            "group_velos_total": 1000,
            "group_velos_spendable": 750,
        }.get(objective, None)

        group = GroupFactory(mc_username="testplayer", velos_spendable=500)

        with patch('minecraft.services.scoreboard.rcon_client', mock_rcon):
            with patch('minecraft.services.scoreboard.settings', mock_settings):
                updated = refresh_scoreboard_snapshot()

        assert updated == 1
        group.refresh_from_db()
        assert group.velos_spendable == 750
