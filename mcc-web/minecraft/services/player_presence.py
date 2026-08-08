# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    player_presence.py
# @note    Query Velocity proxy (glist) / Paper list for session player location.

from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings
from mcrcon import MCRconException

from config.logger_utils import get_logger
from minecraft.services.account_login import is_online_auth_mode
from minecraft.services.rcon_client import parse_online_players, run_command

logger = get_logger("minecraft")

# Minecraft legacy color/formatting codes (§x)
_MC_COLOR_RE = re.compile(r"§.", re.UNICODE)

PRESENCE_PAPER = "paper"
PRESENCE_LIMBO = "limbo"
PRESENCE_OTHER = "other"
PRESENCE_OFFLINE = "offline"
PRESENCE_UNKNOWN = "unknown"

PRESENCE_LABELS_DE = {
    PRESENCE_PAPER: "Am Paper-Server",
    PRESENCE_LIMBO: "Wartet im Warteraum",
    PRESENCE_OTHER: "Anderer Server",
    PRESENCE_OFFLINE: "Nicht verbunden",
    PRESENCE_UNKNOWN: "Status unbekannt",
}


@dataclass(frozen=True)
class PlayerPresence:
    """Where a Microsoft login currently is (proxy / paper)."""

    ms_username: str
    state: str
    server: str = ""

    @property
    def label_de(self) -> str:
        return PRESENCE_LABELS_DE.get(self.state, PRESENCE_LABELS_DE[PRESENCE_UNKNOWN])

    @property
    def on_paper(self) -> bool:
        return self.state == PRESENCE_PAPER

    @property
    def waiting_in_lobby(self) -> bool:
        """True when the player is in the Velocity limbo waiting room."""
        return self.state == PRESENCE_LIMBO


def strip_mc_colors(text: str) -> str:
    return _MC_COLOR_RE.sub("", text or "")


def paper_server_name() -> str:
    return (getattr(settings, "MCC_MINECRAFT_VELOCITY_PAPER_SERVER", None) or "mycyclingcity").strip()


def limbo_server_name() -> str:
    return (getattr(settings, "MCC_MINECRAFT_VELOCITY_LIMBO_SERVER", None) or "limbo").strip()


def parse_glist_players(response: str) -> list[str]:
    """
    Parse Velocity ``glist <server>`` output.

    Example (after stripping colors): ``[mycyclingcity] (1): mccpc01, mccpc02``
    """
    plain = strip_mc_colors(response).strip()
    if not plain or ":" not in plain:
        return []
    names_part = plain.split(":", 1)[1].strip()
    if not names_part:
        return []
    return [part.strip() for part in names_part.split(",") if part.strip()]


def _glist_server(server: str) -> list[str]:
    from minecraft.services.velocity_rcon import send_velocity_command

    name = (server or "").strip()
    if not name:
        return []
    return parse_glist_players(send_velocity_command(f"glist {name}"))


def fetch_proxy_players_by_server() -> dict[str, str]:
    """
    Map lowercased player name → Velocity backend server name.

    Queries configured Paper + Limbo servers via ``glist``.
    """
    mapping: dict[str, str] = {}
    for server in (paper_server_name(), limbo_server_name()):
        if not server:
            continue
        try:
            for player in _glist_server(server):
                mapping[player.lower()] = server
        except (MCRconException, OSError, ValueError) as exc:
            logger.warning(
                "[minecraft_presence] glist failed server=%s error=%s",
                server,
                exc,
            )
            raise
    return mapping


def presence_from_server_map(
    ms_username: str,
    server_map: dict[str, str],
) -> PlayerPresence:
    player = (ms_username or "").strip()
    if not player:
        return PlayerPresence(ms_username="", state=PRESENCE_UNKNOWN)

    server = server_map.get(player.lower(), "")
    if not server:
        return PlayerPresence(ms_username=player, state=PRESENCE_OFFLINE)

    paper = paper_server_name().lower()
    limbo = limbo_server_name().lower()
    if server.lower() == paper:
        state = PRESENCE_PAPER
    elif server.lower() == limbo:
        state = PRESENCE_LIMBO
    else:
        state = PRESENCE_OTHER
    return PlayerPresence(ms_username=player, state=state, server=server)


def fetch_paper_online_names() -> set[str]:
    """Lowercased names from Paper ``list``."""
    response = run_command("list")
    return {name.lower() for name in parse_online_players(response)}


def resolve_player_presence(ms_username: str) -> PlayerPresence:
    """Single-player presence (online mode: proxy glist; authme: paper list)."""
    player = (ms_username or "").strip()
    if not player:
        return PlayerPresence(ms_username="", state=PRESENCE_UNKNOWN)

    if not is_online_auth_mode():
        try:
            online = player.lower() in fetch_paper_online_names()
        except MCRconException as exc:
            logger.warning("[minecraft_presence] paper list failed error=%s", exc)
            return PlayerPresence(ms_username=player, state=PRESENCE_UNKNOWN)
        return PlayerPresence(
            ms_username=player,
            state=PRESENCE_PAPER if online else PRESENCE_OFFLINE,
            server=paper_server_name() if online else "",
        )

    try:
        server_map = fetch_proxy_players_by_server()
    except (MCRconException, OSError, ValueError):
        # Fallback: Paper list only
        try:
            online = player.lower() in fetch_paper_online_names()
        except MCRconException:
            return PlayerPresence(ms_username=player, state=PRESENCE_UNKNOWN)
        return PlayerPresence(
            ms_username=player,
            state=PRESENCE_PAPER if online else PRESENCE_UNKNOWN,
            server=paper_server_name() if online else "",
        )
    presence = presence_from_server_map(player, server_map)
    try:
        if player.lower() in fetch_paper_online_names():
            return PlayerPresence(
                ms_username=player,
                state=PRESENCE_PAPER,
                server=paper_server_name(),
            )
    except MCRconException:
        pass
    return presence


def resolve_presences_for_logins(
    ms_usernames: list[str],
    *,
    paper_override: bool = True,
) -> dict[str, PlayerPresence]:
    """Batch presence lookup keyed by original ms_username string."""
    wanted = [(name or "").strip() for name in ms_usernames if (name or "").strip()]
    if not wanted:
        return {}

    if not is_online_auth_mode():
        try:
            online = fetch_paper_online_names()
        except MCRconException as exc:
            logger.warning("[minecraft_presence] paper list failed error=%s", exc)
            return {
                name: PlayerPresence(ms_username=name, state=PRESENCE_UNKNOWN)
                for name in wanted
            }
        result: dict[str, PlayerPresence] = {}
        for name in wanted:
            on = name.lower() in online
            result[name] = PlayerPresence(
                ms_username=name,
                state=PRESENCE_PAPER if on else PRESENCE_OFFLINE,
                server=paper_server_name() if on else "",
            )
        return result

    try:
        server_map = fetch_proxy_players_by_server()
    except (MCRconException, OSError, ValueError) as exc:
        logger.warning("[minecraft_presence] proxy map failed error=%s", exc)
        # Paper fallback
        try:
            online = fetch_paper_online_names()
        except MCRconException:
            return {
                name: PlayerPresence(ms_username=name, state=PRESENCE_UNKNOWN)
                for name in wanted
            }
        return {
            name: PlayerPresence(
                ms_username=name,
                state=PRESENCE_PAPER if name.lower() in online else PRESENCE_UNKNOWN,
                server=paper_server_name() if name.lower() in online else "",
            )
            for name in wanted
        }

    result = {name: presence_from_server_map(name, server_map) for name in wanted}
    if not paper_override:
        return result
    # After Velocity send, glist can still show limbo while Paper ``list`` already
    # has the player — prefer Paper so abandon-reconcile stays correct.
    try:
        paper_online = fetch_paper_online_names()
    except MCRconException as exc:
        logger.warning("[minecraft_presence] paper override list failed error=%s", exc)
        return result

    paper = paper_server_name()
    for name in wanted:
        if name.lower() in paper_online:
            result[name] = PlayerPresence(
                ms_username=name,
                state=PRESENCE_PAPER,
                server=paper,
            )
    return result
