# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    arena_bossbar.py
# @note    Velo-race countdown bossbar (Motion-Worker, not scoreboard).

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from minecraft.services.sidebar_visibility import arena_audience_selector


def bossbar_enabled() -> bool:
    return bool(getattr(settings, "MCC_MINECRAFT_ARENA_BOSSBAR_ENABLED", True))


def bossbar_id() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_ARENA_BOSSBAR_ID", None) or "mcc:arena_live"
    ).strip() or "mcc:arena_live"


def format_bossbar_title(remaining_s: int) -> str:
    remaining = max(0, int(remaining_s))
    minutes, seconds = divmod(remaining, 60)
    if minutes:
        return f"Restzeit {minutes}:{seconds:02d}"
    return f"Restzeit {seconds}s"


def bossbar_audience_selector() -> str:
    return arena_audience_selector()


@dataclass(frozen=True)
class BossbarSnapshot:
    remaining_s: int


def build_bossbar_commands(
    *,
    remaining_s: int,
    time_limit_seconds: int,
    create: bool = False,
) -> list[str]:
    """RCON batch for velos-mode countdown bossbar (arena team only)."""
    bid = bossbar_id()
    remaining = max(0, int(remaining_s))
    limit = max(1, int(time_limit_seconds))
    title = format_bossbar_title(remaining).replace('"', '\\"')
    selector = bossbar_audience_selector()
    title_json = f'{{"text":"{title}","color":"yellow","bold":true}}'
    commands: list[str] = []
    if create:
        commands.append(f"bossbar add {bid} {title_json}")
        commands.extend(
            [
                f"bossbar set {bid} max {limit}",
                f"bossbar set {bid} color yellow",
                f"bossbar set {bid} style notched_6",
                f"bossbar set {bid} players {selector}",
            ]
        )
    commands.extend(
        [
            f"bossbar set {bid} name {title_json}",
            f"bossbar set {bid} max {limit}",
            f"bossbar set {bid} value {remaining}",
        ]
    )
    return commands


def build_clear_bossbar_command() -> str:
    return f"bossbar remove {bossbar_id()}"
