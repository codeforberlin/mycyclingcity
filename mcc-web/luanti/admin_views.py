# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_views.py
# @note    Custom Django Admin pages for Luanti (mobile-first).

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from luanti.consumers import LuantiEventConsumer
from luanti.models import (
    LuantiAccount,
    LuantiArenaLane,
    LuantiArenaMotionSettings,
    LuantiBridgeConnection,
    LuantiCityPreset,
    LuantiIntegrationConfig,
    LuantiSession,
    LuantiShopCategory,
    LuantiStation,
)
from luanti.services.arena import cart_command
from luanti.services.bridge_connection import get_connected_server_ids
from luanti.services.city import mark_preset_run, preset_event_payload
from luanti.services.permissions import (
    can_access_luanti_control,
    user_can_access_luanti_arena,
    user_can_access_luanti_city,
    user_can_access_luanti_shop,
    user_can_manage_luanti_accounts,
    user_can_manage_luanti_sessions,
    user_can_manage_luanti_stations,
)
from luanti.services.session_control import (
    SessionError,
    account_duration_bounds,
    account_time_step_minutes,
    expire_due_sessions,
    extend_session,
    pause_session,
    reduce_session,
    resolve_duration_minutes,
    resume_session,
    set_session_mode,
    start_session,
)
from luanti.services.presence import list_waiting, purge_stale_waiting


def _account_duration_meta(account: LuantiAccount) -> dict:
    """Display + form defaults for session duration on session tiles."""
    step = account_time_step_minutes(account)
    if account.session_unlimited:
        return {
            "unlimited": True,
            "default_minutes": 0,
            "min_minutes": None,
            "max_minutes": None,
            "step": step,
        }
    lo, hi = account_duration_bounds(account)
    return {
        "unlimited": False,
        "default_minutes": resolve_duration_minutes(account),
        "min_minutes": lo,
        "max_minutes": hi,
        "step": step,
    }


def _format_remaining_seconds(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _get_luanti_script_path() -> Path:
    script_path = Path(settings.BASE_DIR) / "scripts" / "luanti_server.sh"
    if script_path.exists():
        return script_path
    return Path(settings.BASE_DIR).resolve() / "scripts" / "luanti_server.sh"


def _luanti_script_env() -> dict[str, str]:
    env = os.environ.copy()
    env["MCC_LUANTI_SERVER_DIR"] = str(getattr(settings, "MCC_LUANTI_SERVER_DIR", "") or "")
    env["MCC_LUANTI_SERVER_PIDFILE"] = str(
        getattr(settings, "MCC_LUANTI_SERVER_PIDFILE", "") or ""
    )
    env["MCC_LUANTI_SERVER_LOG"] = str(getattr(settings, "MCC_LUANTI_SERVER_LOG", "") or "")
    env["MCC_LUANTI_WORLD"] = str(getattr(settings, "MCC_LUANTI_WORLD", "world") or "world")
    env["MCC_LUANTI_CONFIG"] = str(getattr(settings, "MCC_LUANTI_CONFIG", "") or "")
    env["MCC_LUANTI_BIN_NAME"] = str(
        getattr(settings, "MCC_LUANTI_BIN_NAME", "luantiserver") or "luantiserver"
    )
    env["MCC_LUANTI_STOP_WAIT"] = str(getattr(settings, "MCC_LUANTI_STOP_WAIT", 30))
    return env


def _run_luanti_script(action: str, *, timeout: int = 60) -> dict:
    script_path = _get_luanti_script_path()
    if not script_path.exists():
        return {"ok": False, "running": False, "error": _("Script not found"), "output": ""}
    if not os.access(script_path, os.X_OK):
        return {
            "ok": False,
            "running": False,
            "error": _("Script not executable"),
            "output": "",
        }
    try:
        result = subprocess.run(
            [str(script_path), action],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_luanti_script_env(),
        )
        output = (result.stdout or "") + (result.stderr or "")
        running = action == "status" and result.returncode == 0
        if action in ("start", "restart"):
            running = result.returncode == 0
        if action == "stop":
            running = False
        return {
            "ok": result.returncode == 0,
            "running": running,
            "output": output.strip(),
            "error": "" if result.returncode == 0 else output.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "running": False,
            "error": _("Timeout"),
            "output": _("Timeout"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "running": False, "error": str(exc), "output": str(exc)}


def _get_luanti_server_status() -> dict:
    status = _run_luanti_script("status", timeout=10)
    return {
        "running": bool(status.get("running")),
        "output": status.get("output") or "",
        "error": status.get("error") or "",
        "dir": getattr(settings, "MCC_LUANTI_SERVER_DIR", ""),
        "world": getattr(settings, "MCC_LUANTI_WORLD", "world"),
        "log": getattr(settings, "MCC_LUANTI_SERVER_LOG", ""),
    }


@user_passes_test(can_access_luanti_control)
@staff_member_required
def luanti_control(request):
    config = LuantiIntegrationConfig.get_config()
    connected = get_connected_server_ids()
    bridges = list(LuantiBridgeConnection.objects.order_by("server_id"))
    server_status = _get_luanti_server_status()
    context = {
        "title": _("Luanti Control"),
        "config": config,
        "connected_ids": connected,
        "bridges": bridges,
        "bridge_online": bool(connected),
        "server_status": server_status,
        "luanti_log_key": "luanti_server",
    }
    return render(request, "admin/luanti/luanti_control.html", context)


@user_passes_test(can_access_luanti_control)
@staff_member_required
@require_POST
def luanti_action(request, action: str):
    allowed = {"server-start", "server-stop", "server-status", "server-restart"}
    if action not in allowed:
        return JsonResponse({"success": False, "error": _("Invalid action")}, status=400)

    script_action = {
        "server-start": "start",
        "server-stop": "stop",
        "server-status": "status",
        "server-restart": "restart",
    }[action]
    timeout = 120 if script_action in ("start", "stop", "restart") else 10
    result = _run_luanti_script(script_action, timeout=timeout)
    if script_action == "status":
        return JsonResponse(
            {
                "success": True,
                "running": result.get("running"),
                "message": result.get("output") or "",
            }
        )
    if result.get("ok"):
        return JsonResponse(
            {
                "success": True,
                "running": result.get("running"),
                "message": result.get("output") or _("OK"),
            }
        )
    return JsonResponse(
        {
            "success": False,
            "running": result.get("running"),
            "error": result.get("error") or result.get("output") or _("Failed"),
        },
        status=400,
    )


@user_passes_test(user_can_manage_luanti_accounts)
@staff_member_required
def luanti_accounts(request):
    from api.models import Group
    from luanti.services.passwords import provision_account_password
    from luanti.services.wallet import (
        candidate_wallet_groups,
        leaves_by_home_payload,
        wallet_payload,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            login_name = (request.POST.get("login_name") or "").strip()
            id_tag = (request.POST.get("id_tag") or login_name).strip()
            password = (request.POST.get("login_password") or "").strip()
            home_id = request.POST.get("assigned_to_group") or None
            wallet_id = request.POST.get("active_wallet") or None
            wallet_mode = request.POST.get("wallet_mode") or LuantiAccount.WALLET_FIXED
            if login_name:
                defaults = {
                    "id_tag": id_tag or login_name,
                    "allowed_modes": ["play", "build", "watch"],
                    "default_mode": "play",
                    "wallet_mode": wallet_mode
                    if wallet_mode in dict(LuantiAccount.WALLET_MODE_CHOICES)
                    else LuantiAccount.WALLET_FIXED,
                }
                if home_id:
                    defaults["assigned_to_group_id"] = int(home_id)
                if wallet_id:
                    defaults["active_wallet_id"] = int(wallet_id)
                account, created = LuantiAccount.objects.get_or_create(
                    login_name=login_name,
                    defaults=defaults,
                )
                if created or not account.login_password or password:
                    provision_account_password(account, password or None)
                    messages.success(
                        request,
                        _("Account angelegt. Passwort: %(pw)s")
                        % {"pw": account.login_password},
                    )
                else:
                    messages.info(request, _("Account existiert bereits."))
            return redirect("admin:luanti_accounts")
        if action == "toggle":
            account = get_object_or_404(LuantiAccount, pk=request.POST.get("account_id"))
            account.is_active = not account.is_active
            account.save(update_fields=["is_active", "updated_at"])
            messages.success(request, _("Account aktualisiert."))
            return redirect("admin:luanti_accounts")
        if action == "reset_password":
            account = get_object_or_404(LuantiAccount, pk=request.POST.get("account_id"))
            password = (request.POST.get("login_password") or "").strip()
            provision_account_password(account, password or None)
            messages.success(
                request,
                _("Passwort neu gesetzt: %(pw)s") % {"pw": account.login_password},
            )
            return redirect("admin:luanti_accounts")
        if action == "set_wallet":
            account = get_object_or_404(LuantiAccount, pk=request.POST.get("account_id"))
            home_id = request.POST.get("assigned_to_group") or ""
            wallet_id = request.POST.get("active_wallet") or ""
            wallet_mode = request.POST.get("wallet_mode") or LuantiAccount.WALLET_FIXED
            account.assigned_to_group_id = int(home_id) if home_id else None
            account.active_wallet_id = int(wallet_id) if wallet_id else None
            if wallet_mode in dict(LuantiAccount.WALLET_MODE_CHOICES):
                account.wallet_mode = wallet_mode
            # Reject wallet outside selected TOP's leaves.
            if account.assigned_to_group_id and account.active_wallet_id:
                allowed = {
                    g.pk for g in candidate_wallet_groups(account.assigned_to_group)
                }
                if account.active_wallet_id not in allowed:
                    account.active_wallet_id = None
                    messages.warning(
                        request,
                        _("Wallet gehört nicht zur Heimat-Gruppe — Auswahl zurückgesetzt."),
                    )
            account.save(
                update_fields=[
                    "assigned_to_group",
                    "active_wallet",
                    "wallet_mode",
                    "updated_at",
                ]
            )
            messages.success(request, _("Wallet-Zuweisung gespeichert."))
            return redirect("admin:luanti_accounts")
        if action == "set_session_limits":
            account = get_object_or_404(LuantiAccount, pk=request.POST.get("account_id"))

            def _opt_int(key):
                raw = (request.POST.get(key) or "").strip()
                if raw == "":
                    return None
                return max(0, int(raw))

            try:
                account.session_duration_minutes = _opt_int("session_duration_minutes")
                account.session_duration_min_minutes = _opt_int("session_duration_min_minutes")
                account.session_duration_max_minutes = _opt_int("session_duration_max_minutes")
                step_raw = _opt_int("session_add_minutes")
                account.session_add_minutes = (
                    max(1, step_raw) if step_raw is not None else None
                )
            except (TypeError, ValueError):
                messages.error(request, _("Ungültige Minutenwerte."))
                return redirect("admin:luanti_accounts")
            account.session_unlimited = bool(request.POST.get("session_unlimited"))
            if (
                account.session_duration_min_minutes is not None
                and account.session_duration_max_minutes is not None
                and account.session_duration_min_minutes
                > account.session_duration_max_minutes
            ):
                messages.error(request, _("Minimum darf nicht größer als Maximum sein."))
                return redirect("admin:luanti_accounts")
            account.save(
                update_fields=[
                    "session_duration_minutes",
                    "session_duration_min_minutes",
                    "session_duration_max_minutes",
                    "session_add_minutes",
                    "session_unlimited",
                    "updated_at",
                ]
            )
            messages.success(request, _("Session-Dauer gespeichert."))
            return redirect("admin:luanti_accounts")
    accounts = LuantiAccount.objects.select_related(
        "assigned_to_group", "active_wallet"
    ).order_by("sort_order", "login_name")
    top_groups = list(Group.objects.filter(parent__isnull=True).order_by("name"))
    account_rows = []
    for a in accounts:
        wp = wallet_payload(a)
        account_rows.append(
            {
                "account": a,
                "wallet": wp,
                "wallet_choices": candidate_wallet_groups(a.assigned_to_group),
            }
        )
    return render(
        request,
        "admin/luanti/luanti_accounts.html",
        {
            "title": _("Luanti-Accounts"),
            "account_rows": account_rows,
            "top_groups": top_groups,
            "leaves_by_home": leaves_by_home_payload(top_groups),
            "wallet_mode_choices": LuantiAccount.WALLET_MODE_CHOICES,
        },
    )


@user_passes_test(user_can_manage_luanti_sessions)
@staff_member_required
def luanti_sessions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        account_id = request.POST.get("account_id")
        session_id = request.POST.get("session_id")
        try:
            if action == "start" and account_id:
                account = get_object_or_404(LuantiAccount, pk=account_id)
                # Only start sessions for players currently waiting in-game
                # (same policy as Minecraft lobby freigabe).
                waiting_now = {
                    w.account_id for w in list_waiting()
                }
                if account.pk not in waiting_now:
                    raise SessionError("not_waiting")
                mode = request.POST.get("mode") or account.default_mode
                wallet_raw = request.POST.get("wallet_group") or ""
                wallet_group = None
                if wallet_raw:
                    from api.models import Group

                    wallet_group = Group.objects.filter(pk=int(wallet_raw)).first()
                duration_override = None
                if request.POST.get("session_unlimited"):
                    duration_override = 0
                else:
                    raw_dur = (request.POST.get("duration_minutes") or "").strip()
                    if raw_dur != "":
                        try:
                            duration_override = max(0, int(raw_dur))
                        except ValueError:
                            raise SessionError("invalid_duration")
                start_session(
                    account=account,
                    mode=mode,
                    source=LuantiSession.SOURCE_ADMIN,
                    duration=duration_override,
                    started_by=request.user,
                    wallet_group=wallet_group,
                )
                # Notify bridge so waiting client can apply session without re-login.
                LuantiEventConsumer.push_to_all_sync(
                    {
                        "type": "SESSION_STARTED",
                        "player": account.login_name,
                        "mode": mode,
                    }
                )
                messages.success(request, _("Session gestartet."))
            elif action == "set_default_mode" and account_id:
                account = get_object_or_404(LuantiAccount, pk=account_id)
                mode = (request.POST.get("mode") or "").strip()
                allowed = account.resolved_allowed_modes()
                if mode not in allowed:
                    raise SessionError("mode_not_allowed")
                account.default_mode = mode
                account.save(update_fields=["default_mode", "updated_at"])
            elif action == "kick" and session_id:
                # Do not end_session here — bridge kicks, on_leaveplayer posts
                # inventory to /session/leave/ which ends the session with payload.
                # If the player is offline, the bridge ends without inventory.
                session = get_object_or_404(LuantiSession, pk=session_id)
                LuantiEventConsumer.push_to_all_sync(
                    {
                        "type": "KICK_PLAYER",
                        "player": session.login_name,
                        "reason": "session_ended",
                    }
                )
                messages.success(
                    request,
                    _("Kick gesendet — Inventar wird beim Verlassen gesichert."),
                )
            elif action == "extend" and session_id:
                session = get_object_or_404(LuantiSession, pk=session_id)
                raw_add = (request.POST.get("adjust_minutes") or "").strip()
                try:
                    add = int(raw_add) if raw_add else None
                except ValueError:
                    raise SessionError("invalid_duration")
                extend_session(session, minutes=add)
                messages.success(request, _("Zeit verlängert."))
            elif action == "reduce" and session_id:
                session = get_object_or_404(LuantiSession, pk=session_id)
                raw_sub = (request.POST.get("adjust_minutes") or "").strip()
                try:
                    sub = int(raw_sub) if raw_sub else None
                except ValueError:
                    raise SessionError("invalid_duration")
                reduce_session(session, minutes=sub)
                messages.success(request, _("Zeit gekürzt."))
            elif action == "pause" and session_id:
                session = get_object_or_404(LuantiSession, pk=session_id)
                pause_session(session)
                # Freeze in-game: shout-only + Lua physics_override (no walk/fly).
                LuantiEventConsumer.push_to_all_sync(
                    {
                        "type": "SET_MODE",
                        "player": session.login_name,
                        "mode": "paused",
                        "paused": True,
                    }
                )
                messages.success(request, _("Session pausiert."))
            elif action == "resume" and session_id:
                session = get_object_or_404(LuantiSession, pk=session_id)
                resume_session(session)
                LuantiEventConsumer.push_to_all_sync(
                    {
                        "type": "SET_MODE",
                        "player": session.login_name,
                        "mode": session.mode,
                        "paused": False,
                    }
                )
                messages.success(request, _("Session fortgesetzt."))
            elif action == "set_mode" and session_id:
                session = get_object_or_404(LuantiSession, pk=session_id)
                mode = request.POST.get("mode") or ""
                # Do not switch mode in DB here — bridge posts /session/set-mode/
                # with the live inventory first (saves old mode, then switches).
                allowed = session.account.resolved_allowed_modes()
                if mode not in allowed:
                    raise SessionError("mode_not_allowed")
                if session.status == LuantiSession.STATUS_PAUSED:
                    raise SessionError("session_paused")
                from luanti.services.bridge_connection import bridge_is_online

                if bridge_is_online():
                    LuantiEventConsumer.push_to_all_sync(
                        {
                            "type": "SET_MODE",
                            "player": session.login_name,
                            "mode": mode,
                            "paused": False,
                        }
                    )
                    messages.success(
                        request,
                        _("Moduswechsel gesendet — Inventar wird gesichert."),
                    )
                else:
                    set_session_mode(session, mode)
                    messages.warning(
                        request,
                        _("Bridge offline — Modus ohne Live-Inventar gewechselt."),
                    )
        except SessionError as exc:
            messages.error(request, _("Fehler: %(code)s") % {"code": exc.code})
        return redirect("admin:luanti_sessions")

    purge_stale_waiting()
    waiting = list_waiting()
    waiting_account_ids = {w.account_id for w in waiting}
    accounts = (
        LuantiAccount.objects.filter(is_active=True)
        .select_related("assigned_to_group", "active_wallet")
        .order_by("sort_order", "login_name")
    )
    active = (
        LuantiSession.objects.filter(status__in=LuantiSession.OPEN_STATUSES)
        .select_related("account", "wallet_group")
        .order_by("-timestamp_start")
    )
    active_names = {s.login_name.lower() for s in active}
    from luanti.services.wallet import candidate_wallet_groups, wallet_payload

    idle_accounts = []
    for a in accounts:
        if a.pk not in waiting_account_ids and a.login_name.lower() not in active_names:
            idle_accounts.append(
                {
                    "account": a,
                    "wallet_choices": candidate_wallet_groups(a.assigned_to_group),
                    "resolved": wallet_payload(a),
                    "duration": _account_duration_meta(a),
                }
            )
    waiting_rows = []
    for w in waiting:
        waiting_rows.append(
            {
                "waiting": w,
                "wallet_choices": candidate_wallet_groups(w.account.assigned_to_group),
                "resolved": wallet_payload(w.account),
                "duration": _account_duration_meta(w.account),
            }
        )
    active_rows = []
    cfg = LuantiIntegrationConfig.get_config()
    now = timezone.now()
    for s in active:
        remaining_sec = None
        if s.status == LuantiSession.STATUS_PAUSED and s.remaining_seconds is not None:
            remaining_sec = max(0, int(s.remaining_seconds))
        elif s.ends_at:
            remaining_sec = max(0, int((s.ends_at - now).total_seconds()))
        active_rows.append(
            {
                "session": s,
                "resolved": wallet_payload(s.account, session=s),
                "remaining_seconds": remaining_sec,
                "remaining_label": _format_remaining_seconds(remaining_sec),
                "remaining_minutes": (
                    remaining_sec // 60 if remaining_sec is not None else None
                ),
                "adjust_step": account_time_step_minutes(s.account),
            }
        )
    return render(
        request,
        "admin/luanti/luanti_sessions.html",
        {
            "title": _("Luanti-Sessions"),
            "accounts": idle_accounts,
            "waiting_players": waiting_rows,
            "active_sessions": active_rows,
            "hint": cfg.session_active_hint,
            "adjust_step_default": cfg.session_add_minutes,
        },
    )


@user_passes_test(user_can_access_luanti_shop)
@staff_member_required
def luanti_shop_ops(request):
    from luanti.models import LuantiRegisteredItem, LuantiShopItem
    from luanti.services.material_map import registry_search
    from luanti.services.shop_import_mc import (
        add_registry_item_to_shop,
        import_minecraft_shop_catalog,
    )
    from luanti.services.shop_registry import registry_count, request_registry_dump

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "import_minecraft":
            result = import_minecraft_shop_catalog(only_enabled=True)
            messages.success(
                request,
                _(
                    "Minecraft-Import: %(cc)s/%(cu)s Kategorien neu/aktualisiert, "
                    "%(ic)s/%(iu)s Artikel neu/aktualisiert, %(sk)s übersprungen."
                )
                % {
                    "cc": result.categories_created,
                    "cu": result.categories_updated,
                    "ic": result.items_created,
                    "iu": result.items_updated,
                    "sk": result.items_skipped,
                },
            )
            if result.unmapped:
                preview = ", ".join(result.unmapped[:25])
                more = len(result.unmapped) - 25
                suffix = _(" … (+%(n)s)") % {"n": more} if more > 0 else ""
                messages.warning(
                    request,
                    _("Ohne Mapping (Auszug): %(list)s%(more)s")
                    % {"list": preview, "more": suffix},
                )
            return redirect("admin:luanti_shop_ops")
        if action == "refresh_registry":
            if request_registry_dump():
                messages.success(
                    request,
                    _(
                        "Registry-Dump an Bridge gesendet — in wenigen Sekunden "
                        "aktualisiert (Heartbeat)."
                    ),
                )
            else:
                messages.warning(request, _("Bridge nicht erreichbar / kein Dump eingeordnet."))
            return redirect("admin:luanti_shop_ops")
        if action == "add_from_registry":
            item_name = (request.POST.get("item_name") or "").strip()
            category_slug = (request.POST.get("category_slug") or "misc").strip() or "misc"
            display_name = (request.POST.get("display_name") or "").strip()
            try:
                price = int(request.POST.get("buy_price_velos") or "1")
            except ValueError:
                price = 1
            try:
                add_registry_item_to_shop(
                    item_name=item_name,
                    category_slug=category_slug,
                    buy_price_velos=price,
                    display_name=display_name,
                )
                messages.success(
                    request,
                    _("Artikel %(item)s zur Kategorie %(cat)s hinzugefügt.")
                    % {"item": item_name, "cat": category_slug},
                )
            except ValueError:
                messages.error(request, _("Ungültiger Itemstring."))
            return redirect("admin:luanti_shop_ops")

    categories = LuantiShopCategory.objects.prefetch_related("items").order_by("sort_order")
    q = (request.GET.get("q") or "").strip()
    registry_names = list(
        LuantiRegisteredItem.objects.order_by("item_name").values_list("item_name", flat=True)
    )
    search_hits = registry_search(q, registry_names, limit=80) if q else []
    return render(
        request,
        "admin/luanti/luanti_shop_ops.html",
        {
            "title": _("Luanti Shop"),
            "categories": categories,
            "item_count": LuantiShopItem.objects.count(),
            "registry_count": registry_count(),
            "registry_query": q,
            "registry_hits": search_hits,
            "category_slugs": list(
                LuantiShopCategory.objects.order_by("sort_order", "slug").values_list(
                    "slug", flat=True
                )
            ),
        },
    )


@user_passes_test(user_can_access_luanti_city)
@staff_member_required
def luanti_city(request):
    if request.method == "POST":
        slug = request.POST.get("slug")
        preset = get_object_or_404(LuantiCityPreset, slug=slug, enabled=True)
        payload = preset_event_payload(preset)
        sent = LuantiEventConsumer.push_to_all_sync(payload)
        mark_preset_run(
            preset,
            user=request.user,
            success=sent > 0,
            output=_("An %(n)s Bridge(s) gesendet") % {"n": sent}
            if sent
            else _("Keine Bridge verbunden"),
        )
        if sent:
            messages.success(request, _("Preset an Bridge gesendet/eingereiht."))
        else:
            messages.warning(request, _("Befehl konnte nicht zugestellt werden."))
        return redirect("admin:luanti_city")
    presets = LuantiCityPreset.objects.filter(enabled=True).order_by("sort_order", "name")
    return render(
        request,
        "admin/luanti/luanti_city.html",
        {"title": _("Luanti Stadtsteuerung"), "presets": presets},
    )


@user_passes_test(user_can_access_luanti_arena)
@staff_member_required
def luanti_arena(request):
    settings_obj = LuantiArenaMotionSettings.get_solo()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle":
            settings_obj.enabled = not settings_obj.enabled
            settings_obj.save(update_fields=["enabled", "updated_at"])
            messages.success(request, _("Arena-Status aktualisiert."))
        elif action == "clear_carts":
            LuantiEventConsumer.push_to_all_sync(cart_command("clear"))
            messages.success(request, _("Clear-Carts gesendet."))
        elif action == "spawn_lane":
            lane = get_object_or_404(LuantiArenaLane, pk=request.POST.get("lane_id"))
            LuantiEventConsumer.push_to_all_sync(
                cart_command(
                    "spawn",
                    lane_id=lane.pk,
                    start=[lane.start_x, lane.start_y, lane.start_z],
                    direction=[lane.direction_x, lane.direction_y, lane.direction_z],
                    speed=settings_obj.default_speed,
                )
            )
            messages.success(request, _("Spawn gesendet."))
        return redirect("admin:luanti_arena")
    lanes = LuantiArenaLane.objects.filter(enabled=True).order_by("sort_order", "name")
    return render(
        request,
        "admin/luanti/luanti_arena.html",
        {
            "title": _("Luanti Arena / Loren"),
            "settings": settings_obj,
            "lanes": lanes,
        },
    )


@user_passes_test(user_can_manage_luanti_stations)
@staff_member_required
def luanti_stations(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            name = (request.POST.get("name") or "").strip()
            if name:
                LuantiStation.objects.get_or_create(name=name)
                messages.success(request, _("Station angelegt."))
        elif action == "reload":
            station = get_object_or_404(LuantiStation, pk=request.POST.get("station_id"))
            LuantiEventConsumer.push_to_all_sync(
                {"type": "STATION_RELOAD", "station": station.name}
            )
            messages.success(request, _("Reload angefordert."))
        return redirect("admin:luanti_stations")
    stations = LuantiStation.objects.select_related("default_account").order_by(
        "sort_order", "name"
    )
    return render(
        request,
        "admin/luanti/luanti_stations.html",
        {"title": _("Luanti-Stationen"), "stations": stations},
    )
