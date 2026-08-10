# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    session_views.py
# @note    Touch-friendly Minecraft session dashboards (player + builder).

from __future__ import annotations

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from config.logger_utils import get_logger
from minecraft.models import MCSession, MinecraftIntegrationConfig, MinecraftPlayAccount
from minecraft.services.preset_permissions import (
    user_can_manage_builder_sessions,
    user_can_manage_player_sessions,
)
from minecraft.services.session_control import (
    AccountAlreadyActiveError,
    AccountNotFoundError,
    MissingMicrosoftLoginError,
    MsAllowlistError,
    RconSequenceError,
    SessionControlError,
    SessionNotActiveError,
    StationBusyError,
    add_session_time,
    end_session,
    expire_due_sessions,
    reconcile_abandoned_sessions,
    resolve_add_time_for_session,
    resolve_builder_add_time,
    resolve_builder_duration,
    resolve_player_add_time,
    resolve_player_duration,
    set_all_active_gamemodes,
    set_session_gamemode,
    start_builder_session,
    start_player_session,
    toggle_session_spectator,
    end_all_active_sessions,
    start_all_idle_sessions,
    teleport_all_active_to_spawn,
    teleport_session_to_spawn,
)
from minecraft.services.team_registration import active_registrations

VALID_ACTIONS = frozenset(
    {
        "start",
        "kick",
        "add_time",
        "toggle_spectator",
        "set_gamemode",
        "set_all_gamemode",
        "kick_all",
        "start_all",
        "spawn_all",
        "teleport_spawn",
    }
)
BULK_ACTIONS = frozenset({"set_all_gamemode", "kick_all", "start_all", "spawn_all"})
DEFAULT_PROXY_PRESENCE_POLL_SECONDS = 10
MIN_PROXY_PRESENCE_POLL_SECONDS = 2
DEFAULT_PROXY_PRESENCE_POLL_FAST_SECONDS = 2
# Housekeeping (expire/reconcile/bootstrap) at most this often per worker process.
_HOUSEKEEPING_MIN_INTERVAL_SEC = 8.0
_last_housekeeping_at = 0.0


def _proxy_presence_poll_seconds() -> int:
    """Admin-configurable Velocity RCON poll interval for session dashboards."""
    try:
        raw = int(MinecraftIntegrationConfig.get_config().proxy_presence_poll_seconds)
    except (TypeError, ValueError, AttributeError):
        raw = DEFAULT_PROXY_PRESENCE_POLL_SECONDS
    return max(MIN_PROXY_PRESENCE_POLL_SECONDS, raw)


def _proxy_presence_poll_fast_seconds() -> int:
    """Faster tile poll while a player is still in the limbo waiting room."""
    try:
        raw = int(getattr(settings, "MCC_MINECRAFT_PROXY_PRESENCE_POLL_FAST_SECONDS", 2))
    except (TypeError, ValueError):
        raw = DEFAULT_PROXY_PRESENCE_POLL_FAST_SECONDS
    return max(1, min(raw, _proxy_presence_poll_seconds()))


VALID_GAMEMODES = frozenset(
    {
        MCSession.GAMEMODE_SURVIVAL,
        MCSession.GAMEMODE_ADVENTURE,
        MCSession.GAMEMODE_SPECTATOR,
    }
)

logger = get_logger("minecraft")


def _expire_sessions_if_due(*, force: bool = False) -> None:
    """End due / abandoned sessions. Throttled so polls don't block button actions."""
    global _last_housekeeping_at
    now = time.monotonic()
    if not force and (now - _last_housekeeping_at) < _HOUSEKEEPING_MIN_INTERVAL_SEC:
        return
    _last_housekeeping_at = now
    try:
        from minecraft.services.session_control import retry_pending_session_bootstraps

        retry_pending_session_bootstraps()
    except Exception as exc:
        logger.warning("[minecraft_session] pending bootstrap retry failed: %s", exc)
    try:
        expire_due_sessions()
    except Exception as exc:
        logger.warning("[minecraft_session] expire_due_sessions failed: %s", exc)
    try:
        reconcile_abandoned_sessions()
    except Exception as exc:
        logger.warning("[minecraft_session] reconcile_abandoned_sessions failed: %s", exc)


def _presence_lookup_for_cards(
    cards_ms: list[str],
    *,
    paper_override: bool = True,
) -> dict[str, object]:
    """ms_username → PlayerPresence (best-effort)."""
    from minecraft.services.player_presence import resolve_presences_for_logins

    names = [n for n in cards_ms if n]
    if not names:
        return {}
    try:
        return resolve_presences_for_logins(names, paper_override=paper_override)
    except Exception as exc:
        logger.warning("[minecraft_session] presence lookup failed: %s", exc)
        return {}


def _attach_presence(card: dict, presence_by_ms: dict) -> None:
    from minecraft.services.player_presence import (
        PRESENCE_LIMBO,
        PRESENCE_UNKNOWN,
        PRESENCE_LABELS_DE,
    )

    ms = (card.get("ms_username") or "").strip()
    presence = presence_by_ms.get(ms) if ms else None
    if presence is None:
        card["proxy_state"] = ""
        card["proxy_server"] = ""
        card["proxy_label"] = ""
        card["waiting_in_lobby"] = False
        return
    card["proxy_state"] = presence.state
    card["proxy_server"] = presence.server or ""
    card["proxy_label"] = presence.label_de
    card["waiting_in_lobby"] = presence.state == PRESENCE_LIMBO
    if not card.get("is_active") and presence.state == PRESENCE_UNKNOWN:
        card["proxy_label"] = PRESENCE_LABELS_DE.get(PRESENCE_UNKNOWN, "")



def can_manage_player_sessions(user):
    return user_can_manage_player_sessions(user)


def can_manage_builder_sessions(user):
    return user_can_manage_builder_sessions(user)


def _add_minutes() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_SESSION_ADD_MINUTES", 15))


def _player_duration() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_PLAYER_SESSION_MINUTES", 15))


def _builder_duration() -> int:
    return int(getattr(settings, "MCC_MINECRAFT_BUILDER_SESSION_MINUTES", 90))


def _session_payload(account_name: str, session: MCSession | None, *, card: dict | None = None) -> dict:
    if session is None:
        payload = {
            "account_name": account_name,
            "status": "IDLE",
            "ends_at": None,
            "remaining_seconds": 0,
            "gamemode_spectator": False,
            "play_gamemode": "",
            "ms_username": (card or {}).get("ms_username", "") if card else "",
            "proxy_state": (card or {}).get("proxy_state", "") if card else "",
            "proxy_server": (card or {}).get("proxy_server", "") if card else "",
            "proxy_label": (card or {}).get("proxy_label", "") if card else "",
            "waiting_in_lobby": bool((card or {}).get("waiting_in_lobby")) if card else False,
        }
        return payload
    ends_at = session.ends_at.isoformat() if session.ends_at else None
    return {
        "account_name": account_name,
        "status": session.status,
        "ends_at": ends_at,
        "remaining_seconds": session.remaining_seconds,
        "gamemode_spectator": bool(getattr(session, "gamemode_spectator", False)),
        "play_gamemode": getattr(session, "play_gamemode", "") or "",
        "ms_username": getattr(session, "ms_username", "")
        or ((card or {}).get("ms_username", "") if card else ""),
        "proxy_state": (card or {}).get("proxy_state", "") if card else "",
        "proxy_server": (card or {}).get("proxy_server", "") if card else "",
        "proxy_label": (card or {}).get("proxy_label", "") if card else "",
        "waiting_in_lobby": bool((card or {}).get("waiting_in_lobby")) if card else False,
    }


def _active_sessions_by_name(account_names: list[str]) -> dict[str, MCSession]:
    if not account_names:
        return {}
    sessions = MCSession.objects.filter(
        status=MCSession.STATUS_ACTIVE,
        account_name__in=account_names,
    ).select_related("station")
    # Case-insensitive lookup map
    by_lower = {s.account_name.lower(): s for s in sessions}
    result: dict[str, MCSession] = {}
    for name in account_names:
        session = by_lower.get(name.lower())
        if session is not None:
            result[name] = session
    return result


def _build_player_cards(*, include_presence: bool = True) -> list[dict]:
    from minecraft.services.waitlist_service import get_assigned_player_entry

    accounts = list(
        MinecraftPlayAccount.objects.filter(is_active=True).order_by("sort_order", "short_name")
    )
    names = [a.short_name for a in accounts]
    sessions = _active_sessions_by_name(names)
    cards = []
    for account in accounts:
        session = sessions.get(account.short_name)
        assigned = None if session else get_assigned_player_entry(account.short_name)
        start_minutes = (
            assigned.duration_minutes
            if assigned is not None
            else resolve_player_duration(account)
        )
        play_gamemode = ""
        if session:
            play_gamemode = session.play_gamemode or (
                MCSession.GAMEMODE_SPECTATOR
                if session.gamemode_spectator
                else MCSession.GAMEMODE_ADVENTURE
            )
        ms = (account.ms_username or "").strip()
        if session and (session.ms_username or "").strip():
            ms = (session.ms_username or "").strip()
        cards.append(
            {
                "account": account,
                "account_name": account.short_name,
                "ms_username": ms,
                "label": account.label,
                "session": session,
                "is_active": session is not None and session.status == MCSession.STATUS_ACTIVE,
                "remaining_seconds": session.remaining_seconds if session else 0,
                "ends_at": session.ends_at if session else None,
                "start_minutes": start_minutes,
                "add_minutes": resolve_player_add_time(account),
                "uses_custom_settings": (
                    account.session_duration_minutes is not None
                    or account.add_time_minutes is not None
                ),
                "waitlist_ticket": assigned.ticket_number if assigned else "",
                "waitlist_guest": assigned.guest_label if assigned else "",
                "is_waitlist_assigned": assigned is not None,
                "gamemode_spectator": bool(session.gamemode_spectator) if session else False,
                "play_gamemode": play_gamemode,
                "prefer_spectator": bool(account.prefer_spectator),
                "station_name": (
                    session.station.name if session and getattr(session, "station_id", None) else ""
                ),
            }
        )
    if include_presence:
        # Skip Paper override on dashboard polls — glist is enough for tiles and
        # avoids an extra RCON round-trip that blocks the single Gunicorn worker.
        presence_by_ms = _presence_lookup_for_cards(
            [c["ms_username"] for c in cards],
            paper_override=False,
        )
        for card in cards:
            _attach_presence(card, presence_by_ms)
    else:
        for card in cards:
            card["proxy_state"] = ""
            card["proxy_server"] = ""
            card["proxy_label"] = ""
            card["waiting_in_lobby"] = False
    return cards


def _build_builder_cards(*, include_presence: bool = True) -> list[dict]:
    from minecraft.services.region_admin import regions_for_builder_choices
    from minecraft.services.waitlist_service import get_assigned_builder_entry

    registrations = list(active_registrations())
    names = [r.mc_username for r in registrations]
    sessions = _active_sessions_by_name(names)
    cards = []
    for registration in registrations:
        session = sessions.get(registration.mc_username)
        assigned = None if session else get_assigned_builder_entry(registration.mc_username)
        start_minutes = (
            assigned.duration_minutes
            if assigned is not None
            else resolve_builder_duration(registration)
        )
        play_gamemode = ""
        if session:
            play_gamemode = session.play_gamemode or (
                MCSession.GAMEMODE_SPECTATOR
                if session.gamemode_spectator
                else MCSession.GAMEMODE_ADVENTURE
            )
        ms = (registration.ms_username or "").strip()
        if session and (session.ms_username or "").strip():
            ms = (session.ms_username or "").strip()
        cards.append(
            {
                "registration": registration,
                "account_name": registration.mc_username,
                "ms_username": ms,
                "label": registration.group.name if registration.group_id else registration.mc_username,
                "session": session,
                "is_active": session is not None and session.status == MCSession.STATUS_ACTIVE,
                "remaining_seconds": session.remaining_seconds if session else 0,
                "ends_at": session.ends_at if session else None,
                "start_minutes": start_minutes,
                "add_minutes": resolve_builder_add_time(registration),
                "uses_custom_settings": (
                    registration.session_duration_minutes is not None
                    or registration.add_time_minutes is not None
                ),
                "waitlist_ticket": assigned.ticket_number if assigned else "",
                "waitlist_guest": assigned.guest_label if assigned else "",
                "is_waitlist_assigned": assigned is not None,
                "gamemode_spectator": bool(session.gamemode_spectator) if session else False,
                "play_gamemode": play_gamemode,
                "prefer_spectator": bool(registration.prefer_spectator),
                "spawn_regions": regions_for_builder_choices(registration),
                "station_name": (
                    session.station.name if session and getattr(session, "station_id", None) else ""
                ),
            }
        )
    if include_presence:
        presence_by_ms = _presence_lookup_for_cards(
            [c["ms_username"] for c in cards],
            paper_override=False,
        )
        for card in cards:
            _attach_presence(card, presence_by_ms)
    else:
        for card in cards:
            card["proxy_state"] = ""
            card["proxy_server"] = ""
            card["proxy_label"] = ""
            card["waiting_in_lobby"] = False
    return cards




def _is_connectivity_error(exc: BaseException) -> bool:
    raw = str(exc).lower()
    return (
        isinstance(exc, (OSError, ConnectionError))
        or "connection refused" in raw
        or "errno 111" in raw
        or "timed out" in raw
        or "timeout" in raw
    )


def _friendly_dashboard_exception(exc: BaseException) -> str:
    """Map infra failures to admin-readable German messages."""
    if _is_connectivity_error(exc):
        return str(
            _(
                "Minecraft-RCON nicht erreichbar (Paper/Velocity gestoppt oder Host/Port falsch). "
                "Bitte Server starten und unter Minecraft-Steuerung den RCON-Status prüfen."
            )
        )
    return str(_("Serverfehler: %(error)s") % {"error": str(exc)})


def _json_dashboard_or_error(*, ok: bool, message: str, build_cards) -> JsonResponse:
    """Build dashboard JSON; never return HTML 500 for AJAX clients."""
    try:
        cards = build_cards(include_presence=False)
        return JsonResponse(
            _json_dashboard_payload(cards, ok=ok, message=message),
            status=200 if ok else 400,
        )
    except Exception as exc:
        logger.exception("[minecraft_session] dashboard JSON build failed")
        return JsonResponse(
            {
                "ok": False,
                "message": _("Serverfehler beim Laden der Sessions: %(error)s")
                % {"error": str(exc)},
                "accounts": [],
            },
            status=500,
        )


def _run_dashboard_post(request, *, handle_action, build_cards, redirect_name: str):
    """POST handler shared by player/builder dashboards."""
    action = (request.POST.get("action") or "").strip()
    account = (request.POST.get("account") or "").strip()
    try:
        if action not in VALID_ACTIONS or (action not in BULK_ACTIONS and not account):
            ok, message = False, str(_("Ungültige Aktion."))
            messages.error(request, message)
        else:
            ok, message = handle_action(request, action, account)
    except Exception as exc:
        logger.exception(
            "[minecraft_session] dashboard action failed action=%s account=%s",
            action,
            account,
        )
        if _wants_json(request):
            msg = _friendly_dashboard_exception(exc)
            return JsonResponse(
                {"ok": False, "message": msg, "accounts": []},
                status=400 if _is_connectivity_error(exc) else 500,
            )
        raise
    if _wants_json(request):
        return _json_dashboard_or_error(ok=ok, message=message, build_cards=build_cards)
    return redirect(redirect_name)

def _wants_json(request) -> bool:
    if request.GET.get("format") == "json":
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept


def _json_dashboard_payload(cards: list[dict], *, ok: bool = True, message: str = "") -> dict:
    return {
        "ok": ok,
        "message": message,
        "accounts": [
            _session_payload(c["account_name"], c["session"], card=c) for c in cards
        ],
        "server_time": timezone.now().isoformat(),
    }


def _post_wants_spawn(request) -> bool:
    """True when the start/spawn checkbox was checked."""
    raw = (request.POST.get("teleport_to_spawn") or "").strip().lower()
    return raw in {"1", "on", "true", "yes"}


def _post_spawn_region_id(request) -> str:
    """Optional protected-region pk from Bau-Session start form."""
    return (request.POST.get("spawn_region_id") or "").strip()


def _handle_kick_all(request, *, account_type: str) -> tuple[bool, str]:
    try:
        ok_count, errors = end_all_active_sessions(account_type=account_type)
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    if ok_count == 0 and not errors:
        msg = str(_("Keine aktiven Sessions zum Beenden."))
        messages.error(request, msg)
        return False, msg
    if errors and ok_count == 0:
        msg = _("Kick aller Sessions fehlgeschlagen: %(error)s") % {
            "error": "; ".join(errors[:3])
        }
        messages.error(request, msg)
        return False, str(msg)
    if errors:
        msg = _(
            "%(ok)s Session(s) beendet; %(fail)s fehlgeschlagen."
        ) % {"ok": ok_count, "fail": len(errors)}
        messages.warning(request, msg)
        return True, str(msg)
    msg = _("Alle %(ok)s aktiven Session(s) beendet.") % {"ok": ok_count}
    messages.success(request, msg)
    return True, str(msg)


def _handle_start_all(request, *, account_type: str) -> tuple[bool, str]:
    try:
        ok_count, errors = start_all_idle_sessions(
            account_type=account_type,
            user=request.user,
            teleport_to_spawn=_post_wants_spawn(request),
        )
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    if ok_count == 0 and not errors:
        msg = str(_("Keine Sessions zum Starten (kein Warteraum / idle)."))
        messages.error(request, msg)
        return False, msg
    if errors and ok_count == 0:
        msg = _("Start aller Sessions fehlgeschlagen: %(error)s") % {
            "error": "; ".join(errors[:3])
        }
        messages.error(request, msg)
        return False, str(msg)
    if errors:
        msg = _(
            "%(ok)s Session(s) gestartet; %(fail)s fehlgeschlagen."
        ) % {"ok": ok_count, "fail": len(errors)}
        messages.warning(request, msg)
        return True, str(msg)
    msg = _("Alle %(ok)s Session(s) gestartet.") % {"ok": ok_count}
    messages.success(request, msg)
    return True, str(msg)


def _handle_spawn_all(request, *, account_type: str) -> tuple[bool, str]:
    try:
        ok_count, errors = teleport_all_active_to_spawn(account_type=account_type)
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    if ok_count == 0 and not errors:
        msg = str(_("Keine aktiven Sessions zum Spawn-Teleport."))
        messages.error(request, msg)
        return False, msg
    if errors and ok_count == 0:
        msg = _("Spawn-Teleport fehlgeschlagen: %(error)s") % {
            "error": "; ".join(errors[:3])
        }
        messages.error(request, msg)
        return False, str(msg)
    if errors:
        msg = _(
            "%(ok)s Spieler zum Spawn; %(fail)s fehlgeschlagen."
        ) % {"ok": ok_count, "fail": len(errors)}
        messages.warning(request, msg)
        return True, str(msg)
    msg = _("Alle %(ok)s aktiven Spieler zum Spawn teleportiert.") % {"ok": ok_count}
    messages.success(request, msg)
    return True, str(msg)


def _handle_set_all_gamemode(
    request,
    *,
    account_type: str,
) -> tuple[bool, str]:
    mode = (request.POST.get("mode") or "").strip().lower()
    if mode not in VALID_GAMEMODES:
        msg = str(_("Ungültiger Spielmodus."))
        messages.error(request, msg)
        return False, msg
    try:
        ok_count, errors = set_all_active_gamemodes(mode, account_type=account_type)
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    if ok_count == 0 and not errors:
        msg = str(_("Keine aktiven Sessions zum Umschalten."))
        messages.error(request, msg)
        return False, msg
    if errors and ok_count == 0:
        msg = _("Spielmodus-Umschaltung fehlgeschlagen: %(error)s") % {
            "error": "; ".join(errors[:3])
        }
        messages.error(request, msg)
        return False, str(msg)
    if errors:
        msg = _(
            "Spielmodus %(mode)s für %(ok)s Session(s) gesetzt; "
            "%(fail)s fehlgeschlagen."
        ) % {"mode": mode, "ok": ok_count, "fail": len(errors)}
        messages.warning(request, msg)
        return True, str(msg)
    msg = _("Spielmodus %(mode)s für alle %(ok)s aktiven Session(s) gesetzt.") % {
        "mode": mode,
        "ok": ok_count,
    }
    messages.success(request, msg)
    return True, str(msg)


def _post_ms_username(request) -> str:
    return (request.POST.get("ms_username") or "").strip()


def _post_station_id(request) -> str:
    return (request.POST.get("station_id") or "").strip()


def _session_start_context() -> dict:
    from minecraft.services.station_admin import (
        allowlist_is_enforced,
        list_allowed_ms_usernames,
        stations_for_role,
    )

    return {
        "allowlist_enforced": allowlist_is_enforced(),
        "allowed_ms_logins": list_allowed_ms_usernames(),
        "play_stations": stations_for_role("play", only_free=False),
        "builder_stations": stations_for_role("builder", only_free=False),
        "stations_url": "/admin/minecraft/stations/",
    }


def _handle_player_action(request, action: str, account: str) -> tuple[bool, str]:
    if action == "set_all_gamemode":
        return _handle_set_all_gamemode(request, account_type=MCSession.ACCOUNT_PLAYER)
    if action == "kick_all":
        return _handle_kick_all(request, account_type=MCSession.ACCOUNT_PLAYER)
    if action == "start_all":
        return _handle_start_all(request, account_type=MCSession.ACCOUNT_PLAYER)
    if action == "spawn_all":
        return _handle_spawn_all(request, account_type=MCSession.ACCOUNT_PLAYER)
    try:
        if action == "start":
            session = start_player_session(
                account,
                user=request.user,
                teleport_to_spawn=_post_wants_spawn(request),
                ms_username=_post_ms_username(request) or None,
                station_id=_post_station_id(request) or None,
            )
            msg = _("Session gestartet: %(name)s (%(min)s Min.)") % {
                "name": session.account_name,
                "min": session.duration_minutes,
            }
            if session.ms_username:
                msg = f"{msg} · MS: {session.ms_username}"
            messages.success(request, msg)
            return True, str(msg)
        if action == "teleport_spawn":
            session = teleport_session_to_spawn(account)
            msg = _("Zum Spawn teleportiert: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "kick":
            session = end_session(account)
            msg = _("Session beendet: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "add_time":
            session = add_session_time(account)
            added = resolve_add_time_for_session(session)
            msg = _("Zeit verlängert: %(name)s (+%(min)s Min., Ende %(ends)s)") % {
                "name": session.account_name,
                "min": added,
                "ends": timezone.localtime(session.ends_at).strftime("%H:%M"),
            }
            messages.success(request, msg)
            return True, str(msg)
        if action == "toggle_spectator":
            session = toggle_session_spectator(account)
            if session.gamemode_spectator:
                msg = _("Spectator aktiv: %(name)s") % {"name": session.account_name}
            else:
                msg = _("Spielmodus aktiv: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "set_gamemode":
            mode = (request.POST.get("mode") or "").strip().lower()
            if mode not in VALID_GAMEMODES:
                msg = str(_("Ungültiger Spielmodus."))
                messages.error(request, msg)
                return False, msg
            session = set_session_gamemode(account, mode)
            msg = _("Spielmodus %(mode)s: %(name)s") % {
                "mode": session.play_gamemode,
                "name": session.account_name,
            }
            messages.success(request, msg)
            return True, str(msg)
    except MissingMicrosoftLoginError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except MsAllowlistError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except StationBusyError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except AccountNotFoundError:
        msg = _("Account nicht gefunden: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except AccountAlreadyActiveError:
        msg = _("Session bereits aktiv: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except SessionNotActiveError:
        msg = _("Keine aktive Session: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except RconSequenceError as exc:
        msg = _("RCON fehlgeschlagen: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    return False, str(_("Ungültige Aktion."))


def _handle_builder_action(request, action: str, account: str) -> tuple[bool, str]:
    if action == "set_all_gamemode":
        return _handle_set_all_gamemode(request, account_type=MCSession.ACCOUNT_BUILDER)
    if action == "kick_all":
        return _handle_kick_all(request, account_type=MCSession.ACCOUNT_BUILDER)
    if action == "start_all":
        return _handle_start_all(request, account_type=MCSession.ACCOUNT_BUILDER)
    if action == "spawn_all":
        return _handle_spawn_all(request, account_type=MCSession.ACCOUNT_BUILDER)
    try:
        if action == "start":
            session = start_builder_session(
                account,
                user=request.user,
                teleport_to_spawn=_post_wants_spawn(request),
                spawn_region_id=_post_spawn_region_id(request) or None,
                ms_username=_post_ms_username(request) or None,
                station_id=_post_station_id(request) or None,
            )
            msg = _("Builder-Session gestartet: %(name)s (%(min)s Min.)") % {
                "name": session.account_name,
                "min": session.duration_minutes,
            }
            if session.ms_username:
                msg = f"{msg} · MS: {session.ms_username}"
            messages.success(request, msg)
            return True, str(msg)
        if action == "teleport_spawn":
            session = teleport_session_to_spawn(account)
            msg = _("Zum Spawn teleportiert: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "kick":
            session = end_session(account)
            msg = _("Session beendet: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "add_time":
            session = add_session_time(account)
            added = resolve_add_time_for_session(session)
            msg = _("Zeit verlängert: %(name)s (+%(min)s Min., Ende %(ends)s)") % {
                "name": session.account_name,
                "min": added,
                "ends": timezone.localtime(session.ends_at).strftime("%H:%M"),
            }
            messages.success(request, msg)
            return True, str(msg)
        if action == "toggle_spectator":
            session = toggle_session_spectator(account)
            if session.gamemode_spectator:
                msg = _("Spectator aktiv: %(name)s") % {"name": session.account_name}
            else:
                msg = _("Spielmodus aktiv: %(name)s") % {"name": session.account_name}
            messages.success(request, msg)
            return True, str(msg)
        if action == "set_gamemode":
            mode = (request.POST.get("mode") or "").strip().lower()
            if mode not in VALID_GAMEMODES:
                msg = str(_("Ungültiger Spielmodus."))
                messages.error(request, msg)
                return False, msg
            session = set_session_gamemode(account, mode)
            msg = _("Spielmodus %(mode)s: %(name)s") % {
                "mode": session.play_gamemode,
                "name": session.account_name,
            }
            messages.success(request, msg)
            return True, str(msg)
    except MissingMicrosoftLoginError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except MsAllowlistError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except StationBusyError as exc:
        messages.error(request, str(exc))
        return False, str(exc)
    except AccountNotFoundError:
        msg = _("Account nicht gefunden: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except AccountAlreadyActiveError:
        msg = _("Session bereits aktiv: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except SessionNotActiveError:
        msg = _("Keine aktive Session: %(name)s") % {"name": account}
        messages.error(request, msg)
        return False, str(msg)
    except RconSequenceError as exc:
        msg = _("RCON fehlgeschlagen: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    except SessionControlError as exc:
        msg = _("Session-Fehler: %(error)s") % {"error": str(exc)}
        messages.error(request, msg)
        return False, str(msg)
    return False, str(_("Ungültige Aktion."))


@user_passes_test(can_manage_player_sessions)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_player_sessions(request):
    if request.method == "POST":
        return _run_dashboard_post(
            request,
            handle_action=_handle_player_action,
            build_cards=_build_player_cards,
            redirect_name="admin:minecraft_player_sessions",
        )

    if request.GET.get("format") == "json":
        _expire_sessions_if_due()
        cards = _build_player_cards()
        return JsonResponse(_json_dashboard_payload(cards))

    _expire_sessions_if_due(force=True)
    cards = _build_player_cards()
    active_count = sum(1 for c in cards if c.get("is_active"))
    idle_count = len(cards) - active_count

    return render(
        request,
        "admin/minecraft/minecraft_player_sessions.html",
        {
            "title": _("Spieler-Sessions"),
            "cards": cards,
            "active_session_count": active_count,
            "idle_session_count": idle_count,
            "add_minutes": _add_minutes(),
            "default_duration": _player_duration(),
            "global_add_minutes": _add_minutes(),
            "global_default_duration": _player_duration(),
            "player_session_active_hint": (
                MinecraftIntegrationConfig.get_config().player_session_active_hint.strip()
            ),
            "dashboard_kind": "player",
            "poll_url": request.path + "?format=json",
            "proxy_presence_poll_seconds": _proxy_presence_poll_seconds(),
            "proxy_presence_poll_fast_seconds": _proxy_presence_poll_fast_seconds(),
            **_session_start_context(),
        },
    )


@user_passes_test(can_manage_builder_sessions)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_builder_sessions(request):
    if request.method == "POST":
        return _run_dashboard_post(
            request,
            handle_action=_handle_builder_action,
            build_cards=_build_builder_cards,
            redirect_name="admin:minecraft_builder_sessions",
        )

    if request.GET.get("format") == "json":
        _expire_sessions_if_due()
        cards = _build_builder_cards()
        return JsonResponse(_json_dashboard_payload(cards))

    _expire_sessions_if_due(force=True)
    cards = _build_builder_cards()
    active_count = sum(1 for c in cards if c.get("is_active"))
    idle_count = len(cards) - active_count

    return render(
        request,
        "admin/minecraft/minecraft_builder_sessions.html",
        {
            "title": _("Bau-Sessions"),
            "cards": cards,
            "active_session_count": active_count,
            "idle_session_count": idle_count,
            "add_minutes": _add_minutes(),
            "default_duration": _builder_duration(),
            "global_add_minutes": _add_minutes(),
            "global_default_duration": _builder_duration(),
            "builder_session_active_hint": (
                MinecraftIntegrationConfig.get_config().builder_session_active_hint.strip()
            ),
            "dashboard_kind": "builder",
            "poll_url": request.path + "?format=json",
            "proxy_presence_poll_seconds": _proxy_presence_poll_seconds(),
            "proxy_presence_poll_fast_seconds": _proxy_presence_poll_fast_seconds(),
            **_session_start_context(),
        },
    )
