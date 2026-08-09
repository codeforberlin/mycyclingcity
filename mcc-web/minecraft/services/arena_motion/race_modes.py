# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    race_modes.py
# @note    Arena race mode constants and helpers (laps / velos / dual).

from __future__ import annotations

from typing import Any

from django.conf import settings

# Stop after N laps; rank by finish time.
MODE_LAPS = "laps"
# Stop after time limit; rank by Velos (like MCC map game).
MODE_VELOS = "velos"
# Stop after N laps; celebrate time winner and Velos winner.
MODE_DUAL = "dual"

VALID_RACE_MODES = frozenset({MODE_LAPS, MODE_VELOS, MODE_DUAL})

MODE_LABELS = {
    MODE_LAPS: "Rundenrennen",
    MODE_VELOS: "Velo-Rennen",
    MODE_DUAL: "Doppel-Sieg",
}


def default_race_mode() -> str:
    raw = str(getattr(settings, "MCC_MINECRAFT_ARENA_DEFAULT_RACE_MODE", MODE_DUAL) or MODE_DUAL)
    mode = raw.strip().lower()
    return mode if mode in VALID_RACE_MODES else MODE_DUAL


def default_target_laps() -> int:
    value = int(getattr(settings, "MCC_MINECRAFT_ARENA_DEFAULT_TARGET_LAPS", 5) or 5)
    return max(1, value)


def default_time_limit_seconds() -> int:
    """
    Default race time limit in seconds.

    Prefer Minecraft → Integration (minutes); fall back to settings (seconds).
    """
    try:
        from django.db import DatabaseError
        from minecraft.models import MinecraftIntegrationConfig

        minutes = int(
            MinecraftIntegrationConfig.get_config().arena_default_time_limit_minutes
        )
        if minutes > 0:
            return max(30, minutes * 60)
    except (TypeError, ValueError, AttributeError, DatabaseError):
        pass
    value = int(
        getattr(settings, "MCC_MINECRAFT_ARENA_DEFAULT_TIME_LIMIT_SECONDS", 300) or 300
    )
    return max(30, value)


def time_limit_minutes_for_ui(seconds: int | float | None) -> float:
    """
    Minutes shown in the operator number input (step 0.5).

    Chrome rejects spinner/arrow steps when the value is not an exact multiple of
    ``step`` relative to ``min`` (stepMismatch). Snap to 0.5 so both browsers behave.
    """
    try:
        secs = float(seconds if seconds is not None else default_time_limit_seconds())
    except (TypeError, ValueError):
        secs = float(default_time_limit_seconds())
    minutes = max(0.5, secs / 60.0)
    snapped = round(minutes * 2.0) / 2.0
    return max(0.5, min(60.0, snapped))


def normalize_race_mode(raw: Any) -> str:
    mode = str(raw or "").strip().lower()
    if mode in VALID_RACE_MODES:
        return mode
    return default_race_mode()


def uses_laps(mode: str) -> bool:
    return normalize_race_mode(mode) in {MODE_LAPS, MODE_DUAL}


def uses_time_limit(mode: str) -> bool:
    return normalize_race_mode(mode) == MODE_VELOS


def ranks_by_velos(mode: str) -> bool:
    return normalize_race_mode(mode) == MODE_VELOS


def show_velos_live(mode: str) -> bool:
    """Floating labels / live UI during the race."""
    return normalize_race_mode(mode) == MODE_VELOS


def show_velos_on_finish(mode: str) -> bool:
    """Show earned Velos on the result label (all modes that finish)."""
    return normalize_race_mode(mode) in {MODE_LAPS, MODE_VELOS, MODE_DUAL}


def live_hud_show_velos(mode: str, *, entry: dict, frozen: bool) -> bool:
    """Whether Velos appear on an ArenaLive sidebar line."""
    if "velos" not in entry:
        return False
    if show_velos_live(mode):
        return True
    # Laps/dual: Velos only after the race (sidebar frozen), including manual Stop.
    if frozen and show_velos_on_finish(mode):
        return True
    return False


def announce_dual_winners(mode: str) -> bool:
    return normalize_race_mode(mode) == MODE_DUAL
