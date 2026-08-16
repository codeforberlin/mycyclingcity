# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    grant_views.py
# @note    Admin CRUD for MinecraftGrantCatalogItem.

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from minecraft.models import MinecraftGrantCatalogItem
from minecraft.services.grant_catalog import ensure_default_catalog_items
from minecraft.services.preset_permissions import user_can_manage_grant_catalog
from minecraft.services.vehiclesplus_catalog import (
    vehiclesplus_models_by_category,
    vehiclesplus_vehicles_dir,
)


def _require_catalog(view_func):
    @staff_member_required
    def wrapper(request, *args, **kwargs):
        if not user_can_manage_grant_catalog(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def _unique_slug(base: str, *, exclude_pk: int | None = None) -> str:
    root = slugify(base)[:50] or "item"
    slug = root
    n = 2
    while True:
        qs = MinecraftGrantCatalogItem.objects.filter(slug=slug)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        if not qs.exists():
            return slug
        slug = f"{root}-{n}"
        n += 1


def _apply_form(request, item: MinecraftGrantCatalogItem) -> list[str]:
    errors: list[str] = []
    name = (request.POST.get("name") or "").strip()
    if not name:
        errors.append(str(_("Name ist erforderlich.")))
    item.name = name[:128]

    slug_raw = (request.POST.get("slug") or "").strip()
    if slug_raw:
        item.slug = slugify(slug_raw)[:64] or item.slug
    elif not item.pk:
        item.slug = _unique_slug(name)

    kind = (request.POST.get("kind") or "").strip()
    if kind not in dict(MinecraftGrantCatalogItem.KIND_CHOICES):
        errors.append(str(_("Ungültige Art.")))
    else:
        item.kind = kind

    item.enabled = request.POST.get("enabled") == "1"
    item.applies_to_player = request.POST.get("applies_to_player") == "1"
    item.applies_to_builder = request.POST.get("applies_to_builder") == "1"
    try:
        item.sort_order = max(0, int(request.POST.get("sort_order") or 100))
    except ValueError:
        errors.append(str(_("Sortierung ungültig.")))
    item.model_id = (request.POST.get("model_id") or "").strip()[:64]
    try:
        item.quantity_default = max(1, int(request.POST.get("quantity_default") or 1))
    except ValueError:
        errors.append(str(_("Menge ungültig.")))
    try:
        item.velos_cost = max(0, int(request.POST.get("velos_cost") or 0))
        item.repair_velos_cost = max(0, int(request.POST.get("repair_velos_cost") or 0))
    except ValueError:
        errors.append(str(_("Velos-Betrag ungültig.")))

    item.rcon_grant_template = (request.POST.get("rcon_grant_template") or "").strip()[:512]
    if not item.rcon_grant_template:
        errors.append(str(_("RCON-Vergabe ist erforderlich.")))
    item.rcon_revoke_template = (request.POST.get("rcon_revoke_template") or "").strip()[:512]
    item.rcon_repair_template = (request.POST.get("rcon_repair_template") or "").strip()[:512]
    item.notes = (request.POST.get("notes") or "").strip()[:255]

    if not errors:
        try:
            item.full_clean()
        except ValidationError as exc:
            for msgs in exc.message_dict.values():
                errors.extend(str(m) for m in msgs)
    return errors


@_require_catalog
@require_http_methods(["GET", "POST"])
def minecraft_grant_catalog_list(request):
    ensure_default_catalog_items()
    items = MinecraftGrantCatalogItem.objects.all().order_by("sort_order", "name")
    return render(
        request,
        "admin/minecraft/minecraft_grant_catalog_list.html",
        {
            "title": _("Vergabe-Katalog"),
            "items": items,
            "kind_choices": MinecraftGrantCatalogItem.KIND_CHOICES,
        },
    )


def _vp_form_context() -> dict:
    groups = vehiclesplus_models_by_category()
    vp_dir = vehiclesplus_vehicles_dir()
    return {
        "vp_model_groups": [
            (category, [m.as_dict() for m in models]) for category, models in groups
        ],
        "vp_vehicles_dir": str(vp_dir),
        "vp_models_available": bool(groups),
    }


@_require_catalog
@require_http_methods(["GET", "POST"])
def minecraft_grant_catalog_edit(request, item_id: int | None = None):
    ensure_default_catalog_items()
    item = (
        get_object_or_404(MinecraftGrantCatalogItem, pk=item_id)
        if item_id
        else     MinecraftGrantCatalogItem(
            rcon_grant_template="v give {player} {model}",
            rcon_repair_template="v repair {player}",
            rcon_revoke_template="mccbridge vpremove {player} {model}",
            kind=MinecraftGrantCatalogItem.KIND_VEHICLE_GARAGE,
        )
    )
    errors: list[str] = []
    if request.method == "POST":
        errors = _apply_form(request, item)
        if not errors:
            if not item.slug:
                item.slug = _unique_slug(item.name, exclude_pk=item.pk)
            item.save()
            messages.success(request, _("Katalogeintrag gespeichert."))
            return redirect("admin:minecraft_grant_catalog_list")
    return render(
        request,
        "admin/minecraft/minecraft_grant_catalog_form.html",
        {
            "title": _("Katalogeintrag bearbeiten") if item.pk else _("Katalogeintrag anlegen"),
            "item": item,
            "errors": errors,
            "kind_choices": MinecraftGrantCatalogItem.KIND_CHOICES,
            **_vp_form_context(),
        },
    )


@_require_catalog
@require_POST
def minecraft_grant_catalog_delete(request, item_id: int):
    item = get_object_or_404(MinecraftGrantCatalogItem, pk=item_id)
    name = item.name
    item.delete()
    messages.success(request, _("Gelöscht: %(name)s") % {"name": name})
    return redirect("admin:minecraft_grant_catalog_list")
