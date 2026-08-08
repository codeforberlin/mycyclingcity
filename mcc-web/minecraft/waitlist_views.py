# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    waitlist_views.py
# @note    Operator waitlist management and public/staff displays.

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from config.logger_utils import get_logger
from minecraft.models import MinecraftSessionWaitlistEntry
from minecraft.services.preset_permissions import (
    user_can_manage_builder_sessions,
    user_can_manage_player_sessions,
)
from minecraft.services.session_control import (
    AccountAlreadyActiveError,
    AccountNotFoundError,
    RconSequenceError,
    SessionControlError,
    SessionNotActiveError,
    expire_due_sessions,
)
from minecraft.services.waitlist_service import (
    WaitlistError,
    add_waitlist_entry,
    assign_builder_from_waitlist,
    assign_player_from_waitlist,
    build_display_payload,
    cancel_waitlist_entry,
    duration_from_velos,
    free_builder_registrations,
    free_play_accounts,
    generate_ticket_numbers,
    get_integration_config,
    unassign_waitlist_entry,
    waiting_entries,
)

logger = get_logger("minecraft")


def can_manage_any_waitlist(user):
    return user_can_manage_player_sessions(user) or user_can_manage_builder_sessions(user)


def _handle_waitlist_error(request, exc: Exception) -> None:
    if isinstance(exc, WaitlistError):
        messages.error(request, str(exc))
    elif isinstance(exc, (AccountNotFoundError, AccountAlreadyActiveError, SessionNotActiveError)):
        messages.error(request, str(exc))
    elif isinstance(exc, RconSequenceError):
        messages.error(request, _("RCON fehlgeschlagen: %(error)s") % {"error": str(exc)})
    elif isinstance(exc, SessionControlError):
        messages.error(request, _("Session-Fehler: %(error)s") % {"error": str(exc)})
    else:
        logger.exception("[waitlist] unexpected error")
        messages.error(request, _("Unerwarteter Fehler: %(error)s") % {"error": str(exc)})


@user_passes_test(can_manage_any_waitlist)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_waitlist_manage(request):
    config = get_integration_config()
    can_player = user_can_manage_player_sessions(request.user)
    can_builder = user_can_manage_builder_sessions(request.user)
    tab = (request.GET.get("tab") or request.POST.get("tab") or "player").strip()
    if tab == "builder" and not can_builder:
        tab = "player"
    if tab == "player" and not can_player and can_builder:
        tab = "builder"

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "add_player" and can_player:
                velos = int(request.POST.get("velos_cost") or 0)
                add_waitlist_entry(
                    queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                    ticket_number=request.POST.get("ticket_number") or "",
                    guest_label=request.POST.get("guest_label") or "",
                    velos_cost=velos,
                    internal_note=request.POST.get("internal_note") or "",
                    user=request.user,
                )
                messages.success(request, _("Spieler-Eintrag zur Warteliste hinzugefügt."))
            elif action == "add_builder" and can_builder:
                duration = int(request.POST.get("duration_minutes") or 0)
                add_waitlist_entry(
                    queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
                    ticket_number=request.POST.get("ticket_number") or "",
                    guest_label=request.POST.get("guest_label") or "",
                    velos_cost=0,
                    duration_minutes=duration if duration > 0 else None,
                    internal_note=request.POST.get("internal_note") or "",
                    user=request.user,
                )
                messages.success(request, _("Bau-Eintrag zur Warteliste hinzugefügt."))
            elif action == "generate_ticket":
                count = int(request.POST.get("ticket_count") or 1)
                tickets = generate_ticket_numbers(count)
                if len(tickets) == 1:
                    messages.success(
                        request,
                        _("Ticketnummer für Flyer erzeugt: %(ticket)s — bitte auf den Flyer schreiben.")
                        % {"ticket": tickets[0]},
                    )
                    return redirect(
                        f"{reverse('admin:minecraft_waitlist_manage')}?tab={tab}&ticket={tickets[0]}"
                    )
                messages.success(
                    request,
                    _("Ticketnummern für Flyer erzeugt: %(tickets)s")
                    % {"tickets": ", ".join(tickets)},
                )
                return redirect(
                    f"{reverse('admin:minecraft_waitlist_manage')}?tab={tab}&tickets={','.join(tickets)}"
                )
            elif action == "cancel":
                cancel_waitlist_entry(int(request.POST.get("entry_id") or 0))
                messages.success(request, _("Wartelisteneintrag abgebrochen."))
            elif action == "unassign":
                unassign_waitlist_entry(int(request.POST.get("entry_id") or 0))
                messages.success(request, _("Zuweisung aufgehoben — Eintrag wieder wartend."))
            elif action == "assign_player" and can_player:
                assign_player_from_waitlist(
                    int(request.POST.get("entry_id") or 0),
                    (request.POST.get("play_account") or "").strip(),
                    user=request.user,
                )
                messages.success(
                    request,
                    _(
                        "Arena zugewiesen. Freigabe (Login) bitte unter „Spieler-Sessions“ starten, "
                        "sobald der PC verbunden ist."
                    ),
                )
            elif action == "assign_builder" and can_builder:
                assign_builder_from_waitlist(
                    int(request.POST.get("entry_id") or 0),
                    (request.POST.get("builder_team") or "").strip(),
                    user=request.user,
                )
                messages.success(
                    request,
                    _(
                        "Bau-PC zugewiesen. Freigabe (Login) bitte unter „Bau-Sessions“ starten, "
                        "sobald der PC verbunden ist."
                    ),
                )
            else:
                messages.error(request, _("Ungültige Aktion oder fehlende Berechtigung."))
        except (ValueError, TypeError):
            messages.error(request, _("Ungültige Eingabe."))
        except Exception as exc:
            _handle_waitlist_error(request, exc)
        return redirect(f"{reverse('admin:minecraft_waitlist_manage')}?tab={tab}")

    try:
        expire_due_sessions()
    except Exception as exc:
        logger.warning("[waitlist] expire_due_sessions failed: %s", exc)

    public_url = request.build_absolute_uri(
        reverse("minecraft_waitlist_public_display", kwargs={"token": config.waitlist_public_token})
    )
    staff_display_url = reverse("admin:minecraft_waitlist_display")
    player_sessions_url = reverse("admin:minecraft_player_sessions")
    builder_sessions_url = reverse("admin:minecraft_builder_sessions")

    player_assigned = (
        list(
            MinecraftSessionWaitlistEntry.objects.filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            )
            .select_related("assigned_play_account")
            .order_by("queued_at")
        )
        if can_player
        else []
    )
    builder_assigned = (
        list(
            MinecraftSessionWaitlistEntry.objects.filter(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_BUILDER,
                status=MinecraftSessionWaitlistEntry.STATUS_ASSIGNED,
            )
            .select_related("assigned_builder_registration", "assigned_builder_registration__group")
            .order_by("queued_at")
        )
        if can_builder
        else []
    )

    context = {
        "title": _("Minecraft-Wartelisten"),
        "tab": tab,
        "config": config,
        "can_player": can_player,
        "can_builder": can_builder,
        "player_waiting": waiting_entries(MinecraftSessionWaitlistEntry.QUEUE_PLAYER) if can_player else [],
        "builder_waiting": waiting_entries(MinecraftSessionWaitlistEntry.QUEUE_BUILDER) if can_builder else [],
        "player_assigned": player_assigned,
        "builder_assigned": builder_assigned,
        "free_play_accounts": free_play_accounts() if can_player else [],
        "free_builder_teams": free_builder_registrations() if can_builder else [],
        "player_min_velos": config.player_min_velos,
        "player_velos_per_minute": config.player_velos_per_minute,
        "default_player_minutes": duration_from_velos(config.player_min_velos, config=config),
        "public_url": public_url,
        "staff_display_url": staff_display_url,
        "player_sessions_url": player_sessions_url,
        "builder_sessions_url": builder_sessions_url,
        "poll_url": reverse("admin:minecraft_waitlist_display") + "?format=json",
        "prefill_ticket": (request.GET.get("ticket") or "").strip(),
        "generated_tickets": [
            t.strip() for t in (request.GET.get("tickets") or "").split(",") if t.strip()
        ],
    }
    return render(request, "admin/minecraft/minecraft_waitlist_manage.html", context)


@user_passes_test(can_manage_any_waitlist)
@staff_member_required
@require_GET
def minecraft_waitlist_display(request):
    if request.GET.get("format") == "json":
        return JsonResponse(build_display_payload(include_private=True))

    config = get_integration_config()
    payload = build_display_payload(include_private=True)
    return render(
        request,
        "admin/minecraft/minecraft_waitlist_display.html",
        {
            "title": _("Wartelisten-Anzeige (Operator)"),
            "include_private": True,
            "config": config,
            "payload": payload,
            "poll_url": request.path + "?format=json",
            "manage_url": reverse("admin:minecraft_waitlist_manage"),
            "is_public": False,
        },
    )


@require_GET
def minecraft_waitlist_public_display(request, token: str):
    config = get_integration_config()
    if not config.waitlist_public_enabled:
        raise Http404
    if (token or "").strip() != (config.waitlist_public_token or "").strip():
        raise Http404

    if request.GET.get("format") == "json":
        return JsonResponse(build_display_payload(include_private=False))

    payload = build_display_payload(include_private=False)
    return render(
        request,
        "admin/minecraft/minecraft_waitlist_display.html",
        {
            "title": _("Minecraft-Warteliste"),
            "include_private": False,
            "config": config,
            "payload": payload,
            "poll_url": request.path + "?format=json",
            "manage_url": "",
            "is_public": True,
        },
    )
