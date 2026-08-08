# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from minecraft.services.rcon_client import (
    parse_online_players,
    response_indicates_missing_player,
    run_commands_require_player,
    wait_for_player_online,
)


@pytest.mark.unit
class TestParseOnlinePlayers:
    def test_empty(self):
        assert parse_online_players("") == []
        assert parse_online_players("There are 0 of a max of 20 players online: ") == []

    def test_single(self):
        assert parse_online_players(
            "There are 1 of a max of 20 players online: Arena1"
        ) == ["Arena1"]

    def test_multiple(self):
        assert parse_online_players(
            "There are 2 of a max of 20 players online: Arena1, Kette"
        ) == ["Arena1", "Kette"]

    def test_strips_team_prefix(self):
        assert parse_online_players(
            "There are 1 of a max of 20 players online: [Dynamo] mccpc01"
        ) == ["mccpc01"]

    def test_strips_team_prefix_multiple(self):
        assert parse_online_players(
            "There are 2 of a max of 20 players online: [Dynamo] mccpc01, [Kette] mccpc02"
        ) == ["mccpc01", "mccpc02"]


@pytest.mark.unit
class TestMissingPlayerResponse:
    def test_detects_missing(self):
        assert response_indicates_missing_player("No player was found")
        assert response_indicates_missing_player("No entity was found")
        assert not response_indicates_missing_player(
            "Set Arena1's game mode to Adventure Mode"
        )


@pytest.mark.unit
@pytest.mark.django_db
class TestWaitAndRequirePlayer:
    @patch("minecraft.services.rcon_client.is_player_online", side_effect=[False, False, True])
    @patch("minecraft.services.rcon_client.time.sleep")
    def test_wait_for_player_online(self, _sleep, _online):
        assert wait_for_player_online("Arena1", timeout_sec=2, interval_sec=0.01) is True

    @patch("minecraft.services.rcon_client.is_player_online", return_value=False)
    @patch("minecraft.services.rcon_client.time.sleep")
    def test_wait_timeout(self, _sleep, _online):
        assert wait_for_player_online("Arena1", timeout_sec=0.05, interval_sec=0.01) is False

    @patch("minecraft.services.rcon_client.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.rcon_client.run_command",
        side_effect=["No player was found", "Set Arena1's game mode to Adventure Mode"],
    )
    def test_require_player_retries(self, mock_cmd, _wait):
        ok, log = run_commands_require_player(
            ["gamemode adventure Arena1"],
            player="Arena1",
            retries=3,
            retry_delay_sec=0.01,
        )
        assert ok is True
        assert mock_cmd.call_count == 2
        assert "retry 1" in log


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionLoginWaitConfig:
    def test_uses_integration_config_wait(self, settings):
        from minecraft.models import MinecraftIntegrationConfig
        from minecraft.services.session_control import _session_login_wait_seconds

        settings.MCC_MINECRAFT_SESSION_LOGIN_WAIT_SECONDS = 8
        config = MinecraftIntegrationConfig.get_config()
        config.session_login_wait_seconds = 45
        config.save()
        assert _session_login_wait_seconds() == 45.0

    def test_clamps_minimum(self):
        from minecraft.models import MinecraftIntegrationConfig
        from minecraft.services.session_control import _session_login_wait_seconds

        config = MinecraftIntegrationConfig.get_config()
        config.session_login_wait_seconds = 1
        config.save()
        assert _session_login_wait_seconds() == 5.0


@pytest.mark.unit
def test_describe_rcon_error_connection_refused():
    from minecraft.services.rcon_client import RconConfig, describe_rcon_error

    cfg = RconConfig(host="127.0.0.1", port=25575, password="x")
    msg = describe_rcon_error("Paper", cfg, ConnectionRefusedError(111, "Connection refused"))
    assert "nicht erreichbar" in msg
    assert "25575" in msg
