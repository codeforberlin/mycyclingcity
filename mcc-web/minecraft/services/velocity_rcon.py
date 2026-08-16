# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    velocity_rcon.py
# @note    Velocircon client for proxy send (limbo ↔ paper).

from __future__ import annotations

from django.conf import settings
from mcrcon import MCRconException

from config.logger_utils import get_logger
from minecraft.services.rcon_client import RconConfig, describe_rcon_error
from minecraft.services.thread_safe_mcrcon import ThreadSafeMCRcon

logger = get_logger("minecraft")


def get_velocity_rcon_config() -> RconConfig:
    return RconConfig(
        host=settings.MCC_MINECRAFT_VELOCITY_RCON_HOST,
        port=int(settings.MCC_MINECRAFT_VELOCITY_RCON_PORT),
        password=settings.MCC_MINECRAFT_VELOCITY_RCON_PASSWORD,
    )


def check_connection() -> tuple[bool, str, str]:
    """
    Probe Velocircon (Velocity proxy RCON).

    Returns ``(ok, message, mode)`` where mode is ``auth`` (login + command).
    Uses ThreadSafeMCRcon so this works under Gunicorn gthread workers.
    """
    try:
        send_velocity_command("glist")
        return True, "", "auth"
    except Exception as exc:
        return False, str(exc), "auth"


def send_velocity_command(command: str) -> str:
    config = get_velocity_rcon_config()
    try:
        with ThreadSafeMCRcon(config.host, config.password, port=config.port) as mcr:
            logger.debug("[minecraft_velocity_rcon] sending command='%s'", command)
            response = mcr.command(command)
            logger.debug("[minecraft_velocity_rcon] response='%s'", response)
            return response or ""
    except (MCRconException, OSError, ConnectionError) as exc:
        msg = describe_rcon_error("Velocity", config, exc)
        logger.error(
            "[minecraft_velocity_rcon] command failed: command='%s' error=%s",
            command,
            msg,
        )
        raise MCRconException(msg) from exc


def send_player_to_server(ms_username: str, server_name: str) -> str:
    """Velocity: send <player> <server> via Velocircon."""
    player = (ms_username or "").strip()
    server = (server_name or "").strip()
    if not player or not server:
        raise ValueError("ms_username and server_name are required")
    return send_velocity_command(f"send {player} {server}")


def send_player_to_paper(ms_username: str) -> str:
    server = getattr(settings, "MCC_MINECRAFT_VELOCITY_PAPER_SERVER", "mycyclingcity")
    return send_player_to_server(ms_username, server)


def send_player_to_limbo(ms_username: str) -> str:
    server = getattr(settings, "MCC_MINECRAFT_VELOCITY_LIMBO_SERVER", "limbo")
    return send_player_to_server(ms_username, server)


def glist_server(server_name: str) -> str:
    """Raw Velocity ``glist <server>`` response."""
    server = (server_name or "").strip()
    if not server:
        raise ValueError("server_name is required")
    return send_velocity_command(f"glist {server}")
