# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    sidebar_visibility.py
# @note    Route existing Velos sidebar to Bau accounts only (no new objective).

from __future__ import annotations

import re

from django.conf import settings

from config.logger_utils import get_logger
from minecraft.services import rcon_client

logger = get_logger("minecraft")

_DEFAULT_BUILDER_TEAM = "mcc_bau"
_DEFAULT_BUILDER_COLOR = "blue"
_DEFAULT_ARENA_TEAM = "mcc_arena"
_DEFAULT_ARENA_COLOR = "gray"
_DEFAULT_ARENA_AUDIENCE_TAG = "mcc_arena"
_STATION_TEAM_PREFIX = "mcc_"
_STATION_TEAM_MAX_LEN = 16


def builder_team_name() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_SCOREBOARD_BUILDER_TEAM", None)
        or _DEFAULT_BUILDER_TEAM
    ).strip()


def builder_team_color() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_SCOREBOARD_BUILDER_COLOR", None)
        or _DEFAULT_BUILDER_COLOR
    ).strip().lower()


def arena_team_name() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_SCOREBOARD_ARENA_TEAM", None)
        or _DEFAULT_ARENA_TEAM
    ).strip()


def arena_team_color() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_SCOREBOARD_ARENA_COLOR", None)
        or _DEFAULT_ARENA_COLOR
    ).strip().lower()


def arena_audience_tag() -> str:
    """Scoreboard tag for ArenaLive bossbar/actionbar (works with per-station teams)."""
    return (
        getattr(settings, "MCC_MINECRAFT_SCOREBOARD_ARENA_AUDIENCE_TAG", None)
        or _DEFAULT_ARENA_AUDIENCE_TAG
    ).strip() or _DEFAULT_ARENA_AUDIENCE_TAG


def arena_audience_selector() -> str:
    """Target all active Spieler/Reporter sessions (station teams share this tag)."""
    return f"@a[tag={arena_audience_tag()}]"


def builder_sidebar_slot() -> str:
    """Vanilla display slot seen only by players on a team with builder_team_color."""
    return f"sidebar.team.{builder_team_color()}"


def arena_live_sidebar_slot() -> str:
    """Display slot for ArenaLive (spectator/reporter team color)."""
    return f"sidebar.team.{arena_team_color()}"


def builder_station_team_name(team_label: str) -> str:
    """
    Scoreboard team id for a Bau station (tab prefix + blue sidebar color).

    Example: Kette -> mcc_kette (max 16 chars, vanilla-safe).
    """
    slug = re.sub(r"[^a-z0-9]+", "_", (team_label or "").lower()).strip("_")
    if not slug:
        return builder_team_name()
    name = f"{_STATION_TEAM_PREFIX}{slug}"
    return name[:_STATION_TEAM_MAX_LEN]


def builder_station_prefix_text(team_label: str) -> str:
    label = (team_label or "").strip() or "?"
    return f"[{label}] "


def ensure_builder_station_team(team_label: str) -> str:
    """
    Ensure a per-station Bau team with builder color and tab/nametag prefix.

    Returns the scoreboard team name joined by the player.
    """
    label = (team_label or "").strip()
    if not label:
        team = builder_team_name()
        rcon_client.ensure_scoreboard_team(team, color=builder_team_color())
        return team
    team = builder_station_team_name(label)
    rcon_client.ensure_scoreboard_team(
        team,
        color=builder_team_color(),
        prefix=builder_station_prefix_text(label),
    )
    return team


def arena_station_team_name(team_label: str) -> str:
    """
    Scoreboard team id for a Spieler station (tab prefix + gray ArenaLive color).

    Example: Arena1 -> mcc_arena1 (max 16 chars, vanilla-safe).
    """
    slug = re.sub(r"[^a-z0-9]+", "_", (team_label or "").lower()).strip("_")
    if not slug:
        return arena_team_name()
    name = f"{_STATION_TEAM_PREFIX}{slug}"
    return name[:_STATION_TEAM_MAX_LEN]


def arena_station_prefix_text(team_label: str) -> str:
    label = (team_label or "").strip() or "?"
    return f"[{label}] "


def ensure_arena_station_team(team_label: str) -> str:
    """
    Ensure a per-station Arena team with arena color and tab/nametag prefix.

    Returns the scoreboard team name joined by the player.
    """
    label = (team_label or "").strip()
    if not label:
        team = arena_team_name()
        rcon_client.ensure_scoreboard_team(team, color=arena_team_color())
        return team
    team = arena_station_team_name(label)
    rcon_client.ensure_scoreboard_team(
        team,
        color=arena_team_color(),
        prefix=arena_station_prefix_text(label),
    )
    return team


def ensure_sidebar_routing_teams() -> None:
    """Create Bau/Arena scoreboard teams used only for sidebar visibility."""
    rcon_client.ensure_scoreboard_team(builder_team_name(), color=builder_team_color())
    rcon_client.ensure_scoreboard_team(arena_team_name(), color=arena_team_color())


def apply_builder_sidebar_display(objective: str) -> None:
    """
    Show the existing Velos objective only to Bau scoreboard-team members.

    Clears the global sidebar so Arena/Reporter (mcc_arena) do not see it.
    Does not create a second objective or change score entries.
    """
    ensure_sidebar_routing_teams()
    rcon_client.clear_objective_display("sidebar")
    rcon_client.set_objective_display(objective, builder_sidebar_slot())
    logger.info(
        "[minecraft_sidebar] routed objective=%s to slot=%s (builder_team=%s)",
        objective,
        builder_sidebar_slot(),
        builder_team_name(),
    )


def apply_arena_live_display(objective: str) -> None:
    """Ensure ArenaLive objective is routed to the arena spectator sidebar slot."""
    ensure_sidebar_routing_teams()
    rcon_client.ensure_objective(objective, "Velo-Arena LIVE")
    rcon_client.set_objective_display(objective, arena_live_sidebar_slot())
    logger.debug(
        "[minecraft_sidebar] routed objective=%s to slot=%s (arena_team=%s)",
        objective,
        arena_live_sidebar_slot(),
        arena_team_name(),
    )


def clear_arena_live_display(objective: str) -> None:
    """Remove ArenaLive entries and hide the arena sidebar slot."""
    rcon_client.reset_objective_scores(objective)
    rcon_client.clear_objective_display(arena_live_sidebar_slot())


def builder_visibility_commands(login: str, *, team_label: str = "") -> list[str]:
    """
    Join Bau routing team so the player sees the Velos sidebar.

    With team_label (e.g. Kette), joins the station team (same color, tab prefix).
    Without team_label, joins the shared fallback team mcc_bau.
    """
    name = (login or "").strip()
    if not name:
        return []
    label = (team_label or "").strip()
    team = builder_station_team_name(label) if label else builder_team_name()
    return [f"team join {team} {name}"]


def builder_session_intro_commands(login: str, team_label: str) -> list[str]:
    """One-shot tellraw so the player sees Team ↔ login mapping at session start."""
    name = (login or "").strip()
    label = (team_label or "").strip()
    if not name or not label:
        return []
    safe_label = label.replace("\\", "\\\\").replace('"', '\\"')
    return [
        "tellraw "
        f'{name} {{"text":"Du spielst als ","extra":['
        f'{{"text":"{safe_label}","bold":true,"color":"gold"}},'
        '{"text":"."}'
        "]}"
    ]


def arena_visibility_commands(login: str, *, team_label: str = "") -> list[str]:
    """
    Join Arena routing team (ArenaLive via team color) and mark audience tag.

    With team_label (e.g. Arena1), joins the station team (same color, tab prefix).
    Without team_label, joins the shared fallback team mcc_arena.
    """
    name = (login or "").strip()
    if not name:
        return []
    label = (team_label or "").strip()
    team = arena_station_team_name(label) if label else arena_team_name()
    tag = arena_audience_tag()
    return [
        f"tag {name} add {tag}",
        f"team join {team} {name}",
    ]


def clear_visibility_commands(login: str) -> list[str]:
    """Leave scoreboard teams / arena audience tag on session end."""
    name = (login or "").strip()
    if not name:
        return []
    tag = arena_audience_tag()
    return [
        f"tag {name} remove {tag}",
        f"team leave {name}",
    ]
