# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    player_session_bootstrap.py
# @note    Auto-run world preset for player sessions; adventure mode is forced after login.

from __future__ import annotations

from django.conf import settings

from config.logger_utils import get_logger
from minecraft.models import MinecraftRconPreset
from minecraft.rcon_preset_defaults import PLAYER_SESSION_BOOTSTRAP_PRESET
from minecraft.services.preset_commands import normalize_preset_commands

logger = get_logger("minecraft")


def player_bootstrap_enabled() -> bool:
    return bool(getattr(settings, "MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED", True))


def player_bootstrap_preset_slug() -> str:
    slug = getattr(settings, "MCC_MINECRAFT_PLAYER_BOOTSTRAP_PRESET_SLUG", "") or ""
    return slug or PLAYER_SESSION_BOOTSTRAP_PRESET["slug"]


def get_bootstrap_preset_commands() -> list[str]:
    """Return RCON commands from the configured player bootstrap preset (DB or default)."""
    slug = player_bootstrap_preset_slug()
    try:
        preset = MinecraftRconPreset.objects.get(slug=slug, enabled=True)
        commands = list(preset.commands or [])
    except MinecraftRconPreset.DoesNotExist:
        logger.warning(
            "[player_session_bootstrap] preset slug=%s missing, using defaults",
            slug,
        )
        commands = list(PLAYER_SESSION_BOOTSTRAP_PRESET["commands"])
    return normalize_preset_commands(commands)


def build_player_world_commands() -> list[str]:
    """World/gamerule commands only (no player-targeting commands)."""
    if not player_bootstrap_enabled():
        return []
    return get_bootstrap_preset_commands()


def build_player_post_login_commands(
    login: str,
    *,
    emerald_count: int,
    spectator: bool = False,
    gamemode: str | None = None,
    team_label: str | None = None,
    world_ticket_count: int = 0,
) -> list[str]:
    """Commands that require the player entity to exist (after login settles)."""
    from minecraft.services.gamemode_control import gamemode_command, play_gamemode_for_type
    from minecraft.services.sidebar_visibility import (
        arena_visibility_commands,
        ensure_arena_station_team,
    )
    from minecraft.models import MCSession
    from minecraft.services.account_login import normalize_play_gamemode
    from minecraft.services.world_tickets import build_world_ticket_give_command

    name = (login or "").strip()
    label = (team_label if team_label is not None else name).strip()
    mode = normalize_play_gamemode(gamemode) or play_gamemode_for_type(
        MCSession.ACCOUNT_PLAYER, spectator=spectator
    )
    # Ensure station team (color + tab prefix) before join — same label as Bau stations.
    if label:
        ensure_arena_station_team(label)
    commands = [gamemode_command(name, mode)]
    if emerald_count > 0 and mode != MCSession.GAMEMODE_SPECTATOR:
        commands.append(f"give {name} minecraft:emerald {emerald_count}")
    if world_ticket_count > 0 and mode != MCSession.GAMEMODE_SPECTATOR:
        ticket_cmd = build_world_ticket_give_command(name, world_ticket_count)
        if ticket_cmd:
            commands.append(ticket_cmd)
    # Arena/Reporter: ArenaLive via team color; tab prefix via station team.
    commands.extend(arena_visibility_commands(name, team_label=label))
    return commands


def build_player_session_start_commands(
    login: str,
    *,
    emerald_count: int,
    world_ticket_count: int = 0,
) -> list[str]:
    """
    Conceptual full RCON sequence for starting a player session.

    Runtime orchestration in session_control waits for the player after forcelogin,
    because AuthMe joins asynchronously.
    """
    name = (login or "").strip()
    commands: list[str] = []
    commands.extend(build_player_world_commands())
    commands.append(f"authme forcelogin {name}")
    commands.extend(
        build_player_post_login_commands(
            name,
            emerald_count=emerald_count,
            team_label=name,
            world_ticket_count=world_ticket_count,
        )
    )
    return commands
