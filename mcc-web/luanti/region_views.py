# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_views.py
# @note    Admin UI for Luanti protected regions (capture pos, hierarchy).

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from luanti.models import LuantiIntegrationConfig, LuantiProtectedRegion
from luanti.services.permissions import user_can_manage_luanti_regions
from luanti.services.player_pos import fetch_player_block_pos
from luanti.services.region_admin import (
    account_choices,
    annotate_move_flags,
    draft_from_post,
    empty_region_draft,
    hierarchical_region_list,
    master_regions_queryset,
    move_region,
    online_player_names,
    region_to_draft,
    save_region_from_post,
    top_groups_queryset,
    validation_error_message,
)
from luanti.services.regions_push import push_protected_regions_to_luanti


@user_passes_test(user_can_manage_luanti_regions)
@staff_member_required
def luanti_regions_admin(request):
    region_draft = None
    redirect_name = "admin:luanti_regions"
    cfg = LuantiIntegrationConfig.get_config()

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "outline_settings":
                cfg.region_outline_enabled = request.POST.get("region_outline_enabled") == "on"
                cfg.region_outline_enter_hint = (
                    request.POST.get("region_outline_enter_hint") == "on"
                )
                try:
                    vd = int(request.POST.get("region_outline_view_distance") or 48)
                except ValueError:
                    vd = 48
                cfg.region_outline_view_distance = max(8, vd)
                if getattr(request.user, "is_authenticated", False):
                    cfg.updated_by = request.user
                cfg.save(
                    update_fields=[
                        "region_outline_enabled",
                        "region_outline_enter_hint",
                        "region_outline_view_distance",
                        "updated_at",
                        "updated_by",
                    ]
                )
                ok, detail = push_protected_regions_to_luanti()
                if ok:
                    messages.success(
                        request,
                        _("Markierung gespeichert und an Bridge gesendet (%(d)s).")
                        % {"d": detail},
                    )
                else:
                    messages.warning(
                        request,
                        _("Markierung gespeichert (Bridge offline: %(d)s).")
                        % {"d": detail},
                    )
                return redirect(redirect_name)

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
                region = LuantiProtectedRegion.objects.select_related("parent").get(pk=pk)
                region_draft = region_to_draft(region)
                messages.info(
                    request,
                    _("Region „%(id)s“ geladen.") % {"id": region.region_id},
                )

            elif action in {"move_up", "move_down"}:
                pk = int(request.POST.get("rg_pk") or 0)
                region = LuantiProtectedRegion.objects.select_related("parent").get(pk=pk)
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

            elif action == "new":
                region_draft = empty_region_draft()
                messages.info(request, _("Neue Master-Region — Bounds setzen."))

            elif action == "new_under":
                parent_pk = int(request.POST.get("rg_parent") or 0)
                parent = master_regions_queryset().filter(pk=parent_pk).first()
                if parent is None:
                    raise ValueError(_("Ungültige Master-Region."))
                region_draft = empty_region_draft()
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

            elif action == "save":
                region = save_region_from_post(request.POST, user=request.user)
                region_draft = region_to_draft(region)
                ok, detail = push_protected_regions_to_luanti()
                if ok:
                    messages.success(
                        request,
                        _("Region „%(id)s“ gespeichert und an Bridge gesendet.")
                        % {"id": region.region_id},
                    )
                else:
                    messages.warning(
                        request,
                        _(
                            "Region „%(id)s“ gespeichert (Bridge offline: %(detail)s)."
                        )
                        % {"id": region.region_id, "detail": detail},
                    )
                return redirect(redirect_name)

            elif action == "push":
                ok, detail = push_protected_regions_to_luanti()
                if ok:
                    messages.success(request, _("Regionen an Bridge gesendet (%(d)s).") % {"d": detail})
                else:
                    messages.error(request, _("Push fehlgeschlagen: %(d)s") % {"d": detail})
                return redirect(redirect_name)

            elif action == "delete":
                pk = int(request.POST.get("rg_pk") or 0)
                region = LuantiProtectedRegion.objects.filter(pk=pk).first()
                if region is None:
                    raise ValueError(_("Region nicht gefunden."))
                rid = region.region_id
                region.delete()
                push_protected_regions_to_luanti()
                messages.success(request, _("Region „%(id)s“ gelöscht.") % {"id": rid})
                return redirect(redirect_name)

            elif action == "cancel":
                return redirect(redirect_name)

        except ValidationError as exc:
            messages.error(request, validation_error_message(exc))
            region_draft = draft_from_post(request.POST, keep_y_defaults=True)
        except (ValueError, TypeError) as exc:
            messages.error(request, str(exc))
            region_draft = draft_from_post(request.POST, keep_y_defaults=True)

    if region_draft is None:
        region_draft = empty_region_draft()

    regions = annotate_move_flags(hierarchical_region_list())
    return render(
        request,
        "admin/luanti/luanti_regions.html",
        {
            "title": _("Geschützte Regionen"),
            "protected_regions": regions,
            "rg_draft": region_draft,
            "rg_masters": master_regions_queryset(),
            "rg_top_groups": top_groups_queryset(),
            "rg_member_choices": account_choices(),
            "rg_online_players": online_player_names(),
            "integration_config": cfg,
        },
    )
