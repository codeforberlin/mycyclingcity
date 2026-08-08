# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.services.arena_motion.arena_bossbar import (
    BossbarSnapshot,
    build_bossbar_commands,
    build_clear_bossbar_command,
    format_bossbar_title,
)


@pytest.mark.unit
class TestArenaBossbar:
    def test_format_title_minutes(self):
        assert format_bossbar_title(102) == "Restzeit 1:42"

    def test_format_title_seconds_only(self):
        assert format_bossbar_title(45) == "Restzeit 45s"

    def test_build_create_commands(self):
        commands = build_bossbar_commands(
            remaining_s=102,
            time_limit_seconds=180,
            create=True,
        )
        assert commands[0].startswith("bossbar add mcc:arena_live")
        assert "Restzeit 1:42" in commands[0]
        assert "bossbar set mcc:arena_live max 180" in commands
        assert "bossbar set mcc:arena_live value 102" in commands
        assert any("players @a[tag=mcc_arena]" in cmd for cmd in commands)

    def test_build_update_without_create(self):
        commands = build_bossbar_commands(
            remaining_s=99,
            time_limit_seconds=180,
            create=False,
        )
        assert not any(cmd.startswith("bossbar add") for cmd in commands)
        assert commands[-1] == "bossbar set mcc:arena_live value 99"

    def test_clear_command(self):
        assert build_clear_bossbar_command() == "bossbar remove mcc:arena_live"

    def test_snapshot_equality(self):
        assert BossbarSnapshot(42) == BossbarSnapshot(42)
