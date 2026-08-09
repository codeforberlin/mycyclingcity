# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.services.preset_commands import parse_commands_text, validate_commands


@pytest.mark.unit
class TestPresetCommands:
    def test_parse_commands_strips_slashes_and_comments(self):
        text = """
        # comment
        /time set day
        gamerule spawn_monsters false
        """
        commands = parse_commands_text(text)
        assert commands == ["time set day", "gamerule spawn_monsters false"]

    def test_validate_deprecated_gamerule_warning(self):
        errors, warnings = validate_commands(["gamerule mobGriefing false"])
        assert not errors
        assert any("mob_griefing" in warning for warning in warnings)

    def test_normalize_preset_commands_renames_daylight_and_weather(self):
        from minecraft.services.preset_commands import normalize_preset_commands

        commands = normalize_preset_commands(
            [
                "time set day",
                "weather clear",
                "gamerule doDaylightCycle false",
                "gamerule doWeatherCycle false",
            ]
        )
        assert commands == [
            "time set day",
            "weather clear",
            "gamerule advance_time false",
            "gamerule advance_weather false",
        ]

    def test_normalize_injects_worldguard_world(self, settings):
        from minecraft.services.preset_commands import normalize_preset_commands

        settings.MCC_MINECRAFT_PAPER_WORLD = "MyCyclingCity"
        commands = normalize_preset_commands(
            [
                "rg flag __global__ build deny",
                "rg flag -w OtherWorld __global__ pvp deny",
                "difficulty peaceful",
            ]
        )
        assert commands == [
            "rg flag -w MyCyclingCity __global__ build deny",
            "rg flag -w OtherWorld __global__ pvp deny",
            "difficulty peaceful",
        ]

    def test_validate_requires_commands(self):
        errors, warnings = validate_commands([])
        assert errors
        assert not warnings
