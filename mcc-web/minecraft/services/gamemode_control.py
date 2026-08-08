# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    gamemode_control.py
# @note    Session gamemode helpers (survival / adventure / spectator).

from __future__ import annotations

from minecraft.models import MCSession
from minecraft.services.account_login import (
    normalize_play_gamemode,
    preferred_gamemode_for_account,
)


def play_gamemode_for_type(account_type: str, *, spectator: bool) -> str:
    """Legacy helper: play mode vs spectator toggle."""
    return preferred_gamemode_for_account(
        account_type,
        prefer_spectator=spectator,
    )


def gamemode_command(login: str, gamemode: str) -> str:
    name = (login or "").strip()
    mode = (gamemode or "").strip().lower()
    return f"gamemode {mode} {name}"


def apply_play_gamemode_fields(session: MCSession, mode: str) -> None:
    """Set play_gamemode and keep gamemode_spectator in sync (no save)."""
    normalized = normalize_play_gamemode(mode) or MCSession.GAMEMODE_ADVENTURE
    session.play_gamemode = normalized
    session.gamemode_spectator = normalized == MCSession.GAMEMODE_SPECTATOR
