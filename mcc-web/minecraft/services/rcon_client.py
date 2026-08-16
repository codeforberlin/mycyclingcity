import re
import time
from dataclasses import dataclass

from django.conf import settings
from mcrcon import MCRconException

from config.logger_utils import get_logger
from minecraft.services.arena_motion.locked_rcon import rcon_file_lock
from minecraft.services.thread_safe_mcrcon import ThreadSafeMCRcon


logger = get_logger("minecraft")


@dataclass(frozen=True)
class RconConfig:
    host: str
    port: int
    password: str



def describe_rcon_error(label: str, config: RconConfig, exc: BaseException) -> str:
    """Human-readable RCON failure for admin UI (Paper down, wrong host, timeout)."""
    raw = str(exc)
    low = raw.lower()
    endpoint = f"{config.host}:{config.port}"
    if "111" in raw or "refused" in low:
        return (
            f"{label}-RCON nicht erreichbar ({endpoint}). "
            f"Ist Paper/Proxy gestartet und RCON aktiv?"
        )
    if "timed out" in low or "timeout" in low:
        return f"{label}-RCON Timeout ({endpoint}). Server überlastet oder Host falsch?"
    return f"{label}-RCON Fehler ({endpoint}): {raw}"


def get_rcon_config() -> RconConfig:
    return RconConfig(
        host=settings.MCC_MINECRAFT_RCON_HOST,
        port=settings.MCC_MINECRAFT_RCON_PORT,
        password=settings.MCC_MINECRAFT_RCON_PASSWORD,
    )


def _send_command(command: str) -> str:
    config = get_rcon_config()
    try:
        # Share file lock with arena motion worker so both can coexist on one RCON port.
        with rcon_file_lock():
            with ThreadSafeMCRcon(config.host, config.password, port=config.port) as mcr:
                logger.debug(f"[minecraft_rcon] sending command='{command}'")
                response = mcr.command(command)
                logger.debug(f"[minecraft_rcon] response='{response}'")
                return response
    except (MCRconException, OSError, ConnectionError) as exc:
        msg = describe_rcon_error("Paper", config, exc)
        logger.error(f"[minecraft_rcon] command failed: command='{command}' error={msg}")
        raise MCRconException(msg) from exc


def check_connection() -> tuple[bool, str, str]:
    """
    Returns (ok, message, mode).
    mode: "auth" (RCON login tested) — thread-safe via ThreadSafeMCRcon.
    """
    try:
        _send_command("list")
        return True, "", "auth"
    except Exception as exc:
        return False, str(exc), "auth"


def ensure_objective_numberformat_blank(name: str) -> None:
    """Hide red score column on sidebar (MC 1.20.3+ / Paper)."""
    objective = (name or "").strip()
    if not objective:
        return
    try:
        _send_command(f"scoreboard objectives modify {objective} numberformat blank")
    except MCRconException:
        pass


def ensure_objective(name: str, display_name: str | None = None) -> None:
    display = (display_name or name).replace('"', '\\"')
    objective = (name or "").strip()
    if not objective:
        return
    try:
        _send_command(f'scoreboard objectives add {objective} dummy "{display}"')
    except MCRconException:
        pass
    # add does not raise when the objective already exists — always sync displayname.
    _send_command(f'scoreboard objectives modify {objective} displayname "{display}"')


VALID_TEAM_COLORS = frozenset(
    {
        "black",
        "dark_blue",
        "dark_green",
        "dark_aqua",
        "dark_red",
        "dark_purple",
        "gold",
        "gray",
        "dark_gray",
        "blue",
        "green",
        "aqua",
        "red",
        "light_purple",
        "yellow",
        "white",
    }
)

VALID_DISPLAY_SLOTS = frozenset(
    {
        "list",
        "sidebar",
        "below_name",
        # Legacy aliases (kept for compatibility)
        "team_black",
        "team_dark_blue",
        "team_dark_green",
        "team_dark_aqua",
        "team_dark_red",
        "team_dark_purple",
        "team_gold",
        "team_gray",
        "team_dark_gray",
        "team_blue",
        "team_green",
        "team_aqua",
        "team_red",
        "team_light_purple",
        "team_yellow",
        "team_white",
        # Modern Paper/Vanilla: sidebar.team.<color>
        *(f"sidebar.team.{color}" for color in VALID_TEAM_COLORS),
    }
)


def set_objective_display(objective: str, slot: str = "sidebar") -> None:
    """Show an objective in a scoreboard slot (e.g. sidebar or sidebar.team.blue)."""
    normalized = (slot or "sidebar").strip().lower()
    if normalized not in VALID_DISPLAY_SLOTS:
        raise ValueError(f"Invalid scoreboard display slot: {slot}")
    logger.debug(
        f"[minecraft_rcon] set_objective_display objective={objective} slot={normalized}"
    )
    _send_command(f"scoreboard objectives setdisplay {normalized} {objective}")


def clear_objective_display(slot: str = "sidebar") -> None:
    """Hide whatever objective is shown in a scoreboard slot (empty setdisplay)."""
    normalized = (slot or "sidebar").strip().lower()
    if normalized not in VALID_DISPLAY_SLOTS:
        raise ValueError(f"Invalid scoreboard display slot: {slot}")
    logger.debug(f"[minecraft_rcon] clear_objective_display slot={normalized}")
    _send_command(f"scoreboard objectives setdisplay {normalized}")


def set_scoreboard_team_prefix(team: str, prefix_text: str) -> None:
    """Set the tab/nametag prefix for a scoreboard team (JSON text component)."""
    name = (team or "").strip()
    if not name:
        raise ValueError("scoreboard team name is empty")
    safe = (prefix_text or "").replace("\\", "\\\\").replace('"', '\\"')
    _send_command(f'team modify {name} prefix {{"text":"{safe}"}}')


def ensure_scoreboard_team(
    team: str,
    *,
    color: str | None = None,
    prefix: str | None = None,
) -> None:
    """Create a vanilla scoreboard team (idempotent); optionally set color and prefix."""
    name = (team or "").strip()
    if not name:
        raise ValueError("scoreboard team name is empty")
    try:
        _send_command(f"team add {name}")
    except Exception:
        # Team already exists, or server returned a non-fatal error via mcrcon.
        pass
    if color:
        color_norm = color.strip().lower()
        if color_norm not in VALID_TEAM_COLORS:
            raise ValueError(f"Invalid scoreboard team color: {color}")
        _send_command(f"team modify {name} color {color_norm}")
    if prefix is not None:
        set_scoreboard_team_prefix(name, prefix)


def join_scoreboard_team(team: str, player: str) -> None:
    name = (team or "").strip()
    player_name = (player or "").strip()
    if not name or not player_name:
        raise ValueError("team and player are required")
    _send_command(f"team join {name} {player_name}")


def leave_scoreboard_team(player: str) -> None:
    player_name = (player or "").strip()
    if not player_name:
        raise ValueError("player is required")
    _send_command(f"team leave {player_name}")


def set_player_score(player: str, objective: str, value: int) -> None:
    logger.debug(f"[minecraft_rcon] set_player_score player={player} objective={objective} value={value}")
    _send_command(f"scoreboard players set {player} {objective} {int(value)}")


def add_player_score(player: str, objective: str, value: int) -> None:
    logger.debug(f"[minecraft_rcon] add_player_score player={player} objective={objective} delta={value}")
    _send_command(f"scoreboard players add {player} {objective} {int(value)}")


def reset_player_score(player: str, objective: str) -> None:
    logger.debug(
        f"[minecraft_rcon] reset_player_score player={player} objective={objective}"
    )
    _send_command(f"scoreboard players reset {player} {objective}")


def reset_objective_scores(objective: str) -> None:
    """Clear all fake-player entries for one objective."""
    name = (objective or "").strip()
    if not name:
        raise ValueError("objective is required")
    logger.debug(f"[minecraft_rcon] reset_objective_scores objective={name}")
    _send_command(f"scoreboard players reset * {name}")


def run_command(command: str) -> str:
    """Execute a single RCON command and return the server response."""
    return _send_command(command.strip())


def _response_indicates_failure(response: str | None) -> bool:
    text = (response or "").lower()
    if not text:
        return False
    failure_markers = (
        "error executing",
        "expected integer",
        "invalid integer",
        "unknown command",
        "incorrect argument",
        "fehler",
    )
    if any(marker in text for marker in failure_markers):
        return True
    return text.startswith("expected ") or "<--[here]" in text


def run_commands(commands: list[str], *, stop_on_error: bool = True) -> tuple[bool, str]:
    """
    Execute RCON commands in order.

    Returns (success, formatted log). Stops on the first failing command unless
    stop_on_error is False.
    """
    log_lines: list[str] = []
    had_error = False
    for raw in commands:
        command = (raw or "").strip()
        if not command:
            continue
        try:
            response = run_command(command)
            log_lines.append(f"{command} -> {response or '(ok)'}")
            if stop_on_error and _response_indicates_failure(response):
                return False, "\n".join(log_lines)
        except MCRconException as exc:
            log_lines.append(f"{command} -> FEHLER: {exc}")
            had_error = True
            if stop_on_error:
                return False, "\n".join(log_lines)
    if not log_lines:
        return True, "(keine Befehle)"
    return not had_error, "\n".join(log_lines)


def parse_online_players(list_response: str) -> list[str]:
    """Parse Minecraft ``list`` response into bare player names.

    Scoreboard team prefixes appear as ``[Prefix] name`` (e.g. ``[Dynamo] mccpc01``).
    Those decorations are stripped so ``is_player_online("mccpc01")`` works.
    """
    text = (list_response or "").strip()
    if not text or ":" not in text:
        return []
    names_part = text.split(":", 1)[1].strip()
    if not names_part:
        return []
    return [
        _strip_list_name_decoration(part)
        for part in names_part.split(",")
        if _strip_list_name_decoration(part)
    ]


def _strip_list_name_decoration(name: str) -> str:
    """Remove scoreboard team prefixes from a ``list`` entry."""
    text = re.sub(r"§.", "", (name or "").strip())
    while text.startswith("["):
        end = text.find("]")
        if end < 0:
            break
        text = text[end + 1 :].strip()
    return text


def is_player_online(player: str) -> bool:
    name = (player or "").strip().lower()
    if not name:
        return False
    online = [p.lower() for p in parse_online_players(run_command("list"))]
    return name in online


def wait_for_player_online(
    player: str,
    *,
    timeout_sec: float | None = None,
    interval_sec: float | None = None,
) -> bool:
    """
    Poll ``list`` until the player is online or timeout.

    Velocity send / AuthMe forcelogin are asynchronous: the client often needs
    a mouse click / focus before the player entity appears on Paper.
    """
    name = (player or "").strip()
    if not name:
        return False
    timeout = timeout_sec
    if timeout is None:
        timeout = float(getattr(settings, "MCC_MINECRAFT_SESSION_LOGIN_WAIT_SECONDS", 45))
    interval = interval_sec
    if interval is None:
        interval = float(getattr(settings, "MCC_MINECRAFT_SESSION_LOGIN_POLL_SECONDS", 0.25))
    deadline = time.monotonic() + max(0.0, float(timeout))
    while True:
        try:
            if is_player_online(name):
                return True
        except MCRconException as exc:
            logger.warning(
                "[minecraft_rcon] wait_for_player list failed player=%s error=%s",
                name,
                exc,
            )
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.05, float(interval)))


def response_indicates_missing_player(response: str) -> bool:
    text = (response or "").lower()
    return "no player was found" in text or "no entity was found" in text


def run_commands_require_player(
    commands: list[str],
    *,
    player: str,
    retries: int = 5,
    retry_delay_sec: float = 0.35,
) -> tuple[bool, str]:
    """
    Run player-targeting commands; retry when the server reports the player missing.
    """
    log_lines: list[str] = []
    name = (player or "").strip()
    remaining = list(commands)
    attempt = 0
    while remaining:
        command = (remaining[0] or "").strip()
        if not command:
            remaining.pop(0)
            continue
        try:
            response = run_command(command)
        except MCRconException as exc:
            log_lines.append(f"{command} -> FEHLER: {exc}")
            return False, "\n".join(log_lines)
        if response_indicates_missing_player(response):
            attempt += 1
            log_lines.append(f"{command} -> {response} (retry {attempt}/{retries})")
            if attempt > retries:
                return False, "\n".join(log_lines)
            if not wait_for_player_online(
                name,
                timeout_sec=max(1.0, retry_delay_sec * 4),
                interval_sec=retry_delay_sec,
            ):
                time.sleep(retry_delay_sec)
            continue
        log_lines.append(f"{command} -> {response or '(ok)'}")
        remaining.pop(0)
        attempt = 0
    if not log_lines:
        return True, "(keine Befehle)"
    return True, "\n".join(log_lines)


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
