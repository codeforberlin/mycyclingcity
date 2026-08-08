# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import override_settings

from minecraft.services.sidebar_visibility import (
    apply_builder_sidebar_display,
    arena_station_prefix_text,
    arena_station_team_name,
    arena_visibility_commands,
    builder_session_intro_commands,
    builder_sidebar_slot,
    builder_station_prefix_text,
    builder_station_team_name,
    builder_visibility_commands,
    clear_visibility_commands,
    ensure_arena_station_team,
    ensure_builder_station_team,
)
from minecraft.services.team_scoreboard import ensure_team_scoreboard_objective


@pytest.mark.unit
class TestSidebarVisibilityCommands:
    def test_builder_joins_bau_team_without_label(self):
        assert builder_visibility_commands("Kette") == ["team join mcc_bau Kette"]

    def test_builder_joins_station_team_with_label(self):
        assert builder_visibility_commands("mccpc01", team_label="Kette") == [
            "team join mcc_kette mccpc01"
        ]

    def test_builder_station_team_name(self):
        assert builder_station_team_name("Kette") == "mcc_kette"
        assert builder_station_prefix_text("Kette") == "[Kette] "

    def test_builder_session_intro(self):
        cmds = builder_session_intro_commands("mccpc01", "Kette")
        assert len(cmds) == 1
        assert cmds[0].startswith("tellraw mccpc01 ")
        assert "Kette" in cmds[0]

    def test_arena_joins_shared_team_without_label(self):
        assert arena_visibility_commands("Arena1") == [
            "tag Arena1 add mcc_arena",
            "team join mcc_arena Arena1",
        ]

    def test_arena_joins_station_team_with_label(self):
        assert arena_visibility_commands("mccpc01", team_label="Arena1") == [
            "tag mccpc01 add mcc_arena",
            "team join mcc_arena1 mccpc01",
        ]

    def test_arena_station_team_name(self):
        assert arena_station_team_name("Arena1") == "mcc_arena1"
        assert arena_station_prefix_text("Arena1") == "[Arena1] "

    def test_clear_leaves_team_and_audience_tag(self):
        assert clear_visibility_commands("Arena1") == [
            "tag Arena1 remove mcc_arena",
            "team leave Arena1",
        ]

    def test_builder_sidebar_slot(self):
        assert builder_sidebar_slot() == "sidebar.team.blue"

    @patch("minecraft.services.sidebar_visibility.rcon_client")
    def test_ensure_builder_station_team_sets_color_and_prefix(self, mock_rcon):
        team = ensure_builder_station_team("Kette")
        assert team == "mcc_kette"
        mock_rcon.ensure_scoreboard_team.assert_called_once_with(
            "mcc_kette",
            color="blue",
            prefix="[Kette] ",
        )

    @patch("minecraft.services.sidebar_visibility.rcon_client")
    def test_ensure_arena_station_team_sets_color_and_prefix(self, mock_rcon):
        team = ensure_arena_station_team("Arena1")
        assert team == "mcc_arena1"
        mock_rcon.ensure_scoreboard_team.assert_called_once_with(
            "mcc_arena1",
            color="gray",
            prefix="[Arena1] ",
        )


@pytest.mark.unit
@pytest.mark.django_db
class TestEnsureTeamScoreboardObjective:
    @patch("minecraft.services.sidebar_visibility.rcon_client")
    @patch("minecraft.services.team_scoreboard.rcon_client")
    @patch("minecraft.services.team_scoreboard.get_display_name")
    @patch("minecraft.services.team_scoreboard.get_objective_spendable")
    @patch("minecraft.services.team_scoreboard.MinecraftIntegrationConfig")
    def test_routes_sidebar_to_builder_team_when_enabled(
        self, mock_config_cls, mock_objective, mock_display, mock_rcon, mock_sidebar_rcon
    ):
        mock_config_cls.get_config.return_value.sidebar_enabled = True
        mock_objective.return_value = "team_velos_spendable"
        mock_display.return_value = "Velo-Arena"

        result = ensure_team_scoreboard_objective()

        assert result == "team_velos_spendable"
        mock_rcon.ensure_objective.assert_called_once_with("team_velos_spendable", "Velo-Arena")
        mock_sidebar_rcon.clear_objective_display.assert_called_once_with("sidebar")
        mock_sidebar_rcon.set_objective_display.assert_called_once_with(
            "team_velos_spendable",
            "sidebar.team.blue",
        )
        assert mock_sidebar_rcon.ensure_scoreboard_team.call_count == 2

    @patch("minecraft.services.sidebar_visibility.rcon_client")
    @patch("minecraft.services.team_scoreboard.rcon_client")
    @patch("minecraft.services.team_scoreboard.get_display_name")
    @patch("minecraft.services.team_scoreboard.get_objective_spendable")
    @patch("minecraft.services.team_scoreboard.MinecraftIntegrationConfig")
    def test_skips_sidebar_when_disabled(
        self, mock_config_cls, mock_objective, mock_display, mock_rcon, mock_sidebar_rcon
    ):
        mock_config_cls.get_config.return_value.sidebar_enabled = False
        mock_objective.return_value = "team_velos_spendable"
        mock_display.return_value = "Velo-Arena"

        ensure_team_scoreboard_objective()

        mock_rcon.set_objective_display.assert_not_called()
        mock_sidebar_rcon.set_objective_display.assert_not_called()
        mock_sidebar_rcon.clear_objective_display.assert_not_called()

    @override_settings(MCC_MINECRAFT_SCOREBOARD_BUILDER_COLOR="yellow")
    @patch("minecraft.services.sidebar_visibility.rcon_client")
    def test_apply_builder_sidebar_display_uses_color(self, mock_rcon):
        apply_builder_sidebar_display("team_velos_spendable")
        mock_rcon.set_objective_display.assert_called_once_with(
            "team_velos_spendable",
            "sidebar.team.yellow",
        )
