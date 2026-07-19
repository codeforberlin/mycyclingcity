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

    def test_validate_requires_commands(self):
        errors, warnings = validate_commands([])
        assert errors
        assert not warnings
