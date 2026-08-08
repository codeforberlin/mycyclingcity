# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.test import override_settings

from minecraft.models import MinecraftPlayAccount, MinecraftRconPreset
from minecraft.rcon_preset_defaults import PLAYER_SESSION_BOOTSTRAP_PRESET
from minecraft.services.player_session_bootstrap import (
    build_player_session_start_commands,
    get_bootstrap_preset_commands,
)
from minecraft.services.session_control import start_player_session


@pytest.mark.unit
@pytest.mark.django_db
class TestPlayerSessionBootstrap:
    def test_get_bootstrap_preset_commands_from_db(self):
        MinecraftRconPreset.objects.create(
            slug=PLAYER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Player Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful", "gamerule pvp false"],
            enabled=True,
        )
        commands = get_bootstrap_preset_commands()
        assert commands == ["difficulty peaceful", "gamerule pvp false"]

    def test_get_bootstrap_preset_commands_fallback(self):
        commands = get_bootstrap_preset_commands()
        assert commands[0] == "difficulty peaceful"
        assert "gamerule pvp false" in commands

    @override_settings(MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED=True)
    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_build_start_commands_includes_bootstrap_and_adventure(self, mock_ensure):
        MinecraftRconPreset.objects.create(
            slug=PLAYER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Player Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful"],
            enabled=True,
        )
        commands = build_player_session_start_commands("Arena1", emerald_count=4)
        mock_ensure.assert_called_with("Arena1")
        assert commands[0] == "difficulty peaceful"
        assert commands[-5] == "authme forcelogin Arena1"
        assert commands[-4] == "gamemode adventure Arena1"
        assert commands[-3] == "give Arena1 minecraft:emerald 4"
        assert commands[-2] == "tag Arena1 add mcc_arena"
        assert commands[-1] == "team join mcc_arena1 Arena1"

    @override_settings(MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED=False)
    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_build_start_commands_still_forces_adventure_when_disabled(self, mock_ensure):
        commands = build_player_session_start_commands("Arena1", emerald_count=4)
        mock_ensure.assert_called_with("Arena1")
        assert commands == [
            "authme forcelogin Arena1",
            "gamemode adventure Arena1",
            "give Arena1 minecraft:emerald 4",
            "tag Arena1 add mcc_arena",
            "team join mcc_arena1 Arena1",
        ]


@pytest.mark.unit
@pytest.mark.django_db
class TestPlayerSessionBootstrapIntegration:
    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"

    @override_settings(
        MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED=True,
        MCC_MINECRAFT_PLAYER_START_EMERALDS=4,
    )
    def test_start_player_runs_bootstrap_and_adventure(self):
        MinecraftRconPreset.objects.create(
            slug=PLAYER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Player Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful"],
            enabled=True,
        )
        MinecraftPlayAccount.objects.create(
            id_tag="Arena1",
            short_name="Arena1",
            display_name="Arena 1",
            sort_order=1,
        )
        with (
            patch(
                "minecraft.services.session_control.run_commands",
                return_value=(True, "ok"),
            ) as mock_rcon,
            patch(
                "minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams",
            ),
            patch(
                "minecraft.services.sidebar_visibility.ensure_arena_station_team",
            ),
            patch(
                "minecraft.services.session_control.wait_for_player_online",
                return_value=True,
            ),
            patch(
                "minecraft.services.session_control.run_commands_require_player",
                return_value=(True, "ok"),
            ) as mock_player_rcon,
        ):
            start_player_session("Arena1", duration=15)

        world_calls = [c[0][0] for c in mock_rcon.call_args_list]
        assert ["difficulty peaceful"] in world_calls
        assert ["authme forcelogin Arena1"] in world_calls
        player_cmds = mock_player_rcon.call_args[0][0]
        assert player_cmds[0] == "gamemode adventure Arena1"
        assert "minecraft:emerald" in player_cmds[1]
        assert player_cmds[-2] == "tag Arena1 add mcc_arena"
        assert player_cmds[-1] == "team join mcc_arena1 Arena1"
