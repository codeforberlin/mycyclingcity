# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Admin UI: physical PC stations and MS allowlist.

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from minecraft.models import MinecraftPlayAccount, MinecraftStation
from minecraft.services.preset_permissions import user_can_manage_minecraft_stations
from minecraft.services.station_admin import (
    StationAdminError,
    add_allowlist_entry,
    allowlist_is_enforced,
    create_station,
    delete_allowlist_entry,
    delete_station,
    list_allowlist_entries,
    list_station_dtos,
    set_allowlist_active,
    update_station,
)


def _bool_from_post(value) -> bool:
    return str(value or "").lower() in {"1", "true", "on", "yes"}


@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_stations(request):
    if not user_can_manage_minecraft_stations(request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden(_("Keine Berechtigung für Stationen."))

    include_inactive = (request.GET.get("inactive") or "0") == "1"
    edit_id = (request.GET.get("edit") or "").strip()

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "create_station":
                create_station(
                    {
                        "name": request.POST.get("name"),
                        "location": request.POST.get("location"),
                        "role": request.POST.get("role"),
                        "sort_order": request.POST.get("sort_order"),
                        "default_play_account_id": request.POST.get("default_play_account_id"),
                        "note": request.POST.get("note"),
                        "is_active": True,
                    },
                    user=request.user,
                )
                messages.success(request, _("Station angelegt."))
            elif action == "save_station":
                station = MinecraftStation.objects.filter(pk=int(request.POST.get("station_id") or 0)).first()
                if station is None:
                    raise StationAdminError(_("Station nicht gefunden."), code="not_found")
                update_station(
                    station,
                    {
                        "name": request.POST.get("name"),
                        "location": request.POST.get("location"),
                        "role": request.POST.get("role"),
                        "sort_order": request.POST.get("sort_order"),
                        "default_play_account_id": request.POST.get("default_play_account_id"),
                        "note": request.POST.get("note"),
                        "is_active": _bool_from_post(request.POST.get("is_active")),
                    },
                )
                messages.success(request, _("Station gespeichert."))
            elif action == "delete_station":
                station = MinecraftStation.objects.filter(pk=int(request.POST.get("station_id") or 0)).first()
                if station is None:
                    raise StationAdminError(_("Station nicht gefunden."), code="not_found")
                delete_station(station)
                messages.success(request, _("Station gelöscht."))
            elif action == "add_allowlist":
                add_allowlist_entry(
                    ms_username=request.POST.get("ms_username") or "",
                    station_id=request.POST.get("station_id") or None,
                    note=request.POST.get("note") or "",
                    user=request.user,
                )
                messages.success(request, _("Allowlist-Eintrag hinzugefügt."))
            elif action == "deactivate_allowlist":
                set_allowlist_active(int(request.POST.get("entry_id") or 0), is_active=False)
                messages.success(request, _("Allowlist-Eintrag deaktiviert."))
            elif action == "activate_allowlist":
                set_allowlist_active(int(request.POST.get("entry_id") or 0), is_active=True)
                messages.success(request, _("Allowlist-Eintrag aktiviert."))
            elif action == "delete_allowlist":
                delete_allowlist_entry(int(request.POST.get("entry_id") or 0))
                messages.success(request, _("Allowlist-Eintrag gelöscht."))
            else:
                messages.error(request, _("Ungültige Aktion."))
        except StationAdminError as exc:
            messages.error(request, str(exc))
        except (TypeError, ValueError):
            messages.error(request, _("Ungültige Eingabe."))
        return redirect(reverse("admin:minecraft_stations") + (f"?inactive=1" if include_inactive else ""))

    stations = list_station_dtos(include_inactive=include_inactive)
    edit_station = None
    if edit_id:
        try:
            edit_station = MinecraftStation.objects.select_related("default_play_account").get(pk=int(edit_id))
        except (MinecraftStation.DoesNotExist, ValueError, TypeError):
            edit_station = None

    context = {
        "title": _("Stationen (PCs)"),
        "stations": stations,
        "allowlist_entries": list_allowlist_entries(),
        "allowlist_enforced": allowlist_is_enforced(),
        "include_inactive": include_inactive,
        "edit_station": edit_station,
        "show_create": (request.GET.get("create") or "") == "1",
        "role_choices": MinecraftStation.ROLE_CHOICES,
        "play_accounts": MinecraftPlayAccount.objects.filter(is_active=True).order_by(
            "sort_order", "short_name"
        ),
        "player_sessions_url": reverse("admin:minecraft_player_sessions"),
        "builder_sessions_url": reverse("admin:minecraft_builder_sessions"),
    }
    return render(request, "admin/minecraft/minecraft_stations.html", context)
