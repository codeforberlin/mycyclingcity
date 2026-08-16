# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    session_control.py
# @note    Start/end/extend Minecraft play and builder sessions (online or AuthMe).

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MCSession, MinecraftIntegrationConfig, MinecraftPlayAccount, MinecraftTeamRegistration
from minecraft.services.account_login import (
    is_online_auth_mode,
    preferred_gamemode_for_account,
    resolve_builder_online_login,
    resolve_player_online_login,
    session_rcon_login,
)
from minecraft.services.gamemode_control import apply_play_gamemode_fields, gamemode_command
from minecraft.services.rcon_client import (
    is_player_online,
    run_commands,
    run_commands_require_player,
    wait_for_player_online,
)

logger = get_logger("minecraft")

DEFAULT_SESSION_LOGIN_WAIT_SECONDS = 45.0
MIN_SESSION_LOGIN_WAIT_SECONDS = 5.0


def _session_login_wait_seconds() -> float:
    """How long Freigabe waits for the player entity after Velocity send / AuthMe."""
    try:
        raw = float(MinecraftIntegrationConfig.get_config().session_login_wait_seconds)
    except (TypeError, ValueError, AttributeError):
        raw = float(
            getattr(
                settings,
                "MCC_MINECRAFT_SESSION_LOGIN_WAIT_SECONDS",
                DEFAULT_SESSION_LOGIN_WAIT_SECONDS,
            )
        )
    return max(MIN_SESSION_LOGIN_WAIT_SECONDS, raw)


class SessionControlError(Exception):
    """Base error for session control failures."""

    code = "session_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class AccountAlreadyActiveError(SessionControlError):
    code = "already_active"


class AccountNotFoundError(SessionControlError):
    code = "not_found"


class SessionNotActiveError(SessionControlError):
    code = "not_active"


class RconSequenceError(SessionControlError):
    code = "rcon_failed"


class MissingMicrosoftLoginError(SessionControlError):
    code = "missing_ms_login"


class MsAllowlistError(SessionControlError):
    code = "ms_not_allowed"


class StationBusyError(SessionControlError):
    code = "station_busy"


class InsufficientVelosError(SessionControlError):
    code = "insufficient_velos"


def _resolve_session_online_login(
    *,
    default_login: str,
    ms_username_override: str | None,
    station,
    require_allowlist: bool,
) -> str:
    """Pick session MS login (override or default) and enforce allowlist when active."""
    override = (ms_username_override or "").strip()
    online_login = override or (default_login or "").strip()
    if not online_login:
        return ""
    if require_allowlist:
        from minecraft.services.station_admin import StationAdminError, assert_ms_login_allowed

        try:
            return assert_ms_login_allowed(online_login, station=station)
        except StationAdminError as exc:
            raise MsAllowlistError(str(exc), code=exc.code) from exc
    return online_login


def _resolve_start_station(station_id, *, role: str):
    if station_id in (None, ""):
        return None
    from minecraft.services.station_admin import StationAdminError, resolve_station_for_session

    try:
        return resolve_station_for_session(station_id, role=role)
    except StationAdminError as exc:
        if exc.code == "station_busy":
            raise StationBusyError(str(exc), code=exc.code) from exc
        raise SessionControlError(str(exc), code=exc.code) from exc


def _player_duration_default() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_PLAYER_SESSION_MINUTES", 15))


def _builder_duration_default() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_BUILDER_SESSION_MINUTES", 90))


def _add_time_minutes_default() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_SESSION_ADD_MINUTES", 15))


def resolve_player_duration(
    account: MinecraftPlayAccount,
    *,
    override: int | None = None,
) -> int | None:
    """Return minutes, or None for an unlimited (no timeout) session."""
    if override is not None:
        return int(override)
    if getattr(account, "session_unlimited", False):
        return None
    if account.session_duration_minutes is not None:
        return int(account.session_duration_minutes)
    return _player_duration_default()


def resolve_builder_duration(
    registration: MinecraftTeamRegistration,
    *,
    override: int | None = None,
) -> int | None:
    """Return minutes, or None for an unlimited (no timeout) session."""
    if override is not None:
        return int(override)
    if getattr(registration, "session_unlimited", False):
        return None
    if registration.session_duration_minutes is not None:
        return int(registration.session_duration_minutes)
    return _builder_duration_default()


def _session_timing(minutes: int | None) -> tuple[int, datetime | None]:
    """Map resolved duration to (duration_minutes, ends_at). None = unlimited."""
    now = timezone.now()
    if minutes is None:
        return 0, None
    if minutes < 1:
        raise SessionControlError("duration must be >= 1", code="invalid_duration")
    return int(minutes), now + timedelta(minutes=int(minutes))


def resolve_player_add_time(account: MinecraftPlayAccount) -> int:
    if account.add_time_minutes is not None:
        return int(account.add_time_minutes)
    return _add_time_minutes_default()


def resolve_builder_add_time(registration: MinecraftTeamRegistration) -> int:
    if registration.add_time_minutes is not None:
        return int(registration.add_time_minutes)
    return _add_time_minutes_default()


def resolve_add_time_for_session(
    session: MCSession,
    *,
    override: int | None = None,
) -> int:
    if override is not None:
        return int(override)
    name = session.account_name
    if session.account_type == MCSession.ACCOUNT_PLAYER:
        account = MinecraftPlayAccount.objects.filter(short_name__iexact=name).first()
        if account is not None:
            return resolve_player_add_time(account)
    elif session.account_type == MCSession.ACCOUNT_BUILDER:
        registration = MinecraftTeamRegistration.objects.filter(mc_username__iexact=name).first()
        if registration is not None:
            return resolve_builder_add_time(registration)
    return _add_time_minutes_default()


def _emerald_count() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_PLAYER_START_EMERALDS", 4))


def _normalize_world_ticket_count(raw) -> int:
    from minecraft.services.world_tickets import normalize_ticket_count

    return normalize_ticket_count(raw)


def _debit_world_tickets_if_needed(
    *,
    account_name: str,
    queue_type: str,
    ticket_count: int,
    user=None,
) -> None:
    """Deduct Velos when an ASSIGNED waitlist entry has a linked cyclist."""
    if ticket_count < 1:
        return
    from minecraft.services.world_tickets import (
        debit_world_tickets_for_cyclist,
        resolve_waitlist_cyclist,
        ticket_cost_velos,
    )

    cyclist = resolve_waitlist_cyclist(account_name, account_type=queue_type)
    if cyclist is None:
        return
    result = debit_world_tickets_for_cyclist(
        cyclist,
        ticket_count,
        user=user,
    )
    if not result.success:
        cost = ticket_cost_velos(ticket_count)
        raise InsufficientVelosError(
            result.message
            or f"Nicht genug Velos für {ticket_count} Ticket(s) ({cost} Velos).",
            code="insufficient_velos",
        )


def _assert_world_ticket_balance(
    *,
    account_name: str,
    queue_type: str,
    ticket_count: int,
) -> None:
    """Fail fast if a linked cyclist cannot afford the selected tickets."""
    if ticket_count < 1:
        return
    from minecraft.services.world_tickets import (
        resolve_waitlist_cyclist,
        ticket_cost_velos,
    )

    cyclist = resolve_waitlist_cyclist(account_name, account_type=queue_type)
    if cyclist is None:
        return
    cost = ticket_cost_velos(ticket_count)
    balance = int(cyclist.velos_balance or 0)
    if balance < cost:
        raise InsufficientVelosError(
            f"Nur {balance} Velos verfügbar, {cost} für {ticket_count} Ticket(s) benötigt.",
            code="insufficient_velos",
        )


def _format_coord(value: float) -> str:
    """Format coordinates without trailing .0 when whole numbers."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def resolve_world_spawn_xyz() -> tuple[float, float, float]:
    """
    World spawn for session teleports.

    Prefer spawn-x/y/z from Paper server.properties; fall back to
    MCC_MINECRAFT_LOBBY_* settings.
    """
    x = float(getattr(settings, "MCC_MINECRAFT_LOBBY_X", 0) or 0)
    y = float(getattr(settings, "MCC_MINECRAFT_LOBBY_Y", 64) or 64)
    z = float(getattr(settings, "MCC_MINECRAFT_LOBBY_Z", 0) or 0)
    try:
        from minecraft.services.world_border import read_world_spawn_xyz

        spawn = read_world_spawn_xyz()
        if spawn is not None:
            return spawn
    except Exception as exc:
        logger.debug("[minecraft_session] world spawn read failed: %s", exc)
    return x, y, z


def spawn_offset_spacing() -> float:
    """Horizontal spacing (blocks) between simultaneous spawn teleports."""
    try:
        return max(1.0, float(getattr(settings, "MCC_MINECRAFT_SPAWN_OFFSET_SPACING", 3.0) or 3.0))
    except (TypeError, ValueError):
        return 3.0


def spawn_offset_xz(
    index: int = 0,
    *,
    spacing: float | None = None,
) -> tuple[float, float]:
    """
    Offset around world spawn so multiple players don't stack.

    Index 0 stays on the exact spawn; further indices are placed on a line
    along +X then alternate ±X / ±Z in a cross+ring pattern with clear spacing.
    """
    step = spawn_offset_spacing() if spacing is None else max(1.0, float(spacing))
    i = max(0, int(index))
    if i == 0:
        return 0.0, 0.0
    # Deterministic, easy-to-verify layout:
    # 1:(+s,0) 2:(-s,0) 3:(0,+s) 4:(0,-s) 5:(+s,+s) 6:(+s,-s) 7:(-s,+s) 8:(-s,-s)
    # then radius 2 with same pattern scaled, etc.
    pattern = (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )
    slot = i - 1
    radius = slot // len(pattern) + 1
    dx, dz = pattern[slot % len(pattern)]
    return dx * step * radius, dz * step * radius


def world_spawn_tp_command(
    player_name: str,
    *,
    offset_index: int = 0,
) -> str:
    """
    RCON: teleport player onto solid ground at world/lobby spawn XZ.

    Uses ``positioned over world_surface`` so a high default lobby Y (e.g. 64)
    does not drop the player from mid-air. Optional grid offset spreads players.
    """
    x, _y, z = resolve_world_spawn_xyz()
    dx, dz = spawn_offset_xz(offset_index)
    px = _format_coord(x + dx)
    pz = _format_coord(z + dz)
    name = (player_name or "").strip()
    cmd = (
        f"execute as {name} positioned {px} 0 {pz} "
        f"positioned over world_surface run tp @s ~ ~ ~"
    )
    logger.info(
        "[minecraft_session] spawn_tp player=%s offset=%s dx=%s dz=%s cmd=%s",
        name,
        offset_index,
        dx,
        dz,
        cmd,
    )
    return cmd


def region_spawn_xyz(region) -> tuple[float, float, float]:
    """
    Session teleport target for a protected region.

    Prefer explicit spawn_x/y/z when set; otherwise horizontal cuboid center
    with a safe Y (world spawn Y for tall regions, near-floor for short bands).
    """
    if getattr(region, "has_custom_spawn", False):
        # Stand in the middle of the target block.
        return (
            float(region.spawn_x) + 0.5,
            float(region.spawn_y),
            float(region.spawn_z) + 0.5,
        )

    min_x, min_y, min_z, max_x, max_y, max_z = region.normalized_bounds()
    x = (min_x + max_x) / 2.0 + 0.5
    z = (min_z + max_z) / 2.0 + 0.5
    height = int(max_y) - int(min_y)
    if height <= 32:
        y = float(min_y + 2)
        if y > max_y:
            y = (float(min_y) + float(max_y)) / 2.0
    else:
        _wx, world_y, _wz = resolve_world_spawn_xyz()
        y = float(world_y)
        if y < min_y:
            y = float(min_y + 2)
        if y > max_y:
            y = float(max_y) - 1.0 if max_y > min_y else float(max_y)
        if y < min_y:
            y = float(min_y)
    return x, y, z


def region_spawn_tp_command(player_name: str, region) -> str:
    """RCON: teleport player to the center of a protected region cuboid."""
    x, y, z = region_spawn_xyz(region)
    cmd = (
        f"tp {player_name} {_format_coord(x)} {_format_coord(y)} {_format_coord(z)}"
    )
    logger.info(
        "[minecraft_session] region_spawn_tp player=%s region=%s xyz=(%s,%s,%s) cmd=%s",
        player_name,
        getattr(region, "region_id", "?"),
        x,
        y,
        z,
        cmd,
    )
    return cmd


def resolve_builder_spawn_region(registration, region_pk: int | str | None):
    """
    Return the protected region if ``registration`` is a builder member.
    Raises SessionControlError if pk given but not allowed / missing.
    """
    if region_pk is None or region_pk == "":
        return None
    try:
        pk = int(region_pk)
    except (TypeError, ValueError) as exc:
        raise SessionControlError(
            f"Invalid spawn region id: {region_pk}",
            code="invalid_spawn_region",
        ) from exc
    from minecraft.models import MinecraftProtectedRegion

    region = (
        MinecraftProtectedRegion.objects.filter(pk=pk, builders=registration)
        .select_related("parent")
        .first()
    )
    if region is None:
        raise SessionControlError(
            f"Spawn region not allowed for builder {registration.mc_username}",
            code="spawn_region_forbidden",
        )
    return region


def _active_session_for(account_name: str) -> MCSession | None:
    return (
        MCSession.objects.select_for_update()
        .filter(account_name__iexact=account_name, status=MCSession.STATUS_ACTIVE)
        .first()
    )


def get_active_session(account_name: str) -> MCSession | None:
    return MCSession.objects.filter(
        account_name__iexact=account_name,
        status=MCSession.STATUS_ACTIVE,
    ).first()


def _run_or_raise(commands: list[str]) -> str:
    ok, log = run_commands(commands, stop_on_error=True)
    if not ok:
        raise RconSequenceError(log)
    return log


def _run_player_effects_or_raise(commands: list[str], *, player: str) -> str:
    ok, log = run_commands_require_player(commands, player=player)
    if not ok:
        raise RconSequenceError(log)
    return log


PENDING_BOOTSTRAP_PREFIX = "PENDING_BOOTSTRAP:"


def _bring_player_online(online_login: str) -> str:
    """AuthMe forcelogin or Velocity send to Paper, then wait until entity exists."""
    logs: list[str] = []
    logs.append(_transfer_player_to_game(online_login))
    if not wait_for_player_online(online_login, timeout_sec=_session_login_wait_seconds()):
        raise RconSequenceError(
            f"Player {online_login} did not come online after "
            f"{'Velocity send' if is_online_auth_mode() else 'authme forcelogin'}"
        )
    return "\n".join(logs)


def _transfer_player_to_game(online_login: str) -> str:
    """Velocity send / AuthMe forcelogin only (no wait for entity)."""
    if is_online_auth_mode():
        from minecraft.services.velocity_rcon import send_player_to_paper
        from mcrcon import MCRconException

        try:
            return send_player_to_paper(online_login)
        except (MCRconException, OSError, ValueError) as exc:
            raise RconSequenceError(f"Velocity send failed for {online_login}: {exc}") from exc
    return _run_or_raise([f"authme forcelogin {online_login}"])


def _quick_login_wait_seconds() -> float:
    """Brief wait on Freigabe; longer retries happen via pending bootstrap."""
    full = _session_login_wait_seconds()
    quick = float(getattr(settings, "MCC_MINECRAFT_SESSION_LOGIN_QUICK_WAIT_SECONDS", 0.5))
    return max(0.0, min(full, quick))


def _apply_effects_when_online(
    online_login: str,
    post_login_commands: list[str],
    *,
    timeout_sec: float | None = None,
) -> tuple[bool, str]:
    """
    Wait briefly for the player entity, then apply post-login commands.

    Returns (ok, detail). ok=False means bootstrap should be retried later.
    """
    wait_for = _session_login_wait_seconds() if timeout_sec is None else float(timeout_sec)
    if not wait_for_player_online(online_login, timeout_sec=wait_for):
        return False, f"Player {online_login} not online yet (client focus / mouse click)"
    try:
        return True, _run_player_effects_or_raise(post_login_commands, player=online_login)
    except RconSequenceError as exc:
        return False, str(exc)


def _mark_pending_bootstrap(session: MCSession, detail: str) -> None:
    note = f"{PENDING_BOOTSTRAP_PREFIX} {detail}".strip()
    session.last_error = note[:5000]
    session.save(update_fields=["last_error"])


def _clear_pending_bootstrap(session: MCSession) -> None:
    if (session.last_error or "").startswith(PENDING_BOOTSTRAP_PREFIX):
        session.last_error = ""
        session.save(update_fields=["last_error"])


def _forcelogin_then_player_effects(login: str, post_login_commands: list[str]) -> str:
    """Backward-compatible name used by tests; brings player online then applies effects."""
    logs: list[str] = []
    logs.append(_bring_player_online(login))
    logs.append(_run_player_effects_or_raise(post_login_commands, player=login))
    return "\n".join(logs)


def _finish_session(session: MCSession, *, error: str = "") -> MCSession:
    session.status = MCSession.STATUS_FINISHED
    session.timestamp_end = timezone.now()
    if error:
        session.last_error = error[:5000]
        session.save(update_fields=["status", "timestamp_end", "last_error"])
    else:
        session.save(update_fields=["status", "timestamp_end"])
    return session


def terminate_account(account_name: str, *, account_type: str | None = None, ms_username: str = "") -> str:
    """Spectator + leave team; AuthMe logout or Velocity send to limbo (no lobby TP)."""
    from minecraft.services.sidebar_visibility import clear_visibility_commands

    player = (ms_username or account_name or "").strip()
    # Do not teleport on Paper before limbo: lobby Y is high above the city and
    # would be saved as logout position, causing a sky-drop on the next join.
    commands = [
        f"gamemode spectator {player}",
    ]
    commands.extend(clear_visibility_commands(player))
    logs: list[str] = []
    logs.append(_run_or_raise(commands))

    if is_online_auth_mode():
        from minecraft.services.velocity_rcon import send_player_to_limbo
        from mcrcon import MCRconException

        try:
            logs.append(send_player_to_limbo(player))
        except (MCRconException, OSError, ValueError) as exc:
            logger.warning(
                "[minecraft_session] velocity limbo send failed player=%s error=%s",
                player,
                exc,
            )
            raise RconSequenceError(f"Velocity limbo send failed for {player}: {exc}") from exc
    else:
        logs.append(_run_or_raise([f"authme logout {player}"]))
    return "\n".join(logs)


def _post_login_with_spawn_first(
    post_login_commands: list[str],
    spawn_tp_command: str | None,
) -> list[str]:
    """
    Run spawn TP before gamemode/effects.

    Players often rejoin still in spectator; teleporting first then setting the
    play mode avoids falling from mid-air before the spawn TP lands.
    """
    cmds = list(post_login_commands or [])
    spawn = (spawn_tp_command or "").strip()
    if not spawn:
        return cmds
    return [spawn, *cmds]


def start_player_session(
    arena_ref: str,
    *,
    duration: int | None = None,
    user=None,
    source: str = MCSession.SOURCE_ADMIN,
    teleport_to_spawn: bool = False,
    spawn_offset_index: int = 0,
    ms_username: str | None = None,
    station_id: int | str | None = None,
    ticket_count: int | None = None,
    grant_catalog_slugs: list[str] | None = None,
    clear_grants_before_start: bool = False,
) -> MCSession:
    """
    Start a PLAYER session for a MinecraftPlayAccount.

    arena_ref may be id_tag or short_name (case-insensitive).
    Optional ms_username overrides the account default for this session only.
    Optional station_id binds the session to a physical PC (max one active).
    Optional ticket_count issues Paper MCC-Tickets after login (0..max).
    Optional grant_catalog_slugs issues Vergabe-Katalog items (e.g. VP garage).
    Optional clear_grants_before_start revokes active slot grants first.
    """
    ref = (arena_ref or "").strip()
    if not ref:
        raise AccountNotFoundError("Play account reference empty")

    account = (
        MinecraftPlayAccount.objects.filter(is_active=True)
        .filter(models_q_id_or_short(ref))
        .first()
    )
    if account is None:
        raise AccountNotFoundError(f"Play account not found or inactive: {ref}")

    login = account.short_name
    tickets = _normalize_world_ticket_count(ticket_count)
    from minecraft.services.grant_catalog import (
        clear_active_grants_for_account,
        normalize_grant_slugs,
        sync_grant_records_for_session,
    )

    grant_slugs = normalize_grant_slugs(
        grant_catalog_slugs,
        account_type=MCSession.ACCOUNT_PLAYER,
    )
    station = _resolve_start_station(station_id, role="play")
    default_login = resolve_player_online_login(account)
    online_login = _resolve_session_online_login(
        default_login=default_login,
        ms_username_override=ms_username,
        station=station,
        require_allowlist=is_online_auth_mode() or bool((ms_username or "").strip()),
    )
    if not online_login:
        raise MissingMicrosoftLoginError(
            f"Microsoft-Login fehlt für Spieler-Account {login}"
        )

    if get_active_session(login):
        raise AccountAlreadyActiveError(f"Session already active for {login}")

    if duration is None:
        from minecraft.services.waitlist_service import get_assigned_player_entry

        assigned = get_assigned_player_entry(login)
        if assigned is not None:
            duration = assigned.duration_minutes

    minutes = resolve_player_duration(account, override=duration)
    duration_minutes, ends_at = _session_timing(minutes)
    _ = teleport_to_spawn  # start always lands on world surface; flag kept for API/UI

    from minecraft.services.player_session_bootstrap import (
        build_player_post_login_commands,
        build_player_world_commands,
    )
    from minecraft.models import MinecraftSessionWaitlistEntry

    _assert_world_ticket_balance(
        account_name=login,
        queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
        ticket_count=tickets,
    )

    initial_mode = preferred_gamemode_for_account(
        MCSession.ACCOUNT_PLAYER,
        prefer_gamemode=getattr(account, "prefer_gamemode", "") or "",
        prefer_spectator=bool(account.prefer_spectator),
    )

    if clear_grants_before_start:
        _count, clear_cmds = clear_active_grants_for_account(login, user=user)
        if clear_cmds:
            try:
                _run_or_raise(clear_cmds)
            except RconSequenceError as exc:
                logger.warning(
                    "[minecraft_session] grant clear RCON failed account=%s error=%s",
                    login,
                    exc,
                )

    try:
        from minecraft.services.sidebar_visibility import (
            ensure_arena_station_team,
            ensure_sidebar_routing_teams,
        )

        ensure_sidebar_routing_teams()
        ensure_arena_station_team(login)
        world_cmds = build_player_world_commands()
        if world_cmds:
            _run_or_raise(world_cmds)
        _transfer_player_to_game(online_login)
    except RconSequenceError as exc:
        logger.error("[minecraft_session] player start failed account=%s error=%s", login, exc)
        raise

    post_cmds = build_player_post_login_commands(
        online_login,
        emerald_count=_emerald_count(),
        spectator=initial_mode == MCSession.GAMEMODE_SPECTATOR,
        gamemode=initial_mode,
        team_label=login,
        world_ticket_count=tickets,
        grant_catalog_slugs=grant_slugs,
    )
    # Always land on world spawn before play gamemode (safe ground, then mode).
    post_cmds = _post_login_with_spawn_first(
        post_cmds,
        world_spawn_tp_command(online_login, offset_index=spawn_offset_index),
    )

    now = timezone.now()
    with transaction.atomic():
        if _active_session_for(login):
            raise AccountAlreadyActiveError(f"Session already active for {login}")
        _debit_world_tickets_if_needed(
            account_name=login,
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_count=tickets,
            user=user,
        )
        session = MCSession(
            account_name=login,
            ms_username=online_login if is_online_auth_mode() else ((ms_username or "").strip()),
            account_type=MCSession.ACCOUNT_PLAYER,
            timestamp_start=now,
            duration_minutes=duration_minutes,
            ends_at=ends_at,
            status=MCSession.STATUS_ACTIVE,
            source=source,
            started_by=user,
            teleport_to_spawn=True,
            spawn_offset_index=max(0, int(spawn_offset_index or 0)),
            station=station,
            world_ticket_count=tickets,
            grant_catalog_slugs=grant_slugs,
        )
        apply_play_gamemode_fields(session, initial_mode)
        session.save()
        try:
            from minecraft.services.waitlist_service import activate_waitlist_for_session

            activate_waitlist_for_session(session, user=user)
        except Exception as exc:
            logger.warning(
                "[minecraft_session] waitlist activate failed account=%s error=%s",
                login,
                exc,
            )

    # Effects after DB session exists: soft-fail so the tile becomes ACTIVE even if
    # the Minecraft client still needs a mouse click / focus.
    ok, detail = _apply_effects_when_online(
        online_login,
        post_cmds,
        timeout_sec=_quick_login_wait_seconds(),
    )
    if not ok:
        _mark_pending_bootstrap(session, detail)
        logger.warning(
            "[minecraft_session] player bootstrap pending account=%s online=%s detail=%s",
            login,
            online_login,
            detail,
        )
    else:
        _clear_pending_bootstrap(session)
        try:
            sync_grant_records_for_session(
                session, player=online_login, user=user
            )
        except Exception as exc:
            logger.warning(
                "[minecraft_session] grant records failed account=%s error=%s",
                login,
                exc,
            )

    logger.info(
        "[minecraft_session] player started account=%s online=%s duration=%s source=%s "
        "tickets=%s grants=%s bootstrap_ok=%s",
        login,
        online_login,
        minutes,
        source,
        tickets,
        grant_slugs,
        ok,
    )
    return session


def models_q_id_or_short(ref: str):
    from django.db.models import Q

    return Q(id_tag__iexact=ref) | Q(short_name__iexact=ref)


def start_builder_session(
    team_name: str,
    *,
    duration: int | None = None,
    user=None,
    source: str = MCSession.SOURCE_ADMIN,
    teleport_to_spawn: bool = False,
    spawn_offset_index: int = 0,
    spawn_region=None,
    spawn_region_id: int | str | None = None,
    ms_username: str | None = None,
    station_id: int | str | None = None,
    ticket_count: int | None = None,
    grant_catalog_slugs: list[str] | None = None,
    clear_grants_before_start: bool = False,
) -> MCSession:
    """Start a BUILDER session for an active MinecraftTeamRegistration."""
    name = (team_name or "").strip()
    if not name:
        raise AccountNotFoundError("Team name empty")

    registration = (
        MinecraftTeamRegistration.objects.select_related("group")
        .filter(is_active=True, mc_username__iexact=name)
        .first()
    )
    if registration is None:
        raise AccountNotFoundError(f"No active builder registration: {name}")
    if registration.group_id and not registration.group.is_visible:
        raise AccountNotFoundError(f"Builder group not visible: {name}")

    login = registration.mc_username
    tickets = _normalize_world_ticket_count(ticket_count)
    from minecraft.services.grant_catalog import (
        clear_active_grants_for_account,
        normalize_grant_slugs,
        sync_grant_records_for_session,
    )

    grant_slugs = normalize_grant_slugs(
        grant_catalog_slugs,
        account_type=MCSession.ACCOUNT_BUILDER,
    )
    station = _resolve_start_station(station_id, role="builder")
    default_login = resolve_builder_online_login(registration)
    online_login = _resolve_session_online_login(
        default_login=default_login,
        ms_username_override=ms_username,
        station=station,
        require_allowlist=is_online_auth_mode() or bool((ms_username or "").strip()),
    )
    if not online_login:
        raise MissingMicrosoftLoginError(
            f"Microsoft-Login fehlt für Bau-Account {login}"
        )

    if get_active_session(login):
        raise AccountAlreadyActiveError(f"Session already active for {login}")

    resolved_region = spawn_region
    if resolved_region is None and spawn_region_id not in (None, ""):
        resolved_region = resolve_builder_spawn_region(registration, spawn_region_id)
    elif resolved_region is not None:
        # Ensure the provided region is allowed for this builder.
        resolved_region = resolve_builder_spawn_region(registration, resolved_region.pk)

    # Region spawn takes priority; otherwise always world-surface spawn.
    _ = teleport_to_spawn  # retained for call-site / UI compatibility

    if not is_online_auth_mode() and not registration.authme_is_registered:
        from minecraft.services.builder_account_provision import register_builder_account_on_minecraft

        try:
            register_builder_account_on_minecraft(registration)
            registration.refresh_from_db()
        except RconSequenceError:
            raise
        except SessionControlError as exc:
            raise SessionControlError(
                f"AuthMe registration failed for {login}: {exc}",
                code=exc.code,
            ) from exc

    if duration is None:
        from minecraft.services.waitlist_service import get_assigned_builder_entry

        assigned = get_assigned_builder_entry(login)
        if assigned is not None:
            duration = assigned.duration_minutes

    minutes = resolve_builder_duration(registration, override=duration)
    duration_minutes, ends_at = _session_timing(minutes)

    from minecraft.services.builder_session_bootstrap import (
        build_builder_post_login_commands,
        build_builder_world_commands,
    )
    from minecraft.models import MinecraftSessionWaitlistEntry

    _assert_world_ticket_balance(
        account_name=login,
        queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
        ticket_count=tickets,
    )

    initial_mode = preferred_gamemode_for_account(
        MCSession.ACCOUNT_BUILDER,
        prefer_gamemode=getattr(registration, "prefer_gamemode", "") or "",
        prefer_spectator=bool(registration.prefer_spectator),
    )

    if clear_grants_before_start:
        _count, clear_cmds = clear_active_grants_for_account(login, user=user)
        if clear_cmds:
            try:
                _run_or_raise(clear_cmds)
            except RconSequenceError as exc:
                logger.warning(
                    "[minecraft_session] grant clear RCON failed account=%s error=%s",
                    login,
                    exc,
                )

    try:
        from minecraft.services.sidebar_visibility import (
            ensure_builder_station_team,
            ensure_sidebar_routing_teams,
        )

        ensure_sidebar_routing_teams()
        ensure_builder_station_team(login)
        world_cmds = build_builder_world_commands()
        if world_cmds:
            _run_or_raise(world_cmds)
        _transfer_player_to_game(online_login)
    except RconSequenceError as exc:
        logger.error("[minecraft_session] builder start failed account=%s error=%s", login, exc)
        raise

    post_cmds = build_builder_post_login_commands(
        online_login,
        team_label=login,
        spectator=initial_mode == MCSession.GAMEMODE_SPECTATOR,
        gamemode=initial_mode,
        world_ticket_count=tickets,
        grant_catalog_slugs=grant_slugs,
    )
    # Always land on safe ground before play gamemode.
    if resolved_region is not None:
        spawn_tp = region_spawn_tp_command(online_login, resolved_region)
    else:
        spawn_tp = world_spawn_tp_command(
            online_login, offset_index=spawn_offset_index
        )
    post_cmds = _post_login_with_spawn_first(post_cmds, spawn_tp)

    now = timezone.now()
    with transaction.atomic():
        if _active_session_for(login):
            raise AccountAlreadyActiveError(f"Session already active for {login}")
        _debit_world_tickets_if_needed(
            account_name=login,
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
            ticket_count=tickets,
            user=user,
        )
        session = MCSession(
            account_name=login,
            ms_username=online_login if is_online_auth_mode() else ((ms_username or "").strip()),
            account_type=MCSession.ACCOUNT_BUILDER,
            timestamp_start=now,
            duration_minutes=duration_minutes,
            ends_at=ends_at,
            status=MCSession.STATUS_ACTIVE,
            source=source,
            started_by=user,
            teleport_to_spawn=resolved_region is None,
            spawn_offset_index=max(0, int(spawn_offset_index or 0)),
            spawn_region=resolved_region,
            station=station,
            world_ticket_count=tickets,
            grant_catalog_slugs=grant_slugs,
        )
        apply_play_gamemode_fields(session, initial_mode)
        session.save()
        try:
            from minecraft.services.waitlist_service import activate_waitlist_for_session

            activate_waitlist_for_session(session, user=user)
        except Exception as exc:
            logger.warning(
                "[minecraft_session] waitlist activate failed account=%s error=%s",
                login,
                exc,
            )

    ok, detail = _apply_effects_when_online(
        online_login,
        post_cmds,
        timeout_sec=_quick_login_wait_seconds(),
    )
    if not ok:
        _mark_pending_bootstrap(session, detail)
        logger.warning(
            "[minecraft_session] builder bootstrap pending account=%s online=%s detail=%s",
            login,
            online_login,
            detail,
        )
    else:
        _clear_pending_bootstrap(session)
        try:
            sync_grant_records_for_session(
                session, player=online_login, user=user
            )
        except Exception as exc:
            logger.warning(
                "[minecraft_session] grant records failed account=%s error=%s",
                login,
                exc,
            )

    logger.info(
        "[minecraft_session] builder started account=%s online=%s duration=%s source=%s "
        "tickets=%s grants=%s bootstrap_ok=%s",
        login,
        online_login,
        minutes,
        source,
        tickets,
        grant_slugs,
        ok,
    )
    return session


def retry_pending_session_bootstraps(*, limit: int = 20) -> int:
    """
    Apply post-login effects for ACTIVE sessions that started before the client joined.

    Called from dashboard polls / session worker so Freigabe can return quickly while
    the player still clicks into the Minecraft window.
    """
    from minecraft.services.builder_session_bootstrap import build_builder_post_login_commands
    from minecraft.services.player_session_bootstrap import build_player_post_login_commands

    pending = list(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            last_error__startswith=PENDING_BOOTSTRAP_PREFIX,
        )
        .select_related("spawn_region")
        .order_by("timestamp_start")[:limit]
    )
    if not pending:
        return 0

    applied = 0
    for session in pending:
        player = session_rcon_login(session)
        if not player:
            continue
        try:
            if not is_player_online(player):
                continue
        except Exception as exc:
            logger.warning(
                "[minecraft_session] pending bootstrap online-check failed account=%s error=%s",
                session.account_name,
                exc,
            )
            continue

        mode = session.play_gamemode or (
            MCSession.GAMEMODE_SPECTATOR
            if session.gamemode_spectator
            else MCSession.GAMEMODE_ADVENTURE
        )
        if session.account_type == MCSession.ACCOUNT_BUILDER:
            commands = build_builder_post_login_commands(
                player,
                team_label=session.account_name,
                spectator=mode == MCSession.GAMEMODE_SPECTATOR,
                gamemode=mode,
                world_ticket_count=int(session.world_ticket_count or 0),
                grant_catalog_slugs=list(session.grant_catalog_slugs or []),
            )
        else:
            commands = build_player_post_login_commands(
                player,
                emerald_count=_emerald_count(),
                spectator=mode == MCSession.GAMEMODE_SPECTATOR,
                gamemode=mode,
                team_label=session.account_name,
                world_ticket_count=int(session.world_ticket_count or 0),
                grant_catalog_slugs=list(session.grant_catalog_slugs or []),
            )
        spawn_tp = None
        if session.spawn_region_id:
            spawn_tp = region_spawn_tp_command(player, session.spawn_region)
        else:
            spawn_tp = world_spawn_tp_command(
                player,
                offset_index=int(session.spawn_offset_index or 0),
            )
        commands = _post_login_with_spawn_first(commands, spawn_tp)
        try:
            _run_player_effects_or_raise(commands, player=player)
        except RconSequenceError as exc:
            _mark_pending_bootstrap(session, str(exc))
            logger.warning(
                "[minecraft_session] pending bootstrap still failing account=%s error=%s",
                session.account_name,
                exc,
            )
            continue
        _clear_pending_bootstrap(session)
        try:
            from minecraft.services.grant_catalog import sync_grant_records_for_session

            sync_grant_records_for_session(session, player=player)
        except Exception as exc:
            logger.warning(
                "[minecraft_session] pending grant records failed account=%s error=%s",
                session.account_name,
                exc,
            )
        applied += 1
        logger.info(
            "[minecraft_session] pending bootstrap applied account=%s player=%s",
            session.account_name,
            player,
        )
    return applied


def end_session(
    account_name: str,
    *,
    send_rcon: bool = True,
) -> MCSession:
    """Kick/logout an active session (manual or timeout)."""
    name = (account_name or "").strip()
    session = get_active_session(name)
    if session is None:
        raise SessionNotActiveError(f"No active session for {name}")

    login = session.account_name
    player = session_rcon_login(session)
    rcon_error = ""
    if send_rcon:
        try:
            terminate_account(
                login,
                account_type=session.account_type,
                ms_username=player,
            )
        except RconSequenceError as exc:
            rcon_error = str(exc)
            logger.warning(
                "[minecraft_session] terminate RCON failed account=%s error=%s",
                login,
                exc,
            )

    with transaction.atomic():
        locked = _active_session_for(name)
        if locked is None:
            raise SessionNotActiveError(f"No active session for {name}")
        _finish_session(locked, error=rcon_error)
        try:
            from minecraft.services.waitlist_service import complete_waitlist_for_session

            complete_waitlist_for_session(locked)
        except Exception as exc:
            logger.warning(
                "[minecraft_session] waitlist complete failed account=%s error=%s",
                login,
                exc,
            )
        session = locked

    logger.info("[minecraft_session] ended account=%s rcon_ok=%s", login, not bool(rcon_error))
    return session


@transaction.atomic
def add_session_time(
    account_name: str,
    *,
    minutes: int | None = None,
) -> MCSession:
    """Extend ends_at of an active session (Add Time)."""
    name = (account_name or "").strip()
    session = _active_session_for(name)
    if session is None:
        raise SessionNotActiveError(f"No active session for {name}")
    if session.ends_at is None:
        raise SessionControlError(
            "Unbegrenzte Session kann nicht verlängert werden.",
            code="unlimited_session",
        )

    add_min = resolve_add_time_for_session(session, override=minutes)
    if add_min < 1:
        raise SessionControlError("add minutes must be >= 1", code="invalid_duration")

    now = timezone.now()
    base = session.ends_at if session.ends_at > now else now
    session.ends_at = base + timedelta(minutes=add_min)
    session.duration_minutes = session.duration_minutes + add_min
    session.save(update_fields=["ends_at", "duration_minutes"])
    logger.info(
        "[minecraft_session] add_time account=%s minutes=%s ends_at=%s",
        session.account_name,
        add_min,
        session.ends_at.isoformat(),
    )
    return session


def set_session_gamemode(account_name: str, mode: str) -> MCSession:
    """Set survival / adventure / spectator for an active session."""
    from minecraft.services.account_login import normalize_play_gamemode

    name = (account_name or "").strip()
    gamemode = normalize_play_gamemode(mode)
    if not gamemode:
        raise SessionControlError(f"Invalid gamemode: {mode}", code="invalid_gamemode")

    with transaction.atomic():
        session = _active_session_for(name)
        if session is None:
            raise SessionNotActiveError(f"No active session for {name}")
        player = session_rcon_login(session)
        _run_player_effects_or_raise(
            [gamemode_command(player, gamemode)],
            player=player,
        )
        apply_play_gamemode_fields(session, gamemode)
        session.save(update_fields=["play_gamemode", "gamemode_spectator"])
        logger.info(
            "[minecraft_session] set_gamemode account=%s player=%s mode=%s",
            session.account_name,
            player,
            gamemode,
        )
        return session


def set_all_active_gamemodes(
    mode: str,
    *,
    account_type: str,
) -> tuple[int, list[str]]:
    """
    Set the same play gamemode on every ACTIVE session of the given account type.

    Returns (success_count, error_messages). Continues on per-session failures
    so one RCON error does not block the rest.
    """
    from minecraft.services.account_login import normalize_play_gamemode

    gamemode = normalize_play_gamemode(mode)
    if not gamemode:
        raise SessionControlError(f"Invalid gamemode: {mode}", code="invalid_gamemode")
    if account_type not in {MCSession.ACCOUNT_PLAYER, MCSession.ACCOUNT_BUILDER}:
        raise SessionControlError(
            f"Invalid account_type: {account_type}",
            code="invalid_account_type",
        )

    names = list(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            account_type=account_type,
        )
        .order_by("account_name")
        .values_list("account_name", flat=True)
    )
    ok = 0
    errors: list[str] = []
    for name in names:
        try:
            set_session_gamemode(name, gamemode)
            ok += 1
        except SessionControlError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] set_all_gamemode failed account=%s mode=%s error=%s",
                name,
                gamemode,
                exc,
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] set_all_gamemode failed account=%s mode=%s error=%s",
                name,
                gamemode,
                exc,
            )
    logger.info(
        "[minecraft_session] set_all_gamemode type=%s mode=%s ok=%s failed=%s",
        account_type,
        gamemode,
        ok,
        len(errors),
    )
    return ok, errors


def end_all_active_sessions(*, account_type: str) -> tuple[int, list[str]]:
    """
    Kick/end every ACTIVE session of the given account type.

    Returns (success_count, error_messages). Continues on per-session failures.
    """
    if account_type not in {MCSession.ACCOUNT_PLAYER, MCSession.ACCOUNT_BUILDER}:
        raise SessionControlError(
            f"Invalid account_type: {account_type}",
            code="invalid_account_type",
        )

    names = list(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            account_type=account_type,
        )
        .order_by("account_name")
        .values_list("account_name", flat=True)
    )
    ok = 0
    errors: list[str] = []
    for name in names:
        try:
            end_session(name, send_rcon=True)
            ok += 1
        except SessionControlError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] kick_all failed account=%s error=%s",
                name,
                exc,
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] kick_all failed account=%s error=%s",
                name,
                exc,
            )
    logger.info(
        "[minecraft_session] kick_all type=%s ok=%s failed=%s",
        account_type,
        ok,
        len(errors),
    )
    return ok, errors


def start_all_idle_sessions(
    *,
    account_type: str,
    user=None,
    teleport_to_spawn: bool = False,
) -> tuple[int, list[str]]:
    """
    Start sessions for idle accounts.

    If any idle account is currently waiting in the Velocity limbo, only those
    waiting accounts are started (matches the Warteraum UI). Otherwise every
    idle account is started (e.g. AuthMe / nobody online yet).

    Returns (success_count, error_messages). Continues on per-account failures.
    """
    if account_type not in {MCSession.ACCOUNT_PLAYER, MCSession.ACCOUNT_BUILDER}:
        raise SessionControlError(
            f"Invalid account_type: {account_type}",
            code="invalid_account_type",
        )

    # (account_name, presence_login)
    candidates: list[tuple[str, str]] = []
    if account_type == MCSession.ACCOUNT_PLAYER:
        accounts = list(
            MinecraftPlayAccount.objects.filter(is_active=True).order_by(
                "sort_order", "short_name"
            )
        )
        starter = start_player_session
        for account in accounts:
            name = account.short_name
            if get_active_session(name):
                continue
            login = resolve_player_online_login(account) or (account.ms_username or "").strip()
            candidates.append((name, login))
    else:
        from minecraft.services.team_registration import active_registrations

        registrations = list(active_registrations().order_by("mc_username"))
        starter = start_builder_session
        for registration in registrations:
            name = registration.mc_username
            if get_active_session(name):
                continue
            login = (
                resolve_builder_online_login(registration)
                or (registration.ms_username or "").strip()
            )
            candidates.append((name, login))

    if not candidates:
        return 0, []

    waiting_names: set[str] = set()
    try:
        from minecraft.services.player_presence import (
            PRESENCE_LIMBO,
            resolve_presences_for_logins,
        )

        logins = [login for _, login in candidates if login]
        presence_by_login = resolve_presences_for_logins(logins, paper_override=False)
        for name, login in candidates:
            if not login:
                continue
            presence = presence_by_login.get(login)
            if presence is not None and presence.state == PRESENCE_LIMBO:
                waiting_names.add(name)
    except Exception as exc:
        logger.warning(
            "[minecraft_session] start_all presence lookup failed: %s",
            exc,
        )

    # Prefer Warteraum clients when any are waiting; else start every idle slot.
    to_start = (
        [name for name, _ in candidates if name in waiting_names]
        if waiting_names
        else [name for name, _ in candidates]
    )

    ok = 0
    errors: list[str] = []
    spawn_index = 0
    for name in to_start:
        try:
            kwargs = {"user": user}
            if teleport_to_spawn:
                kwargs["teleport_to_spawn"] = True
                kwargs["spawn_offset_index"] = spawn_index
                spawn_index += 1
            starter(name, **kwargs)
            ok += 1
        except AccountAlreadyActiveError:
            continue
        except SessionControlError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] start_all failed account=%s error=%s",
                name,
                exc,
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] start_all failed account=%s error=%s",
                name,
                exc,
            )
    logger.info(
        "[minecraft_session] start_all type=%s spawn=%s ok=%s failed=%s",
        account_type,
        bool(teleport_to_spawn),
        ok,
        len(errors),
    )
    return ok, errors


def teleport_session_to_spawn(
    account_name: str,
    *,
    offset_index: int = 0,
) -> MCSession:
    """Teleport an active session's online login to world/lobby spawn."""
    name = (account_name or "").strip()
    session = get_active_session(name)
    if session is None:
        raise SessionNotActiveError(f"No active session for {name}")
    player = session_rcon_login(session)
    _run_player_effects_or_raise(
        [world_spawn_tp_command(player, offset_index=offset_index)],
        player=player,
    )
    logger.info(
        "[minecraft_session] teleport_to_spawn account=%s player=%s offset=%s",
        session.account_name,
        player,
        offset_index,
    )
    return session


def teleport_all_active_to_spawn(*, account_type: str) -> tuple[int, list[str]]:
    """Teleport every ACTIVE session of the given type to world spawn (with spacing)."""
    if account_type not in {MCSession.ACCOUNT_PLAYER, MCSession.ACCOUNT_BUILDER}:
        raise SessionControlError(
            f"Invalid account_type: {account_type}",
            code="invalid_account_type",
        )
    names = list(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            account_type=account_type,
        )
        .order_by("account_name")
        .values_list("account_name", flat=True)
    )
    ok = 0
    errors: list[str] = []
    for index, name in enumerate(names):
        try:
            teleport_session_to_spawn(name, offset_index=index)
            ok += 1
        except SessionControlError as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] spawn_all failed account=%s error=%s",
                name,
                exc,
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning(
                "[minecraft_session] spawn_all failed account=%s error=%s",
                name,
                exc,
            )
    logger.info(
        "[minecraft_session] spawn_all type=%s ok=%s failed=%s",
        account_type,
        ok,
        len(errors),
    )
    return ok, errors


def toggle_session_spectator(account_name: str) -> MCSession:
    """Toggle play mode ↔ spectator (player sessions / legacy)."""
    name = (account_name or "").strip()
    session = get_active_session(name)
    if session is None:
        raise SessionNotActiveError(f"No active session for {name}")
    current = session.play_gamemode or (
        MCSession.GAMEMODE_SPECTATOR
        if session.gamemode_spectator
        else MCSession.GAMEMODE_ADVENTURE
    )
    if current == MCSession.GAMEMODE_SPECTATOR:
        new_mode = MCSession.GAMEMODE_ADVENTURE
    else:
        new_mode = MCSession.GAMEMODE_SPECTATOR
    return set_session_gamemode(name, new_mode)


def expire_due_sessions(*, limit: int = 50) -> list[MCSession]:
    """End ACTIVE sessions whose ends_at is in the past (skips unlimited)."""
    now = timezone.now()
    due_names = list(
        MCSession.objects.filter(
            status=MCSession.STATUS_ACTIVE,
            ends_at__isnull=False,
            ends_at__lte=now,
        )
        .order_by("ends_at")
        .values_list("account_name", flat=True)[:limit]
    )
    finished: list[MCSession] = []
    for account_name in due_names:
        try:
            finished.append(end_session(account_name, send_rcon=True))
        except SessionNotActiveError:
            continue
    return finished


def _presence_grace_seconds() -> float:
    return float(getattr(settings, "MCC_MINECRAFT_SESSION_PRESENCE_GRACE_SECONDS", 60))


def reconcile_abandoned_sessions(*, limit: int = 50) -> list[MCSession]:
    """
    End ACTIVE sessions whose player left Paper (offline / limbo / other proxy server).

    Uses Velocity ``glist`` in online mode (Paper ``list`` in authme mode).
    Skips sessions younger than the grace period (transfer lag after Start).
    Double-checks Paper ``list`` before ending so a lagging glist cannot kill a live session.
    """
    from minecraft.services.player_presence import (
        PRESENCE_PAPER,
        PRESENCE_UNKNOWN,
        resolve_presences_for_logins,
    )

    now = timezone.now()
    grace = timedelta(seconds=max(0.0, _presence_grace_seconds()))
    active = list(
        MCSession.objects.filter(status=MCSession.STATUS_ACTIVE)
        .order_by("timestamp_start")[:limit]
    )
    eligible: list[MCSession] = []
    login_for: dict[str, str] = {}
    for session in active:
        if grace.total_seconds() > 0 and session.timestamp_start > now - grace:
            continue
        player = session_rcon_login(session)
        if not player:
            continue
        eligible.append(session)
        login_for[session.account_name] = player

    if not eligible:
        return []

    try:
        presence_map = resolve_presences_for_logins(list(login_for.values()))
    except Exception as exc:
        logger.warning("[minecraft_session] presence reconcile failed: %s", exc)
        return []

    finished: list[MCSession] = []
    for session in eligible:
        player = login_for.get(session.account_name, "")
        presence = presence_map.get(player)
        if presence is None or presence.state in {PRESENCE_PAPER, PRESENCE_UNKNOWN}:
            continue
        # glist lag after Velocity send: keep session if Paper still has the entity
        try:
            if is_player_online(player):
                logger.info(
                    "[minecraft_session] skip abandon (paper online) account=%s player=%s presence=%s",
                    session.account_name,
                    player,
                    presence.state,
                )
                continue
        except Exception as exc:
            logger.warning(
                "[minecraft_session] paper check failed account=%s error=%s",
                session.account_name,
                exc,
            )
            continue
        # Player no longer on Paper → treat as self-ended session
        logger.info(
            "[minecraft_session] abandoned account=%s player=%s presence=%s server=%s",
            session.account_name,
            player,
            presence.state,
            presence.server,
        )
        try:
            # No Paper cleanup needed if already gone; avoid noisy RCON errors
            ended = end_session(session.account_name, send_rcon=False)
            note = f"Spieler hat Session beendet ({presence.label_de})"
            if ended.last_error:
                ended.last_error = f"{ended.last_error}\n{note}"[:5000]
            else:
                ended.last_error = note
            ended.save(update_fields=["last_error"])
            finished.append(ended)
        except SessionNotActiveError:
            continue
        except Exception as exc:
            logger.warning(
                "[minecraft_session] abandon end failed account=%s error=%s",
                session.account_name,
                exc,
            )
    return finished
