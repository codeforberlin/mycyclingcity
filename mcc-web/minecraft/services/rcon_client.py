import re
import socket
import threading
from dataclasses import dataclass

from django.conf import settings
from mcrcon import MCRcon, MCRconException

from config.logger_utils import get_logger


logger = get_logger("minecraft")


@dataclass(frozen=True)
class RconConfig:
    host: str
    port: int
    password: str


def get_rcon_config() -> RconConfig:
    return RconConfig(
        host=settings.MCC_MINECRAFT_RCON_HOST,
        port=settings.MCC_MINECRAFT_RCON_PORT,
        password=settings.MCC_MINECRAFT_RCON_PASSWORD,
    )


def _send_command(command: str) -> str:
    config = get_rcon_config()
    try:
        with MCRcon(config.host, config.password, port=config.port) as mcr:
            logger.debug(f"[minecraft_rcon] sending command='{command}'")
            response = mcr.command(command)
            logger.debug(f"[minecraft_rcon] response='{response}'")
            return response
    except MCRconException as exc:
        logger.error(f"[minecraft_rcon] command failed: command='{command}' error={exc}")
        raise


def check_connection() -> tuple[bool, str, str]:
    """
    Returns (ok, message, mode).
    mode: "auth" (RCON login tested) or "port" (TCP port reachability only).
    """
    if threading.current_thread() is not threading.main_thread():
        try:
            config = get_rcon_config()
            with socket.create_connection((config.host, config.port), timeout=3):
                return True, "", "port"
        except Exception as exc:
            return False, str(exc), "port"
    try:
        _send_command("list")
        return True, "", "auth"
    except Exception as exc:
        return False, str(exc), "auth"


def ensure_objective(name: str, display_name: str | None = None) -> None:
    display = display_name or name
    _send_command(f'scoreboard objectives add {name} dummy "{display}"')


def set_player_score(player: str, objective: str, value: int) -> None:
    logger.debug(f"[minecraft_rcon] set_player_score player={player} objective={objective} value={value}")
    _send_command(f"scoreboard players set {player} {objective} {int(value)}")


def add_player_score(player: str, objective: str, value: int) -> None:
    logger.debug(f"[minecraft_rcon] add_player_score player={player} objective={objective} delta={value}")
    _send_command(f"scoreboard players add {player} {objective} {int(value)}")


def get_player_score(player: str, objective: str) -> int | None:
    response = _send_command(f"scoreboard players get {player} {objective}")
    if not response:
        logger.debug(f"[minecraft_rcon] get_player_score player={player} objective={objective} response=empty")
        return None
    match = re.search(r"(-?\d+)", response)
    if not match:
        logger.warning(f"[minecraft_rcon] unexpected response for player={player} objective={objective}: {response}")
        return None
    value = int(match.group(1))
    logger.debug(f"[minecraft_rcon] get_player_score player={player} objective={objective} value={value}")
    return value
