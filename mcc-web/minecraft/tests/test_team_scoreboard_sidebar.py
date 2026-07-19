# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from django.conf import settings

from minecraft.services.team_scoreboard import ensure_team_scoreboard_objective


@pytest.mark.unit
@pytest.mark.django_db
class TestEnsureTeamScoreboardObjective:
    @patch("minecraft.services.team_scoreboard.rcon_client")
    @patch("minecraft.services.team_scoreboard.get_display_name")
    @patch("minecraft.services.team_scoreboard.get_objective_spendable")
    @patch("minecraft.services.team_scoreboard.MinecraftIntegrationConfig")
    def test_sets_sidebar_when_enabled(
        self, mock_config_cls, mock_objective, mock_display, mock_rcon
    ):
        mock_config_cls.get_config.return_value.sidebar_enabled = True
        mock_objective.return_value = "team_velos_spendable"
        mock_display.return_value = "Velo-Arena"

        result = ensure_team_scoreboard_objective()

        assert result == "team_velos_spendable"
        mock_rcon.ensure_objective.assert_called_once_with("team_velos_spendable", "Velo-Arena")
        mock_rcon.set_objective_display.assert_called_once_with(
            "team_velos_spendable",
            settings.MCC_MINECRAFT_SCOREBOARD_DISPLAY_SLOT,
        )

    @patch("minecraft.services.team_scoreboard.rcon_client")
    @patch("minecraft.services.team_scoreboard.get_display_name")
    @patch("minecraft.services.team_scoreboard.get_objective_spendable")
    @patch("minecraft.services.team_scoreboard.MinecraftIntegrationConfig")
    def test_skips_sidebar_when_disabled(
        self, mock_config_cls, mock_objective, mock_display, mock_rcon
    ):
        mock_config_cls.get_config.return_value.sidebar_enabled = False
        mock_objective.return_value = "team_velos_spendable"
        mock_display.return_value = "Velo-Arena"

        ensure_team_scoreboard_objective()

        mock_rcon.set_objective_display.assert_not_called()
