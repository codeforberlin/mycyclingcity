# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from minecraft.services.arena_motion import state as race_state
from minecraft.services.arena_motion.race_modes import MODE_DUAL, MODE_LAPS, MODE_VELOS
from minecraft.services.arena_live_hud import (
    LiveHudSnapshot,
    _format_sidebar_line,
    _should_throttle,
    build_live_hud_commands,
    build_live_hud_snapshot,
    reset_live_hud_cache,
    should_clear_live_hud,
    sync_arena_live_hud,
)
from minecraft.services.sidebar_visibility import arena_live_sidebar_slot


@pytest.fixture(autouse=True)
def _reset_hud_cache():
    reset_live_hud_cache()
    yield
    reset_live_hud_cache()


def _sample_state(**overrides):
    base = {
        "status": race_state.STATUS_RUNNING,
        "race_mode": MODE_DUAL,
        "target_laps": 5,
        "assignments": [
            {"lane_id": "lane_1", "cyclist": "Anna"},
            {"lane_id": "lane_2", "cyclist": "Ben"},
        ],
        "live": {
            "lane_1": {
                "cyclist": "Anna",
                "place": 1,
                "lap": 3,
                "finished": False,
                "speed_kmh": 18.2,
            },
            "lane_2": {
                "cyclist": "Ben",
                "place": 2,
                "lap": 2,
                "finished": False,
                "speed_kmh": 15.0,
            },
        },
    }
    base.update(overrides)
    return base


@pytest.mark.unit
class TestArenaLiveHudLines:
    def test_dual_running_line(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Anna",
                "place": 1,
                "lap": 3,
                "finished": False,
                "speed_kmh": 18.2,
            },
            race_mode=MODE_DUAL,
            target_laps=5,
            lane_slot=1,
            frozen=False,
        )
        assert "P1" not in line
        assert "18 km/h" in line
        assert "2/5" in line
        assert "Velos" not in line

    def test_finished_line(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Ben",
                "place": 2,
                "finished": True,
                "finish_time_s": 45.04,
            },
            race_mode=MODE_LAPS,
            target_laps=5,
            lane_slot=2,
            frozen=True,
        )
        assert "P2" not in line
        assert "45.0s" in line
        assert "Ziel" not in line
        assert "Velos" not in line

    def test_finished_laps_shows_velos_when_frozen(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Anna",
                "place": 1,
                "finished": True,
                "finish_time_s": 120.0,
                "velos": 66,
            },
            race_mode=MODE_LAPS,
            target_laps=5,
            lane_slot=1,
            frozen=True,
        )
        assert "66V" in line
        assert "120.0s" in line
        assert "Ziel" not in line
        assert line.index("120.0s") < line.index("66V")

    def test_finished_velos_mode_time_after_velos(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Anna",
                "place": 1,
                "finished": True,
                "finish_time_s": 180.0,
                "velos": 42,
            },
            race_mode=MODE_VELOS,
            target_laps=1,
            lane_slot=1,
            frozen=True,
        )
        assert line.index("42V") < line.index("180.0s")

    def test_finished_laps_hides_velos_while_running(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Anna",
                "place": 1,
                "finished": True,
                "finish_time_s": 120.0,
                "velos": 66,
            },
            race_mode=MODE_LAPS,
            target_laps=5,
            lane_slot=1,
            frozen=False,
        )
        assert "66V" not in line
        assert "120.0s" in line
        assert "Ziel" not in line

    def test_velos_mode_snapshot_sorted_by_velos(self):
        snapshot = build_live_hud_snapshot(
            _sample_state(
                race_mode=MODE_VELOS,
                live={
                    "lane_1": {
                        "cyclist": "Anna",
                        "place": 2,
                        "lap": 1,
                        "finished": False,
                        "speed_kmh": 10.0,
                        "velos": 40,
                        "distance_m": 100,
                    },
                    "lane_2": {
                        "cyclist": "Ben",
                        "place": 1,
                        "lap": 1,
                        "finished": False,
                        "speed_kmh": 12.0,
                        "velos": 66,
                        "distance_m": 120,
                    },
                },
            )
        )
        assert snapshot is not None
        assert snapshot.rows[0][0].startswith("1.")
        assert "Ben" in snapshot.rows[0][0]
        assert "66V" in snapshot.rows[0][0]
        assert "Anna" in snapshot.rows[1][0]
        assert "40V" in snapshot.rows[1][0]

    def test_velos_mode_line(self):
        line = _format_sidebar_line(
            {
                "cyclist": "Anna",
                "place": 1,
                "lap": 1,
                "finished": False,
                "speed_kmh": 18.0,
                "velos": 66,
            },
            race_mode=MODE_VELOS,
            target_laps=5,
            lane_slot=1,
            frozen=False,
        )
        assert "P1" not in line
        assert "66V" in line
        assert "18 km/h" in line
        assert "Runden" not in line

    def test_metric_columns_align(self):
        line_short = _format_sidebar_line(
            {"cyclist": "Anna", "place": 1, "lap": 3, "finished": False, "speed_kmh": 18.0},
            race_mode=MODE_DUAL,
            target_laps=5,
            lane_slot=1,
            frozen=False,
        )
        line_long = _format_sidebar_line(
            {"cyclist": "Speiche", "place": 2, "lap": 2, "finished": False, "speed_kmh": 15.0},
            race_mode=MODE_DUAL,
            target_laps=5,
            lane_slot=4,
            frozen=False,
        )
        assert line_short.index("km/h") == line_long.index("km/h")
        assert line_short.index("2/5") == line_long.index("1/5")

    def test_scoreboard_holder_uses_nbsp(self):
        from minecraft.services.arena_live_hud import _scoreboard_holder

        assert _scoreboard_holder("1. Anna     18 km/h   2/5") == (
            "1.\u00a0Anna\u00a0\u00a0\u00a0\u00a0\u00a018\u00a0km/h\u00a0\u00a0\u00a02/5"
        )


@pytest.mark.unit
class TestArenaLiveHudSnapshot:
    def test_build_running_snapshot(self):
        snapshot = build_live_hud_snapshot(_sample_state())
        assert snapshot is not None
        assert snapshot.header == "- R LIVE -"
        assert any("Anna" in row[0] for row in snapshot.rows)

    def test_build_frozen_result_header(self):
        snapshot = build_live_hud_snapshot(
            _sample_state(status=race_state.STATUS_IDLE)
        )
        assert snapshot is not None
        assert snapshot.header == "- R ERGEBNIS -"

    def test_laps_mode_running_header(self):
        snapshot = build_live_hud_snapshot(
            _sample_state(race_mode=MODE_LAPS)
        )
        assert snapshot is not None
        assert snapshot.header == "- R LIVE -"

    def test_velos_header_while_running(self):
        snapshot = build_live_hud_snapshot(
            _sample_state(
                race_mode=MODE_VELOS,
                live={
                    "lane_1": {
                        "cyclist": "Anna",
                        "place": 1,
                        "lap": 1,
                        "finished": False,
                        "speed_kmh": 10.0,
                        "velos": 12,
                    }
                },
            )
        )
        assert snapshot is not None
        assert snapshot.header == "- V VELOS -"

    def test_velos_header_includes_remaining(self):
        snapshot = build_live_hud_snapshot(
            _sample_state(
                race_mode=MODE_VELOS,
                live={
                    "lane_1": {
                        "cyclist": "Anna",
                        "place": 1,
                        "lap": 1,
                        "finished": False,
                        "speed_kmh": 10.0,
                        "velos": 12,
                        "remaining_s": 102,
                    }
                },
            )
        )
        assert snapshot is not None
        assert snapshot.header == "- V 1:42 -"

    def test_should_clear_when_live_empty(self):
        assert should_clear_live_hud({"live": {}, "initialized": True}) is True
        assert should_clear_live_hud(_sample_state()) is False

    def test_speed_change_updates_signature(self):
        base = build_live_hud_snapshot(_sample_state())
        faster = build_live_hud_snapshot(
            _sample_state(
                live={
                    "lane_1": {
                        "cyclist": "Anna",
                        "place": 1,
                        "lap": 3,
                        "finished": False,
                        "speed_kmh": 22.0,
                    },
                    "lane_2": {
                        "cyclist": "Ben",
                        "place": 2,
                        "lap": 2,
                        "finished": False,
                        "speed_kmh": 15.0,
                    },
                }
            )
        )
        assert base is not None and faster is not None
        assert base.signature != faster.signature
        assert base.rows != faster.rows
        assert _should_throttle(base, faster, elapsed=0.2) is False

    def test_throttle_when_signature_unchanged(self):
        base = build_live_hud_snapshot(_sample_state())
        same = build_live_hud_snapshot(_sample_state())
        assert base is not None and same is not None
        assert base.signature == same.signature
        assert _should_throttle(base, same, elapsed=0.2) is True
        assert _should_throttle(base, same, elapsed=2.0) is False


@pytest.mark.unit
class TestArenaLiveHudCommands:
    def test_build_commands_include_display_slot(self):
        snapshot = build_live_hud_snapshot(_sample_state())
        assert snapshot is not None
        commands = build_live_hud_commands(snapshot)
        assert commands[0] == "scoreboard players reset * ArenaLive"
        assert 'displayname "- R LIVE -"' in commands[1]
        assert "numberformat blank" in commands[2]
        assert "Anna" in commands[3]
        assert "\u00a0" in commands[3]
        assert "team modify" not in commands[3]
        assert commands[-1] == f"scoreboard objectives setdisplay {arena_live_sidebar_slot()} ArenaLive"

    def test_arena_live_sidebar_slot(self):
        assert arena_live_sidebar_slot() == "sidebar.team.gray"


@pytest.mark.unit
class TestSyncArenaLiveHud:
    @patch("minecraft.services.arena_live_hud.live_hud_enabled", return_value=True)
    @patch("minecraft.services.arena_live_hud.race_state.load_state")
    @patch("minecraft.services.arena_live_hud.rcon_client.run_commands")
    @patch("minecraft.services.arena_live_hud.rcon_client.ensure_objective")
    @patch("minecraft.services.arena_live_hud.ensure_sidebar_routing_teams")
    def test_sync_applies_running_state(
        self,
        _mock_teams,
        _mock_objective,
        mock_run,
        mock_load,
        _mock_enabled,
    ):
        mock_load.return_value = _sample_state()
        mock_run.return_value = (True, "ok")

        assert sync_arena_live_hud(force=True) is True
        mock_run.assert_called_once()
        commands = mock_run.call_args[0][0]
        assert any("Anna" in cmd for cmd in commands)

    @patch("minecraft.services.arena_live_hud.live_hud_enabled", return_value=True)
    @patch("minecraft.services.arena_live_hud.race_state.load_state")
    @patch("minecraft.services.arena_live_hud.clear_arena_live_display")
    @patch("minecraft.services.arena_live_hud.ensure_sidebar_routing_teams")
    def test_sync_clears_when_live_empty(
        self,
        _mock_teams,
        mock_clear,
        mock_load,
        _mock_enabled,
    ):
        mock_load.return_value = _sample_state()
        with patch("minecraft.services.arena_live_hud.rcon_client.run_commands", return_value=(True, "ok")):
            with patch("minecraft.services.arena_live_hud.rcon_client.ensure_objective"):
                sync_arena_live_hud(force=True)

        mock_load.return_value = {"live": {}, "initialized": True}
        assert sync_arena_live_hud(force=True) is True
        mock_clear.assert_called_once()

    @patch("minecraft.services.arena_live_hud.live_hud_enabled", return_value=True)
    @patch("minecraft.services.arena_live_hud.race_state.load_state")
    @patch("minecraft.services.arena_live_hud.rcon_client.run_commands")
    @patch("minecraft.services.arena_live_hud.rcon_client.ensure_objective")
    @patch("minecraft.services.arena_live_hud.ensure_sidebar_routing_teams")
    def test_sync_skips_identical_snapshot(
        self,
        _mock_teams,
        _mock_objective,
        mock_run,
        mock_load,
        _mock_enabled,
    ):
        mock_load.return_value = _sample_state()
        mock_run.return_value = (True, "ok")

        assert sync_arena_live_hud(force=True) is True
        mock_run.reset_mock()
        assert sync_arena_live_hud() is False
        mock_run.assert_not_called()
