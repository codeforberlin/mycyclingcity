# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from minecraft.models import MCSession
from minecraft.services.gamemode_control import gamemode_command, play_gamemode_for_type
from minecraft.services.player_session_bootstrap import build_player_post_login_commands


@pytest.mark.unit
class TestGamemodeControl:
    def test_player_adventure(self):
        assert play_gamemode_for_type(MCSession.ACCOUNT_PLAYER, spectator=False) == "adventure"

    def test_player_spectator(self):
        assert play_gamemode_for_type(MCSession.ACCOUNT_PLAYER, spectator=True) == "spectator"

    def test_builder_adventure(self):
        assert play_gamemode_for_type(MCSession.ACCOUNT_BUILDER, spectator=False) == "adventure"

    def test_gamemode_command(self):
        assert gamemode_command("Arena1", "spectator") == "gamemode spectator Arena1"


@pytest.mark.unit
class TestPlayerBootstrapSpectator:
    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_spectator_skips_emeralds(self, _mock_team):
        commands = build_player_post_login_commands("Arena1", emerald_count=4, spectator=True)
        assert commands[0] == "gamemode spectator Arena1"
        assert not any(cmd.startswith("give ") for cmd in commands)

    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_adventure_gives_emeralds(self, _mock_team):
        commands = build_player_post_login_commands("Arena1", emerald_count=4, spectator=False)
        assert commands[0] == "gamemode adventure Arena1"
        assert "give Arena1 minecraft:emerald 4" in commands
