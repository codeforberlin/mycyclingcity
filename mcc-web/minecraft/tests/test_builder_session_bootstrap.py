# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.test import override_settings

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftRconPreset
from minecraft.rcon_preset_defaults import BUILDER_SESSION_BOOTSTRAP_PRESET
from minecraft.services.builder_session_bootstrap import (
    build_builder_session_start_commands,
    get_bootstrap_preset_commands,
)
from minecraft.services.session_control import end_session, start_builder_session
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
@pytest.mark.django_db
class TestBuilderSessionBootstrap:
    def test_get_bootstrap_preset_commands_from_db(self):
        MinecraftRconPreset.objects.create(
            slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Bootstrap",
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

    @override_settings(
        MCC_MINECRAFT_BUILDER_SESSION_BOOTSTRAP_ENABLED=True,
    )
    @patch("minecraft.services.sidebar_visibility.ensure_builder_station_team")
    def test_build_start_commands_includes_bootstrap_and_login(self, mock_ensure):
        MinecraftRconPreset.objects.create(
            slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful"],
            enabled=True,
        )
        commands = build_builder_session_start_commands("Kette")
        mock_ensure.assert_called_with("Kette")
        assert commands[0] == "difficulty peaceful"
        assert commands[-4] == "authme forcelogin Kette"
        assert commands[-3] == "gamemode adventure Kette"
        assert commands[-2] == "team join mcc_kette Kette"
        assert commands[-1].startswith("tellraw Kette ")

    @override_settings(
        MCC_MINECRAFT_BUILDER_SESSION_BOOTSTRAP_ENABLED=False,
    )
    @patch("minecraft.services.sidebar_visibility.ensure_builder_station_team")
    def test_build_start_commands_minimal_when_disabled(self, mock_ensure):
        commands = build_builder_session_start_commands("Kette")
        mock_ensure.assert_called_with("Kette")
        assert commands == [
            "authme forcelogin Kette",
            "gamemode adventure Kette",
            "team join mcc_kette Kette",
            'tellraw Kette {"text":"Du spielst als ","extra":[{"text":"Kette","bold":true,"color":"gold"},{"text":"."}]}',
        ]


@pytest.mark.unit
@pytest.mark.django_db
class TestBuilderSessionBootstrapIntegration:
    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"

    @override_settings(
        MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret",
    )
    def test_start_builder_runs_bootstrap(self):
        from unittest.mock import patch

        MinecraftRconPreset.objects.create(
            slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful"],
            enabled=True,
        )
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        from minecraft.models import MinecraftTeamRegistration

        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(authme_is_registered=True)

        with (
            patch(
                "minecraft.services.session_control.run_commands",
                return_value=(True, "ok"),
            ) as mock_rcon,
            patch(
                "minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams",
            ),
            patch(
                "minecraft.services.sidebar_visibility.ensure_builder_station_team",
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
            start_builder_session("Kette", duration=90)

        world_calls = [c[0][0] for c in mock_rcon.call_args_list]
        assert ["difficulty peaceful"] in world_calls
        assert ["authme forcelogin Kette"] in world_calls
        assert mock_player_rcon.call_args[0][0] == [
            "gamemode adventure Kette",
            "team join mcc_kette Kette",
            'tellraw Kette {"text":"Du spielst als ","extra":[{"text":"Kette","bold":true,"color":"gold"},{"text":"."}]}',
        ]

    def test_end_builder_logs_out_without_lp_revoke(self):
        from unittest.mock import patch

        MinecraftRconPreset.objects.create(
            slug=BUILDER_SESSION_BOOTSTRAP_PRESET["slug"],
            name="Bootstrap",
            category="gamerule",
            commands=["difficulty peaceful"],
            enabled=True,
        )
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        from minecraft.models import MinecraftTeamRegistration

        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(authme_is_registered=True)

        with (
            patch("minecraft.services.session_control.run_commands", return_value=(True, "ok")),
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_builder_station_team"),
            patch("minecraft.services.session_control.wait_for_player_online", return_value=True),
            patch(
                "minecraft.services.session_control.run_commands_require_player",
                return_value=(True, "ok"),
            ),
        ):
            start_builder_session("Kette", duration=90)

        with patch("minecraft.services.session_control.run_commands", return_value=(True, "ok")) as mock_rcon:
            end_session("Kette")

        assert mock_rcon.call_count >= 2
        first = mock_rcon.call_args_list[0][0][0]
        assert "team leave Kette" in first
        assert mock_rcon.call_args_list[1][0][0] == ["authme logout Kette"]
        assert reg.mc_username == "Kette"
