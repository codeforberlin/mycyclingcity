# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_views.py
# @note    TOP-operator UI for subregions inside assigned master regions.

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from minecraft.models import MinecraftProtectedRegion
from minecraft.services.preset_permissions import (
    user_can_manage_assigned_protected_regions,
)
from minecraft.services.region_admin import (
    annotate_move_flags,
    draft_from_post,
    empty_region_draft,
    move_region,
    operator_builder_choices,
    operator_can_access_region,
    operator_master_regions,
    region_to_draft,
    save_region_from_post,
)
from minecraft.services.region_ops import (
    apply_region_full,
    default_region_max_y,
    default_region_min_y,
    fetch_player_block_pos,
    paper_world,
    remove_region_from_server,
    sync_region_members,
)
from minecraft.services.regions_push import push_protected_regions_to_minecraft


def can_manage_assigned_regions(user):
    return user_can_manage_assigned_protected_regions(user)


@user_passes_test(can_manage_assigned_regions)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_my_build_zones(request):
    """Operator page: manage subregions inside TOP-assigned master regions."""
    masters = list(operator_master_regions(request.user))
    region_draft = None
    region_output = None
    redirect_name = "admin:minecraft_my_build_zones"

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "capture_pos":
                player = (request.POST.get("rg_player") or "").strip()
                corner = (request.POST.get("rg_corner") or "min").strip()
                x, y, z = fetch_player_block_pos(player)
                region_draft = draft_from_post(request.POST, keep_y_defaults=True)
                region_draft["player"] = player
                if corner == "spawn":
                    region_draft["spawn_x"] = x
                    region_draft["spawn_y"] = y
                    region_draft["spawn_z"] = z
                    messages.success(
                        request,
                        _(
                            "Spawn-Punkt von %(player)s: X=%(x)s / Y=%(y)s / Z=%(z)s"
                        )
                        % {"player": player, "x": x, "y": y, "z": z},
                    )
                else:
                    if corner == "max":
                        region_draft["max_x"], region_draft["max_z"] = x, z
                    else:
                        region_draft["min_x"], region_draft["min_z"] = x, z
                    messages.success(
                        request,
                        _(
                            "Position von %(player)s: X=%(x)s / Z=%(z)s → %(corner)s "
                            "(Y unverändert, Spieler-Y war %(y)s)"
                        )
                        % {
                            "player": player,
                            "x": x,
                            "y": y,
                            "z": z,
                            "corner": "Max" if corner == "max" else "Min",
                        },
                    )

            elif action == "load":
                pk = int(request.POST.get("rg_pk") or 0)
                region = MinecraftProtectedRegion.objects.select_related("parent").get(
                    pk=pk
                )
                if not operator_can_access_region(request.user, region):
                    raise ValueError(_("Keine Berechtigung für diese Region."))
                region_draft = region_to_draft(region)
                messages.info(
                    request,
                    _("Region „%(id)s“ geladen.") % {"id": region.region_id},
                )

            elif action in {"move_up", "move_down"}:
                pk = int(request.POST.get("rg_pk") or 0)
                region = MinecraftProtectedRegion.objects.select_related("parent").get(
                    pk=pk
                )
                if not operator_can_access_region(request.user, region):
                    raise ValueError(_("Keine Berechtigung für diese Region."))
                moved = move_region(region, -1 if action == "move_up" else 1)
                if moved:
                    messages.success(
                        request,
                        _("Reihenfolge von „%(id)s“ aktualisiert.")
                        % {"id": region.region_id},
                    )
                else:
                    messages.info(
                        request,
                        _("„%(id)s“ ist bereits am Ende der Liste.")
                        % {"id": region.region_id},
                    )
                return redirect(redirect_name)

            elif action == "new_under":
                parent_pk = int(request.POST.get("rg_parent") or 0)
                parent = next((m for m in masters if m.pk == parent_pk), None)
                if parent is None:
                    raise ValueError(_("Ungültige Master-Region."))
                region_draft = empty_region_draft(for_operator=True)
                region_draft["parent_id"] = str(parent.pk)
                region_draft["world"] = parent.world
                region_draft["min_x"] = parent.min_x
                region_draft["min_y"] = parent.min_y
                region_draft["min_z"] = parent.min_z
                region_draft["max_x"] = parent.max_x
                region_draft["max_y"] = parent.max_y
                region_draft["max_z"] = parent.max_z
                messages.info(
                    request,
                    _("Neue Subregion unter „%(id)s“ — Bounds bitte verkleinern.")
                    % {"id": parent.region_id},
                )

            elif action in {"save", "apply", "sync_members"}:
                region = save_region_from_post(
                    request.POST, user=request.user, operator_mode=True
                )
                region_draft = region_to_draft(region)
                masters = list(operator_master_regions(request.user))

                if action == "save":
                    messages.success(
                        request,
                        _("Subregion „%(id)s“ gespeichert (nur Datenbank).")
                        % {"id": region.region_id},
                    )
                    push_protected_regions_to_minecraft()
                    return redirect(redirect_name)

                if action == "sync_members":
                    ok, output = sync_region_members(region)
                    region_output = output
                    if ok:
                        messages.success(
                            request,
                            _("Members für „%(id)s“ synchronisiert.")
                            % {"id": region.region_id},
                        )
                        push_protected_regions_to_minecraft()
                    else:
                        messages.error(
                            request,
                            _("Member-Sync fehlgeschlagen: %(err)s") % {"err": output},
                        )
                else:
                    ok, output = apply_region_full(
                        region, admin_user=str(request.user)
                    )
                    region_output = output
                    if ok:
                        messages.success(
                            request,
                            _("Region „%(id)s“ auf dem Server angewendet.")
                            % {"id": region.region_id},
                        )
                        push_protected_regions_to_minecraft()
                    else:
                        messages.error(
                            request,
                            _("Anwenden fehlgeschlagen: %(err)s") % {"err": output},
                        )

            elif action == "delete":
                pk = int(request.POST.get("rg_pk") or 0)
                region = MinecraftProtectedRegion.objects.select_related("parent").get(
                    pk=pk
                )
                if not operator_can_access_region(request.user, region):
                    raise ValueError(_("Keine Berechtigung für diese Region."))
                region_id = region.region_id
                remove_server = request.POST.get("rg_remove_server") == "on"
                if remove_server:
                    ok, server_log = remove_region_from_server(region)
                    region_output = server_log
                    if not ok:
                        messages.error(
                            request,
                            _("Löschen auf dem Server fehlgeschlagen: %(err)s")
                            % {"err": server_log},
                        )
                        return redirect(redirect_name)
                region.delete()
                push_protected_regions_to_minecraft()
                messages.success(
                    request,
                    _("Region „%(id)s“ gelöscht%(suffix)s.")
                    % {
                        "id": region_id,
                        "suffix": _(" (auch WorldGuard)") if remove_server else "",
                    },
                )
                return redirect(redirect_name)

            else:
                messages.error(request, _("Unbekannte Aktion."))
                return redirect(redirect_name)
        except MinecraftProtectedRegion.DoesNotExist:
            messages.error(request, _("Region nicht gefunden."))
            return redirect(redirect_name)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(redirect_name)
        except Exception as exc:
            messages.error(request, _("Regionen-Fehler: %(err)s") % {"err": exc})
            return redirect(redirect_name)

    masters = list(operator_master_regions(request.user))
    for master in masters:
        annotate_move_flags(list(master.subregions.all()))

    context = {
        "title": _("Meine Bauzonen"),
        "master_regions": masters,
        "rg_builder_choices": list(operator_builder_choices(request.user)),
        "rg_draft": region_draft or empty_region_draft(for_operator=True),
        "rg_output": region_output,
        "rg_paper_world": paper_world(),
        "rg_world_min_y": default_region_min_y(),
        "rg_world_max_y": default_region_max_y(),
    }
    return render(request, "admin/minecraft/minecraft_my_build_zones.html", context)
