# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    account_login.py
# @note    Resolve Microsoft online login vs internal team/slot names.

from __future__ import annotations

from django.conf import settings

from minecraft.models import MCSession, MinecraftPlayAccount, MinecraftTeamRegistration


def session_auth_mode() -> str:
    mode = (getattr(settings, "MCC_MINECRAFT_SESSION_AUTH_MODE", "online") or "online").strip().lower()
    return mode if mode in {"online", "authme"} else "online"


def is_online_auth_mode() -> bool:
    return session_auth_mode() == "online"


def resolve_builder_online_login(registration: MinecraftTeamRegistration) -> str:
    """Return the RCON/proxy target for a builder registration."""
    ms = (registration.ms_username or "").strip()
    if ms:
        return ms
    if is_online_auth_mode():
        return ""
    return (registration.mc_username or "").strip()


def resolve_player_online_login(account: MinecraftPlayAccount) -> str:
    ms = (account.ms_username or "").strip()
    if ms:
        return ms
    if is_online_auth_mode():
        return ""
    return (account.short_name or "").strip()


def session_rcon_login(session: MCSession) -> str:
    """Player name used for Paper RCON during an active session."""
    ms = (session.ms_username or "").strip()
    if ms:
        return ms
    return (session.account_name or "").strip()


VALID_PLAY_GAMEMODES = frozenset(
    {
        MCSession.GAMEMODE_SURVIVAL,
        MCSession.GAMEMODE_ADVENTURE,
        MCSession.GAMEMODE_SPECTATOR,
    }
)


def normalize_play_gamemode(value: str | None) -> str | None:
    mode = (value or "").strip().lower()
    if mode in VALID_PLAY_GAMEMODES:
        return mode
    return None


def preferred_gamemode_for_account(
    account_type: str,
    *,
    prefer_gamemode: str = "",
    prefer_spectator: bool = False,
) -> str:
    """Initial play_gamemode when starting a session (always adventure unless overridden)."""
    explicit = normalize_play_gamemode(prefer_gamemode)
    if explicit:
        return explicit
    if prefer_spectator:
        return MCSession.GAMEMODE_SPECTATOR
    # Play and builder sessions both start in adventure; supervisors switch via Session GUI.
    return MCSession.GAMEMODE_ADVENTURE
