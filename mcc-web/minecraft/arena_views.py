# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    arena_views.py
# @note    Operator UI for VeloArena motion control (assign / start / stop / reset).

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from config.logger_utils import get_logger
from minecraft.services.arena_motion.control import (
    ArenaControlError,
    assert_arena_sim_roster,
    auto_assign_active_sessions,
    get_status,
    request_avatars,
    request_clear_all,
    request_init,
    request_start,
    request_stop,
    set_assignments,
    set_continue_after_finish,
    set_race_mode,
    set_target_laps,
    set_time_limit_seconds,
    update_sim_rates,
)
from minecraft.services.arena_motion.cyclists import (
    cyclists_for_top_group,
    devices_for_top_group,
    top_groups_for_user,
)
from minecraft.services.preset_permissions import (
    user_can_manage_player_sessions,
    user_can_run_arena_sim,
)

logger = get_logger("minecraft")

SESSION_TOP_GROUP_KEY = "arena_top_group_id"


def can_manage_arena(user):
    return user_can_manage_player_sessions(user)


def can_run_arena_sim(user):
    return user_can_run_arena_sim(user)


def _parse_top_group_id(raw) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _resolve_top_group_id(request, *, from_post: bool = False) -> int | None:
    top_groups = list(top_groups_for_user(request.user))
    allowed = {g.id for g in top_groups}

    if from_post:
        candidate = _parse_top_group_id(request.POST.get("top_group_id"))
    else:
        candidate = _parse_top_group_id(request.GET.get("top_group"))
        if candidate is None:
            candidate = _parse_top_group_id(request.session.get(SESSION_TOP_GROUP_KEY))

    if candidate is not None and candidate in allowed:
        request.session[SESSION_TOP_GROUP_KEY] = candidate
        return candidate

    if len(top_groups) == 1:
        request.session[SESSION_TOP_GROUP_KEY] = top_groups[0].id
        return top_groups[0].id

    request.session.pop(SESSION_TOP_GROUP_KEY, None)
    return None


from minecraft.services.arena_motion.race_modes import (
    MODE_LABELS,
    default_race_mode,
    default_time_limit_seconds,
    time_limit_minutes_for_ui,
)


def _empty_status_fallback(**extra) -> dict:
    """Minimal status dict when get_status() fails (keeps race-mode UI usable)."""
    from minecraft.services.arena_motion.race_modes import (
        default_target_laps,
        uses_laps,
        uses_time_limit,
    )

    mode = default_race_mode()
    base = {
        "status": "idle",
        "race_mode": mode,
        "race_modes": [{"id": k, "label": v} for k, v in MODE_LABELS.items()],
        "target_laps": default_target_laps(),
        "time_limit_seconds": default_time_limit_seconds(),
        "time_limit_minutes": time_limit_minutes_for_ui(default_time_limit_seconds()),
        "uses_laps": uses_laps(mode),
        "uses_time_limit": uses_time_limit(mode),
        "continue_after_finish": False,
        "lane_cards": [],
        "result": {},
        "last_error": "",
        "initialized": False,
        "worker_heartbeat": None,
        "pending_command": None,
    }
    base.update(extra)
    return base


def _post_action(request) -> str:
    """Resolve arena control action from POST (avoid Django admin ``action`` quirks)."""
    if request.POST.get("save_race_mode"):
        return "save_mode"
    return (request.POST.get("arena_action") or request.POST.get("action") or "").strip()


def _parse_race_options(request) -> dict:
    """Parse race_mode / target_laps / time_limit / continue_after_finish from POST."""
    opts: dict = {}
    if "race_mode" in request.POST:
        opts["race_mode"] = (request.POST.get("race_mode") or "").strip()
    if "target_laps" in request.POST:
        opts["target_laps"] = int(request.POST.get("target_laps") or 5)
    # Prefer minutes field from UI; fall back to seconds / Integration default.
    if "time_limit_minutes" in request.POST:
        raw_minutes = str(request.POST.get("time_limit_minutes") or "").replace(",", ".").strip()
        if raw_minutes:
            minutes = float(raw_minutes)
        else:
            minutes = time_limit_minutes_for_ui(default_time_limit_seconds())
        opts["time_limit_seconds"] = max(30, int(round(minutes * 60)))
    elif "time_limit_seconds" in request.POST:
        opts["time_limit_seconds"] = int(
            request.POST.get("time_limit_seconds") or default_time_limit_seconds()
        )
    # Checkbox (+ optional hidden 0): use last posted value so checked → "1".
    if "continue_after_finish" in request.POST:
        raw = request.POST.getlist("continue_after_finish")
        opts["continue_after_finish"] = (raw[-1] if raw else "") in (
            "1",
            "on",
            "true",
            "True",
        )
    return opts


def _persist_race_options(request) -> None:
    opts = _parse_race_options(request)
    if "race_mode" in opts and opts["race_mode"]:
        set_race_mode(opts["race_mode"])
    if "target_laps" in opts:
        set_target_laps(opts["target_laps"])
    if "time_limit_seconds" in opts:
        set_time_limit_seconds(opts["time_limit_seconds"])
    if "continue_after_finish" in opts:
        set_continue_after_finish(opts["continue_after_finish"])


def _allowed_scope(request, top_groups) -> set[int] | None:
    allowed_ids = {g.id for g in top_groups}
    return None if request.user.is_superuser else allowed_ids


@staff_member_required
@user_passes_test(can_manage_arena)
@require_http_methods(["GET", "POST"])
def minecraft_arena_control(request):
    title = _("Velo-Arena Steuerung")
    error = ""
    if request.method == "POST":
        action = _post_action(request)
        try:
            if action == "save_mode":
                _persist_race_options(request)
                messages.success(request, _("Rennmodus gespeichert."))
                return redirect("admin:minecraft_arena_control")
            _persist_race_options(request)
            if action == "save_assignments":
                _resolve_top_group_id(request, from_post=True)
                lanes = request.POST.getlist("lane_id")
                cyclists = request.POST.getlist("cyclist")
                devices = request.POST.getlist("device_name")
                raw = []
                for index, lane_id in enumerate(lanes):
                    cyclist = cyclists[index] if index < len(cyclists) else ""
                    if not str(cyclist).strip():
                        continue
                    device_name = devices[index] if index < len(devices) else ""
                    raw.append(
                        {
                            "lane_id": lane_id,
                            "cyclist": cyclist,
                            "device_name": device_name,
                        }
                    )
                set_assignments(raw)
                messages.success(request, _("Zuweisungen gespeichert."))
            elif action == "auto_assign":
                top_group_id = _resolve_top_group_id(request, from_post=True)
                top_groups = list(top_groups_for_user(request.user))
                allowed_scope = _allowed_scope(request, top_groups)
                arena_sim_only = str(
                    request.POST.get("arena_sim_only") or ""
                ).lower() in {"1", "on", "true", "yes"}
                # top_group_id None = „Alle TOP-Gruppen“ (union of allowed / all for superuser)
                if (
                    top_group_id is not None
                    and allowed_scope is not None
                    and top_group_id not in allowed_scope
                ):
                    raise ArenaControlError(_("TOP-Gruppe nicht erlaubt."))
                result = auto_assign_active_sessions(
                    top_group_id,
                    arena_sim_only=arena_sim_only,
                    allowed_top_group_ids=allowed_scope,
                )
                if result.get("cleared"):
                    messages.warning(
                        request,
                        result.get("warning")
                        or _(
                            "Keine aktiven Radler — Bahnzuweisungen geleert."
                        ),
                    )
                else:
                    msg = _(
                        "%(assigned)d aktive Radler erkannt und Bahnen zugeordnet "
                        "(%(detected)d Session(s) gesamt)."
                    ) % {
                        "assigned": result["assigned"],
                        "detected": result["detected"],
                    }
                    preferred_hits = int(result.get("preferred_hits") or 0)
                    if preferred_hits:
                        msg += " " + _(
                            "%(n)d über bevorzugte Stationen (Bahn-Setup)."
                        ) % {"n": preferred_hits}
                    if result["overflow"]:
                        msg += " " + _(
                            "%(n)d weitere Session(s) ohne freie Bahn."
                        ) % {"n": result["overflow"]}
                    messages.success(request, msg)
            elif action == "start":
                opts = _parse_race_options(request)
                request_start(
                    target_laps=opts.get("target_laps"),
                    time_limit_seconds=opts.get("time_limit_seconds"),
                    race_mode=opts.get("race_mode"),
                    continue_after_finish=opts.get("continue_after_finish"),
                    sim_distance=False,
                )
                messages.success(request, _("Start gesendet."))
            elif action == "stop":
                request_stop()
                messages.success(request, _("Stop gesendet."))
            elif action == "init":
                request_init(kill_all=False)
                messages.success(
                    request,
                    _(
                        "Init: vorhandene Loren zum Start gesetzt, "
                        "fehlende Loren neu erzeugt."
                    ),
                )
            elif action == "clear_all":
                request_clear_all()
                messages.success(
                    request,
                    _(
                        "Reset: Arena-Loren gelöscht. Danach Init für neue Loren "
                        "(z. B. vor neuen Avataren)."
                    ),
                )
            elif action == "avatars":
                request_avatars()
            else:
                messages.error(request, _("Unbekannte Aktion."))
        except ArenaControlError as exc:
            messages.error(request, str(exc))
            error = str(exc)
        except Exception as exc:
            logger.exception("[arena_motion] control action failed")
            messages.error(request, str(exc))
            error = str(exc)
        return redirect("admin:minecraft_arena_control")

    try:
        status = get_status()
    except Exception as exc:
        logger.exception("[arena_motion] status failed")
        status = _empty_status_fallback(
            config_path="",
            sim_distance=False,
            kill_all_on_reset=False,
            last_error=str(exc),
        )
        error = str(exc)

    top_group_id = _resolve_top_group_id(request)
    top_groups = list(top_groups_for_user(request.user))
    allowed_scope = _allowed_scope(request, top_groups)
    cyclists = cyclists_for_top_group(
        top_group_id,
        allowed_top_group_ids=allowed_scope,
    )
    devices = devices_for_top_group(
        top_group_id,
        allowed_top_group_ids=allowed_scope,
    )
    assigned_cyclists = {
        (card.get("cyclist") or "").strip()
        for card in status.get("lane_cards") or []
        if (card.get("cyclist") or "").strip()
    }
    assigned_devices = {
        (card.get("device_name") or "").strip()
        for card in status.get("lane_cards") or []
        if (card.get("device_name") or "").strip()
    }
    available_cyclists = {c["user_id"] for c in cyclists}
    available_devices = {d["name"] for d in devices}
    orphan_assigned = sorted(assigned_cyclists - available_cyclists)
    orphan_devices = sorted(assigned_devices - available_devices)

    context = {
        "title": title,
        "status": status,
        "error": error,
        "top_groups": top_groups,
        "selected_top_group_id": top_group_id,
        "cyclists": cyclists,
        "devices": devices,
        "orphan_assigned": orphan_assigned,
        "orphan_devices": orphan_devices,
    }
    return render(request, "admin/minecraft/minecraft_arena_control.html", context)


@staff_member_required
@user_passes_test(lambda u: can_manage_arena(u) or can_run_arena_sim(u))
@require_GET
def minecraft_arena_status_json(request):
    """Live status for partial UI refresh (no full page reload)."""
    try:
        return JsonResponse(get_status())
    except Exception as exc:
        logger.exception("[arena_motion] status json failed")
        return JsonResponse({"status": "idle", "last_error": str(exc), "lane_cards": []}, status=500)


@staff_member_required
@user_passes_test(can_manage_arena)
@require_GET
def minecraft_arena_cyclists_json(request):
    """Cyclist options for the selected TOP group (lane dropdowns)."""
    top_groups = list(top_groups_for_user(request.user))
    allowed = {g.id for g in top_groups}
    top_group_id = _parse_top_group_id(request.GET.get("top_group"))
    if top_group_id is not None and top_group_id not in allowed:
        top_group_id = None
    if top_group_id is not None:
        request.session[SESSION_TOP_GROUP_KEY] = top_group_id
    elif "top_group" in request.GET and not request.GET.get("top_group"):
        request.session.pop(SESSION_TOP_GROUP_KEY, None)
        top_group_id = None
    search = request.GET.get("search", "")
    allowed_scope = _allowed_scope(request, top_groups)
    arena_sim_only = str(request.GET.get("arena_sim_only") or "").lower() in {
        "1",
        "true",
        "yes",
    }
    return JsonResponse(
        {
            "top_group_id": top_group_id,
            "cyclists": cyclists_for_top_group(
                top_group_id,
                search=search,
                allowed_top_group_ids=allowed_scope,
                arena_sim_only=arena_sim_only,
            ),
        }
    )


@staff_member_required
@user_passes_test(can_manage_arena)
@require_GET
def minecraft_arena_devices_json(request):
    """IoT device options for the selected TOP group (lane dropdowns)."""
    top_groups = list(top_groups_for_user(request.user))
    allowed = {g.id for g in top_groups}
    top_group_id = _parse_top_group_id(request.GET.get("top_group"))
    if top_group_id is not None and top_group_id not in allowed:
        top_group_id = None
    if top_group_id is not None:
        request.session[SESSION_TOP_GROUP_KEY] = top_group_id
    elif "top_group" in request.GET and not request.GET.get("top_group"):
        request.session.pop(SESSION_TOP_GROUP_KEY, None)
        top_group_id = None
    search = request.GET.get("search", "")
    allowed_scope = _allowed_scope(request, top_groups)
    arena_sim_only = str(request.GET.get("arena_sim_only") or "").lower() in {
        "1",
        "true",
        "yes",
    }
    return JsonResponse(
        {
            "top_group_id": top_group_id,
            "devices": devices_for_top_group(
                top_group_id,
                search=search,
                allowed_top_group_ids=allowed_scope,
                arena_sim_only=arena_sim_only,
            ),
        }
    )


@staff_member_required
@user_passes_test(can_run_arena_sim)
@require_http_methods(["GET", "POST"])
def minecraft_arena_sim(request):
    """
    Kid/operator-friendly distance simulation UI.

    Uses cyclists already assigned on the main Velo-Arena page; only rates +
    Init/Start/Stop/Reset are controlled here (permission: minecraft.run_arena_sim).
    """
    title = _("Arena-Simulation")
    error = ""
    if request.method == "POST":
        action = _post_action(request)
        try:
            if action == "save_mode":
                _persist_race_options(request)
                messages.success(request, _("Rennmodus gespeichert."))
                return redirect("admin:minecraft_arena_sim")
            _persist_race_options(request)
            if action in {"save_rates", "init", "start", "start_api"}:
                assert_arena_sim_roster()
                lanes = request.POST.getlist("lane_id")
                rates = request.POST.getlist("sim_rate_mps")
                raw = []
                for index, lane_id in enumerate(lanes):
                    rate_raw = rates[index] if index < len(rates) else ""
                    try:
                        rate = float(str(rate_raw).replace(",", ".") or 0)
                    except ValueError as exc:
                        raise ArenaControlError(
                            _("Ungültige Rate für Bahn %(lane)s") % {"lane": lane_id}
                        ) from exc
                    raw.append({"lane_id": lane_id, "sim_rate_mps": rate})
                update_sim_rates(raw)

            if action == "save_rates":
                messages.success(
                    request,
                    _("Sim-Raten übernommen — wirken sofort, auch während der Simulation."),
                )
            elif action == "init":
                request_init(kill_all=False)
                messages.success(
                    request,
                    _(
                        "Init: vorhandene Loren zum Start gesetzt, "
                        "fehlende Loren neu erzeugt."
                    ),
                )
            elif action == "start":
                opts = _parse_race_options(request)
                request_start(
                    target_laps=opts.get("target_laps"),
                    time_limit_seconds=opts.get("time_limit_seconds"),
                    race_mode=opts.get("race_mode"),
                    continue_after_finish=opts.get("continue_after_finish"),
                    sim_distance=True,
                    api_live_pulse=False,
                )
                messages.success(request, _("Simulation gestartet (intern Distanz → Motion)."))
            elif action == "start_api":
                opts = _parse_race_options(request)
                request_start(
                    target_laps=opts.get("target_laps"),
                    time_limit_seconds=opts.get("time_limit_seconds"),
                    race_mode=opts.get("race_mode"),
                    continue_after_finish=opts.get("continue_after_finish"),
                    sim_distance=False,
                    api_live_pulse=True,
                )
                messages.success(
                    request,
                    _("API-Live gestartet (Pulse → /api/update-data → Motion)."),
                )
            elif action == "stop":
                request_stop()
                messages.success(request, _("Stop gesendet."))
            elif action == "clear_all":
                request_clear_all()
                messages.success(
                    request,
                    _(
                        "Reset: Arena-Loren gelöscht. Danach Init für neue Loren "
                        "(z. B. vor neuen Avataren)."
                    ),
                )
            else:
                messages.error(request, _("Unbekannte Aktion."))
        except ArenaControlError as exc:
            messages.error(request, str(exc))
            error = str(exc)
        except Exception as exc:
            logger.exception("[arena_motion] sim action failed")
            messages.error(request, str(exc))
            error = str(exc)
        return redirect("admin:minecraft_arena_sim")

    try:
        status = get_status()
    except Exception as exc:
        logger.exception("[arena_motion] sim status failed")
        status = _empty_status_fallback(
            sim_distance=True,
            reference_mps=2.0,
            last_error=str(exc),
        )
        error = str(exc)

    context = {
        "title": title,
        "status": status,
        "error": error,
        "can_manage_full_arena": user_can_manage_player_sessions(request.user),
        "has_assigned_cyclists": any(
            (card.get("cyclist") or "").strip()
            for card in (status.get("lane_cards") or [])
        ),
    }
    return render(request, "admin/minecraft/minecraft_arena_sim.html", context)
