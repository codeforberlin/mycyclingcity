# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from luanti.models import (
    LuantiAccount,
    LuantiIntegrationConfig,
    LuantiPlayerInventory,
    LuantiSession,
)


class SessionError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


PRIVS_BY_MODE = {
    # Mineclonia: do NOT grant "creative" unless world creative_mode is on —
    # otherwise inventory code expects creative.lua (not loaded) and crashes the server.
    LuantiAccount.MODE_PLAY: ["shout", "fast", "interact"],
    LuantiAccount.MODE_BUILD: ["shout", "fast", "interact", "fly"],
    LuantiAccount.MODE_WATCH: ["shout", "fly", "noclip"],
}


def account_duration_bounds(account: LuantiAccount) -> tuple[int, int]:
    """Resolved (min, max) minutes for an account (config fallbacks)."""
    cfg = LuantiIntegrationConfig.get_config()
    lo = (
        int(account.session_duration_min_minutes)
        if account.session_duration_min_minutes is not None
        else int(cfg.session_min_minutes or 5)
    )
    hi = (
        int(account.session_duration_max_minutes)
        if account.session_duration_max_minutes is not None
        else int(cfg.session_max_minutes or 180)
    )
    if lo < 1:
        lo = 1
    if hi < lo:
        hi = lo
    return lo, hi


def clamp_duration_minutes(account: LuantiAccount, minutes: int) -> int:
    """Clamp a finite duration to account/config bounds. 0 (unlimited) stays 0."""
    minutes = max(0, int(minutes))
    if minutes == 0 or account.session_unlimited:
        return 0
    lo, hi = account_duration_bounds(account)
    return max(lo, min(hi, minutes))


def account_time_step_minutes(account: LuantiAccount) -> int:
    """± button step for session tiles (account override or global config)."""
    if account.session_add_minutes is not None:
        return max(1, int(account.session_add_minutes))
    return max(1, int(LuantiIntegrationConfig.get_config().session_add_minutes or 15))


def resolve_duration_minutes(account: LuantiAccount, override: int | None = None) -> int:
    if override is not None:
        return clamp_duration_minutes(account, int(override))
    if account.session_unlimited:
        return 0
    if account.session_duration_minutes is not None:
        return clamp_duration_minutes(account, int(account.session_duration_minutes))
    return clamp_duration_minutes(
        account, int(LuantiIntegrationConfig.get_config().default_session_minutes)
    )


def get_active_session(login_name: str) -> LuantiSession | None:
    """Current open session (ACTIVE or PAUSED)."""
    return (
        LuantiSession.objects.filter(
            login_name__iexact=login_name.strip(),
            status__in=LuantiSession.OPEN_STATUSES,
        )
        .select_related("account")
        .first()
    )


def get_or_create_inventory(account: LuantiAccount, mode: str) -> LuantiPlayerInventory:
    if mode == LuantiAccount.MODE_WATCH:
        mode = LuantiAccount.MODE_PLAY
    inv, _ = LuantiPlayerInventory.objects.get_or_create(
        account=account,
        mode=mode,
        defaults={"payload": []},
    )
    return inv


def coerce_inventory_list(value, *, inventory_count=None) -> list | None:
    """Normalize inventory from bridge JSON.

    Luanti ``core.write_json`` encodes an empty Lua table as ``{}`` (object), not
    ``[]``. Treat that (and ``inventory_count=0``) as an explicit empty list so
    leave/sync can persist a cleared inventory.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and len(value) == 0:
        return []
    if value is None and inventory_count == 0:
        return []
    try:
        if inventory_count is not None and int(inventory_count) == 0 and value in (None, {}):
            return []
    except (TypeError, ValueError):
        pass
    return None


def clear_account_inventory(inv: LuantiPlayerInventory, *, push_live: bool = True) -> LuantiPlayerInventory:
    """Empty stored inventory and bump revision.

    If the account has an open session in the same mode, also push CLEAR_INVENTORY
    so a live player is emptied immediately (leave would otherwise overwrite []).
    """
    inv.payload = []
    inv.revision = int(inv.revision or 0) + 1
    inv.save(update_fields=["payload", "revision", "updated_at"])
    if push_live:
        session = get_active_session(inv.account.login_name)
        if session and session.mode == inv.mode:
            from luanti.consumers import LuantiEventConsumer

            LuantiEventConsumer.push_to_all_sync(
                {
                    "type": "CLEAR_INVENTORY",
                    "player": inv.account.login_name,
                    "mode": inv.mode,
                }
            )
    return inv


@transaction.atomic
def start_session(
    *,
    account: LuantiAccount,
    mode: str | None = None,
    source: str = LuantiSession.SOURCE_ADMIN,
    duration: int | None = None,
    station=None,
    started_by=None,
    wallet_group=None,
) -> LuantiSession:
    if not account.is_active:
        raise SessionError("account_inactive")
    allowed = account.resolved_allowed_modes()
    chosen = mode or account.default_mode
    if chosen not in allowed:
        raise SessionError("mode_not_allowed", f"mode={chosen}")
    existing = get_active_session(account.login_name)
    if existing:
        raise SessionError("already_active", str(existing.session_id))

    minutes = resolve_duration_minutes(account, override=duration)
    now = timezone.now()
    ends_at = None if minutes == 0 else now + timedelta(minutes=minutes)
    session = LuantiSession.objects.create(
        account=account,
        login_name=account.login_name,
        mode=chosen,
        status=LuantiSession.STATUS_ACTIVE,
        source=source,
        timestamp_start=now,
        duration_minutes=minutes,
        ends_at=ends_at,
        station=station,
        started_by=started_by,
        wallet_group=wallet_group,
    )
    from luanti.services.presence import clear_waiting

    clear_waiting(account.login_name)
    try:
        from luanti.services.session_bootstrap import push_session_bootstrap

        push_session_bootstrap(user=started_by)
    except Exception:
        # Session must still start even if bridge/preset push fails.
        import logging

        logging.getLogger("luanti").exception("[start_session] bootstrap failed")
    return session


@transaction.atomic
def end_session(session: LuantiSession, *, inventory_payload: list | None = None) -> LuantiSession:
    if session.status not in LuantiSession.OPEN_STATUSES:
        return session
    if inventory_payload is not None:
        inv = get_or_create_inventory(session.account, session.mode)
        inv.payload = inventory_payload
        inv.revision = inv.revision + 1
        inv.save(update_fields=["payload", "revision", "updated_at"])
    session.status = LuantiSession.STATUS_FINISHED
    session.timestamp_end = timezone.now()
    session.paused_at = None
    session.remaining_seconds = None
    session.save(
        update_fields=["status", "timestamp_end", "paused_at", "remaining_seconds"]
    )
    return session


def clear_waiting_for_login(login_name: str) -> None:
    from luanti.services.presence import clear_waiting

    clear_waiting(login_name)


@transaction.atomic
def set_session_mode(session: LuantiSession, new_mode: str, *, save_inventory=None) -> LuantiSession:
    if session.status not in LuantiSession.OPEN_STATUSES:
        raise SessionError("not_active")
    if session.status == LuantiSession.STATUS_PAUSED:
        raise SessionError("session_paused")
    allowed = session.account.resolved_allowed_modes()
    if new_mode not in allowed:
        raise SessionError("mode_not_allowed")
    if save_inventory is not None:
        inv = get_or_create_inventory(session.account, session.mode)
        inv.payload = save_inventory
        inv.revision = inv.revision + 1
        inv.save(update_fields=["payload", "revision", "updated_at"])
    session.mode = new_mode
    session.save(update_fields=["mode"])
    return session


def extend_session(session: LuantiSession, minutes: int | None = None) -> LuantiSession:
    if session.status != LuantiSession.STATUS_ACTIVE:
        raise SessionError("not_active")
    if session.ends_at is None and (session.duration_minutes or 0) == 0:
        raise SessionError("unlimited")
    add = minutes
    if add is None:
        add = account_time_step_minutes(session.account)
    add = max(1, int(add))
    base = session.ends_at or timezone.now()
    new_end = base + timedelta(minutes=add)
    _, hi = account_duration_bounds(session.account)
    if not session.account.session_unlimited:
        cap = session.timestamp_start + timedelta(minutes=hi)
        if new_end > cap:
            new_end = cap
    if session.ends_at and new_end <= session.ends_at:
        raise SessionError("at_max_duration")
    session.ends_at = new_end
    remaining = max(0, int((new_end - session.timestamp_start).total_seconds() // 60))
    session.duration_minutes = remaining
    session.end_warning_sent_at = None
    session.save(update_fields=["ends_at", "duration_minutes", "end_warning_sent_at"])
    return session


def reduce_session(session: LuantiSession, minutes: int | None = None) -> LuantiSession:
    """Shorten remaining time. Raises session_expired if nothing left."""
    if session.status != LuantiSession.STATUS_ACTIVE:
        raise SessionError("not_active")
    if session.ends_at is None:
        raise SessionError("unlimited")
    sub = minutes
    if sub is None:
        sub = account_time_step_minutes(session.account)
    sub = max(1, int(sub))
    now = timezone.now()
    new_end = session.ends_at - timedelta(minutes=sub)
    lo, _ = account_duration_bounds(session.account)
    # Remaining floor: at least 1 minute, or account min if still above start+min... 
    # Practical: never leave less than 1 minute unless cutting forces kick.
    floor_end = now + timedelta(minutes=1)
    if new_end <= now:
        raise SessionError("would_expire")
    if new_end < floor_end:
        new_end = floor_end
    # Also do not go below account min total duration from start when still early
    min_end = session.timestamp_start + timedelta(minutes=lo)
    if new_end < min_end and min_end > now:
        new_end = min_end
    if new_end >= session.ends_at:
        raise SessionError("at_min_duration")
    session.ends_at = new_end
    remaining = max(0, int((new_end - session.timestamp_start).total_seconds() // 60))
    session.duration_minutes = remaining
    session.end_warning_sent_at = None
    session.save(update_fields=["ends_at", "duration_minutes", "end_warning_sent_at"])
    return session


@transaction.atomic
def pause_session(session: LuantiSession) -> LuantiSession:
    if session.status != LuantiSession.STATUS_ACTIVE:
        raise SessionError("not_active")
    now = timezone.now()
    remaining = None
    if session.ends_at is not None:
        remaining = max(0, int((session.ends_at - now).total_seconds()))
        if remaining <= 0:
            raise SessionError("session_expired")
    session.status = LuantiSession.STATUS_PAUSED
    session.paused_at = now
    session.remaining_seconds = remaining
    session.ends_at = None
    session.save(
        update_fields=["status", "paused_at", "remaining_seconds", "ends_at"]
    )
    return session


@transaction.atomic
def resume_session(session: LuantiSession) -> LuantiSession:
    if session.status != LuantiSession.STATUS_PAUSED:
        raise SessionError("not_paused")
    now = timezone.now()
    ends_at = None
    if session.remaining_seconds is not None:
        ends_at = now + timedelta(seconds=int(session.remaining_seconds))
    session.status = LuantiSession.STATUS_ACTIVE
    session.ends_at = ends_at
    session.paused_at = None
    session.remaining_seconds = None
    session.end_warning_sent_at = None
    session.save(
        update_fields=[
            "status",
            "ends_at",
            "paused_at",
            "remaining_seconds",
            "end_warning_sent_at",
        ]
    )
    return session


def warn_expiring_sessions() -> list[LuantiSession]:
    """
    Notify players whose ACTIVE session ends within the configured warning window.
    Each session is warned at most once until ends_at changes (extend/reduce/resume).
    """
    cfg = LuantiIntegrationConfig.get_config()
    warn_sec = int(cfg.session_end_warning_seconds or 0)
    if warn_sec <= 0:
        return []
    now = timezone.now()
    horizon = now + timedelta(seconds=warn_sec)
    due = list(
        LuantiSession.objects.filter(
            status=LuantiSession.STATUS_ACTIVE,
            ends_at__isnull=False,
            ends_at__gt=now,
            ends_at__lte=horizon,
            end_warning_sent_at__isnull=True,
        ).select_related("account")
    )
    if not due:
        return []
    try:
        from luanti.consumers import LuantiEventConsumer
    except Exception:
        return []
    warned: list[LuantiSession] = []
    for session in due:
        remaining = max(0, int((session.ends_at - now).total_seconds()))
        minutes = max(1, (remaining + 59) // 60)
        try:
            LuantiEventConsumer.push_to_all_sync(
                {
                    "type": "SESSION_END_WARNING",
                    "player": session.login_name,
                    "minutes": minutes,
                }
            )
            session.end_warning_sent_at = now
            session.save(update_fields=["end_warning_sent_at"])
            warned.append(session)
        except Exception:
            continue
    return warned


def expire_due_sessions() -> list[LuantiSession]:
    """
    Find ACTIVE sessions past ends_at and queue kicks (leave saves inventory).
    Returns the sessions that were kicked.
    """
    now = timezone.now()
    due = list(
        LuantiSession.objects.filter(
            status=LuantiSession.STATUS_ACTIVE,
            ends_at__isnull=False,
            ends_at__lte=now,
        ).select_related("account")
    )
    if not due:
        return []
    try:
        from luanti.consumers import LuantiEventConsumer
    except Exception:
        return []
    kicked = []
    for session in due:
        try:
            LuantiEventConsumer.push_to_all_sync(
                {
                    "type": "KICK_PLAYER",
                    "player": session.login_name,
                    "reason": "session_expired",
                }
            )
            kicked.append(session)
        except Exception:
            continue
    return kicked


def reconcile_sessions_with_online_players(players: list | None) -> list[LuantiSession]:
    """
    End open sessions whose login is not currently connected in Luanti.

    Used after hard server restarts (leave HTTP may never arrive) so Admin tiles
    do not stay ACTIVE/PAUSED forever. ``players is None`` means legacy heartbeat
    without a player list — skip reconcile.
    """
    if players is None:
        return []
    online = {
        str(name).strip().lower()
        for name in players
        if name is not None and str(name).strip()
    }
    ended: list[LuantiSession] = []
    open_sessions = list(
        LuantiSession.objects.filter(status__in=LuantiSession.OPEN_STATUSES).select_related(
            "account"
        )
    )
    for session in open_sessions:
        if session.login_name.lower() in online:
            continue
        end_session(session, inventory_payload=None)
        ended.append(session)
    return ended


def prepare_luanti_shutdown(*, wait_seconds: float = 25.0) -> dict:
    """
    Ask the bridge to kick all players (leave saves inventory), then wait until
    open sessions are finished. Remaining sessions are force-ended without a
    fresh inventory payload (last Django inventory kept).
    """
    import time

    from luanti.consumers import LuantiEventConsumer
    from luanti.models import LuantiWaitingPlayer
    from luanti.services.bridge_connection import bridge_is_online

    open_sessions = list(
        LuantiSession.objects.filter(status__in=LuantiSession.OPEN_STATUSES).only(
            "session_id", "login_name", "status"
        )
    )
    requested = [s.login_name for s in open_sessions]
    bridge_up = bridge_is_online()
    commands_queued = 0

    if bridge_up:
        # Kick everyone online so on_leaveplayer posts inventory + ends session.
        LuantiEventConsumer.push_to_all_sync(
            {"type": "SAVE_LEAVE_ALL", "reason": "server_shutdown"}
        )
        commands_queued += 1
        # Compatibility: older mods without SAVE_LEAVE_ALL still get per-player kicks.
        for login_name in requested:
            LuantiEventConsumer.push_to_all_sync(
                {
                    "type": "KICK_PLAYER",
                    "player": login_name,
                    "reason": "server_shutdown",
                }
            )
            commands_queued += 1

        wait_seconds = max(0.0, float(wait_seconds))
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if not LuantiSession.objects.filter(
                status__in=LuantiSession.OPEN_STATUSES
            ).exists():
                break
            time.sleep(0.4)
    else:
        # Do not enqueue kicks for the next boot; just close DB sessions.
        wait_seconds = 0.0

    forced: list[str] = []
    for session in LuantiSession.objects.filter(status__in=LuantiSession.OPEN_STATUSES):
        end_session(session, inventory_payload=None)
        forced.append(session.login_name)

    LuantiWaitingPlayer.objects.all().delete()

    return {
        "ok": len(forced) == 0,
        "bridge_online": bridge_up,
        "commands_queued": commands_queued,
        "sessions_requested": len(requested),
        "logins": requested,
        "forced_end": forced,
        "wait_seconds": wait_seconds,
    }


def auth_check_payload(login_name: str) -> dict:
    account = LuantiAccount.objects.filter(login_name__iexact=login_name.strip()).first()
    if not account or not account.is_active:
        return {"ok": False, "allowed": False, "error": "not_authorized"}
    session = get_active_session(account.login_name)
    return {
        "ok": True,
        "allowed": True,
        "account": account.login_name,
        "has_session": bool(session and session.is_open),
        "session_id": str(session.session_id) if session else None,
        "mode": session.mode if session else None,
        "paused": bool(session and session.is_paused),
        "allowed_modes": account.resolved_allowed_modes(),
    }


def join_payload(login_name: str, server_id: str = "") -> dict:
    from luanti.services.presence import clear_waiting, mark_waiting

    account = LuantiAccount.objects.filter(login_name__iexact=login_name.strip(), is_active=True).first()
    if not account:
        return {"ok": False, "error": "not_authorized"}
    session = get_active_session(account.login_name)
    if not session:
        mark_waiting(account.login_name, server_id=server_id)
        return {
            "ok": True,
            "wait": True,
            "privs": ["shout"],
            "message": "waiting_for_session",
            "poll_seconds": 5,
        }
    if (
        session.status == LuantiSession.STATUS_ACTIVE
        and session.ends_at
        and session.ends_at < timezone.now()
    ):
        end_session(session)
        mark_waiting(account.login_name, server_id=server_id)
        return {"ok": False, "error": "session_expired"}
    clear_waiting(account.login_name)
    inv = get_or_create_inventory(account, session.mode)
    if server_id:
        inv.last_server_id = server_id
        inv.save(update_fields=["last_server_id"])
    from luanti.services.wallet import wallet_payload

    wallet = wallet_payload(account, session=session)
    paused = session.is_paused
    if paused:
        # Freeze: shout only — no interact/fly/fast/noclip. Movement locked in Lua.
        effective_mode = "paused"
        privs = ["shout"]
    else:
        effective_mode = session.mode
        privs = list(PRIVS_BY_MODE.get(effective_mode, ["shout"]))
    return {
        "ok": True,
        "wait": False,
        "paused": paused,
        "session_id": str(session.session_id),
        "mode": effective_mode,
        "session_mode": session.mode,
        "privs": privs,
        "inventory": inv.payload,
        "inventory_revision": inv.revision,
        "team_key": wallet["team_key"],
        "velos_spendable": wallet["velos_spendable"],
        "wallet_group_id": wallet["wallet_group_id"],
        "wallet_group_name": wallet["wallet_group_name"],
        "ends_at": session.ends_at.isoformat() if session.ends_at else None,
        "remaining_seconds": session.remaining_seconds if paused else None,
    }


def find_account_by_token(token: str) -> LuantiAccount | None:
    token = (token or "").strip()
    if not token:
        return None
    return (
        LuantiAccount.objects.filter(is_active=True)
        .filter(models_q_id_or_login(token))
        .first()
    )


def models_q_id_or_login(token: str):
    from django.db.models import Q

    return Q(id_tag__iexact=token) | Q(login_name__iexact=token)


def default_session_minutes_setting() -> int:
    return int(getattr(settings, "MCC_LUANTI_DEFAULT_SESSION_MINUTES", 45))
