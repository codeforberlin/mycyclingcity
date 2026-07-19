# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from django.conf import settings

from minecraft.models import MinecraftPlayerScoreboardSnapshot, MinecraftTeamRegistration
from minecraft.services.scoreboard import refresh_scoreboard_snapshot
from minecraft.services.team_scoreboard import update_snapshot
from api.tests.conftest import GroupFactory


def _register_group(group):
    return MinecraftTeamRegistration.objects.create(
        group=group,
        mc_username=group.mc_username,
        is_active=True,
        was_ever_registered=True,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestScoreboardService:
    def test_update_snapshot_creates_new(self):
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", 500, group_id=group.id, db_velos_total=1000)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 1000
        assert snapshot.velos_spendable == 500
        assert snapshot.group == group
        assert snapshot.source == "rcon"

    def test_update_snapshot_updates_existing(self):
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", 500, group_id=group.id, db_velos_total=1000)
        update_snapshot("testplayer", 1000, group_id=group.id, db_velos_total=2000)

        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 1
        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 2000
        assert snapshot.velos_spendable == 1000

    def test_update_snapshot_handles_negative_values(self):
        group = GroupFactory(mc_username="testplayer")

        update_snapshot("testplayer", -50, group_id=group.id, db_velos_total=-100)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="testplayer")
        assert snapshot.velos_total == 0
        assert snapshot.velos_spendable == 0

    def test_update_snapshot_without_group(self):
        update_snapshot("orphanplayer", 500, db_velos_total=1000)

        snapshot = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="orphanplayer")
        assert snapshot.group is None
        assert snapshot.velos_total == 1000

    @patch('minecraft.services.team_scoreboard.rcon_client')
    @patch('minecraft.services.team_scoreboard.ensure_team_scoreboard_objective')
    def test_refresh_scoreboard_snapshot(self, mock_ensure, mock_rcon):
        mock_ensure.return_value = settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE
        mock_rcon.get_player_score.side_effect = lambda player, objective: {
            ("player1", settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE): 500,
            ("player2", settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE): 1000,
        }.get((player, objective), None)

        group1 = GroupFactory(mc_username="player1", velos_total=1000, velos_spendable=500)
        group2 = GroupFactory(mc_username="player2", velos_total=2000, velos_spendable=1000)
        _register_group(group1)
        _register_group(group2)

        updated = refresh_scoreboard_snapshot()

        assert updated == 2
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 2

        snapshot1 = MinecraftPlayerScoreboardSnapshot.objects.get(player_name="player1")
        assert snapshot1.velos_total == 1000
        assert snapshot1.velos_spendable == 500
        assert snapshot1.group == group1

    @patch('minecraft.services.team_scoreboard.rcon_client')
    @patch('minecraft.services.team_scoreboard.ensure_team_scoreboard_objective')
    def test_refresh_scoreboard_snapshot_skips_unregistered_groups(self, mock_ensure, mock_rcon):
        mock_ensure.return_value = settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE
        mock_rcon.get_player_score.return_value = 100

        GroupFactory(mc_username="noscoreplayer")

        updated = refresh_scoreboard_snapshot()

        assert updated == 0
        assert MinecraftPlayerScoreboardSnapshot.objects.count() == 0

    @patch('minecraft.services.team_scoreboard.rcon_client')
    @patch('minecraft.services.team_scoreboard.ensure_team_scoreboard_objective')
    @patch('minecraft.services.team_scoreboard.settings')
    def test_refresh_scoreboard_snapshot_updates_db_spendable(self, mock_settings, mock_ensure, mock_rcon):
        mock_settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE = True
        mock_settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE = "team_velos_spendable"
        mock_ensure.return_value = "team_velos_spendable"
        mock_rcon.get_player_score.return_value = 750

        group = GroupFactory(mc_username="testplayer", velos_spendable=500)
        _register_group(group)

        updated = refresh_scoreboard_snapshot()

        assert updated == 1
        group.refresh_from_db()
        assert group.velos_spendable == 750
