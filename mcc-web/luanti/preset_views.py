# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from luanti.models import LuantiCityPreset
from luanti.services.city_preset_permissions import (
    user_can_delete_city_preset,
    user_can_edit_city_preset,
    user_can_manage_city_presets,
    user_can_run_city_preset,
)
from luanti.services.city_presets import (
    duplicate_preset,
    filter_presets_for_list,
    preset_to_export_dict,
    run_city_preset,
    sanitize_import_slug,
    unique_slug_from_name,
    upsert_seed_presets,
)
from luanti.services.permissions import user_can_access_luanti_city, user_can_access_luanti_control
from luanti.services.preset_steps import parse_steps_text, steps_to_text, validate_steps


def _luanti_city_access(view_func):
    @staff_member_required
    def wrapper(request, *args, **kwargs):
        if not (
            user_can_access_luanti_control(request.user)
            or user_can_access_luanti_city(request.user)
            or user_can_manage_city_presets(request.user)
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def _form_context(request, preset: LuantiCityPreset | None, *, steps_text: str = "", warnings=None):
    can_system = request.user.is_superuser or request.user.has_perm(
        "luanti.change_system_citypreset"
    )
    if steps_text:
        text = steps_text
    elif preset is not None:
        text = steps_to_text(preset.steps)
    else:
        text = ""
    return {
        "title": _("Stadt-Preset bearbeiten") if preset else _("Stadt-Preset anlegen"),
        "preset": preset,
        "category_choices": LuantiCityPreset.CATEGORY_CHOICES,
        "steps_text": text,
        "command_warnings": warnings or [],
        "can_edit_system_fields": can_system,
        "can_edit_slug": preset is None or (not preset.is_system or can_system),
        "can_delete": preset is not None and user_can_delete_city_preset(request.user, preset),
        "can_run": preset is not None and user_can_run_city_preset(request.user, preset),
        "next_url": request.GET.get("next")
        or request.POST.get("next")
        or reverse("admin:luanti_preset_list"),
        "form_data": request.POST if request.method == "POST" else None,
    }


def _apply_post(request, preset: LuantiCityPreset | None):
    errors: list[str] = []
    warnings: list[str] = []

    if preset is None:
        if not user_can_edit_city_preset(request.user, None):
            raise PermissionDenied
        preset = LuantiCityPreset()
    elif not user_can_edit_city_preset(request.user, preset):
        raise PermissionDenied

    name = (request.POST.get("name") or "").strip()
    if not name:
        errors.append(str(_("Name ist erforderlich.")))
    preset.name = name[:64]

    slug = (request.POST.get("slug") or "").strip()
    if not slug:
        slug = unique_slug_from_name(preset.name or "preset", exclude_pk=preset.pk)
    can_system = request.user.is_superuser or request.user.has_perm(
        "luanti.change_system_citypreset"
    )
    if not (preset.pk and preset.is_system and not can_system):
        preset.slug = slug[:64]

    preset.category = request.POST.get("category") or LuantiCityPreset.CATEGORY_WORLD
    if preset.category not in dict(LuantiCityPreset.CATEGORY_CHOICES):
        preset.category = LuantiCityPreset.CATEGORY_WORLD

    try:
        preset.sort_order = max(0, int(request.POST.get("sort_order") or 0))
    except (TypeError, ValueError):
        preset.sort_order = 0

    preset.enabled = request.POST.get("enabled") == "on"
    preset.description = (request.POST.get("description") or "").strip()
    preset.moderator_can_run = request.POST.get("moderator_can_run") == "on"
    preset.requires_confirmation = request.POST.get("requires_confirmation") == "on"

    if can_system:
        if preset.pk is None or not preset.is_system:
            preset.is_system = request.POST.get("is_system") == "on"

    steps_text = request.POST.get("steps") or ""
    try:
        steps = parse_steps_text(steps_text)
    except ValueError as exc:
        errors.append(str(exc))
        steps = []
    step_errors, step_warnings = validate_steps(steps) if steps or not errors else ([], [])
    errors.extend(step_errors)
    warnings.extend(step_warnings)

    if errors:
        return None, errors, warnings, steps_text

    preset.steps = steps
    preset.save()
    return preset, errors, warnings, steps_text


@_luanti_city_access
@require_http_methods(["GET"])
def luanti_preset_list(request):
    if not user_can_manage_city_presets(request.user) and not user_can_run_city_preset(
        request.user
    ):
        raise PermissionDenied

    category = request.GET.get("category") or ""
    enabled = request.GET.get("enabled") or ""
    query = (request.GET.get("q") or "").strip()
    presets = filter_presets_for_list(
        category=category or None,
        enabled=enabled or None,
        query=query or None,
    )
    return render(
        request,
        "admin/luanti/luanti_city_preset_list.html",
        {
            "title": _("Luanti Stadt-Presets"),
            "presets": presets,
            "category_choices": LuantiCityPreset.CATEGORY_CHOICES,
            "filter_category": category,
            "filter_enabled": enabled,
            "filter_query": query,
            "can_add": user_can_edit_city_preset(request.user, None),
            "can_export": user_can_manage_city_presets(request.user),
        },
    )


@_luanti_city_access
@require_http_methods(["GET", "POST"])
def luanti_preset_add(request):
    if not user_can_edit_city_preset(request.user, None):
        raise PermissionDenied
    if request.method == "GET":
        return render(
            request,
            "admin/luanti/luanti_city_preset_form.html",
            _form_context(request, None, steps_text="set_weather clear\nset_time 6000\nchat "),
        )

    preset, errors, warnings, steps_text = _apply_post(request, None)
    if errors:
        for e in errors:
            messages.error(request, e)
        ctx = _form_context(request, None, steps_text=steps_text, warnings=warnings)
        return render(request, "admin/luanti/luanti_city_preset_form.html", ctx)

    action = request.POST.get("action") or "save"
    messages.success(request, _("Preset gespeichert."))
    if action == "save_and_run" and user_can_run_city_preset(request.user, preset):
        ok, msg = run_city_preset(preset, user=request.user)
        if ok:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
    next_url = request.POST.get("next") or reverse("admin:luanti_preset_list")
    return redirect(next_url)


@_luanti_city_access
@require_http_methods(["GET", "POST"])
def luanti_preset_edit(request, preset_id: int):
    preset = get_object_or_404(LuantiCityPreset, pk=preset_id)
    if not user_can_edit_city_preset(request.user, preset) and request.method == "GET":
        # Allow view-only via manage? Require edit for form.
        if not user_can_manage_city_presets(request.user):
            raise PermissionDenied
    if request.method == "GET":
        return render(
            request,
            "admin/luanti/luanti_city_preset_form.html",
            _form_context(request, preset),
        )
    if not user_can_edit_city_preset(request.user, preset):
        raise PermissionDenied

    preset, errors, warnings, steps_text = _apply_post(request, preset)
    if errors:
        for e in errors:
            messages.error(request, e)
        ctx = _form_context(
            request,
            get_object_or_404(LuantiCityPreset, pk=preset_id),
            steps_text=steps_text,
            warnings=warnings,
        )
        return render(request, "admin/luanti/luanti_city_preset_form.html", ctx)

    action = request.POST.get("action") or "save"
    messages.success(request, _("Preset gespeichert."))
    if action == "save_and_run" and user_can_run_city_preset(request.user, preset):
        ok, msg = run_city_preset(preset, user=request.user)
        if ok:
            messages.success(request, msg)
        else:
            messages.warning(request, msg)
    next_url = request.POST.get("next") or reverse("admin:luanti_preset_list")
    return redirect(next_url)


@_luanti_city_access
@require_POST
def luanti_preset_delete(request, preset_id: int):
    preset = get_object_or_404(LuantiCityPreset, pk=preset_id)
    if not user_can_delete_city_preset(request.user, preset):
        raise PermissionDenied
    name = preset.name
    preset.delete()
    messages.success(request, _("Preset „%(name)s“ gelöscht.") % {"name": name})
    return redirect(request.POST.get("next") or reverse("admin:luanti_preset_list"))


@_luanti_city_access
@require_POST
def luanti_preset_duplicate(request, preset_id: int):
    if not user_can_edit_city_preset(request.user, None):
        raise PermissionDenied
    src = get_object_or_404(LuantiCityPreset, pk=preset_id)
    copy = duplicate_preset(src)
    messages.success(request, _("Kopie angelegt: %(name)s") % {"name": copy.name})
    return redirect("admin:luanti_preset_edit", preset_id=copy.pk)


@_luanti_city_access
@require_http_methods(["GET"])
def luanti_preset_export(request):
    if not user_can_manage_city_presets(request.user):
        raise PermissionDenied
    data = [preset_to_export_dict(p) for p in LuantiCityPreset.objects.order_by("sort_order", "slug")]
    body = json.dumps({"presets": data}, ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="luanti-city-presets.json"'
    return response


@_luanti_city_access
@require_POST
def luanti_preset_import(request):
    if not user_can_edit_city_preset(request.user, None):
        raise PermissionDenied
    upload = request.FILES.get("import_file")
    if not upload:
        messages.error(request, _("Keine Datei gewählt."))
        return redirect("admin:luanti_preset_list")
    try:
        raw = json.loads(upload.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        messages.error(request, _("JSON ungültig: %(err)s") % {"err": exc})
        return redirect("admin:luanti_preset_list")
    rows = raw.get("presets") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        messages.error(request, _("Erwarte Liste oder {\"presets\": [...]}."))
        return redirect("admin:luanti_preset_list")
    created = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = sanitize_import_slug(str(row.get("slug") or row.get("name") or ""))
        if not slug:
            continue
        if LuantiCityPreset.objects.filter(slug=slug).exists():
            slug = unique_slug_from_name(slug)
        steps = row.get("steps") if isinstance(row.get("steps"), list) else []
        LuantiCityPreset.objects.create(
            slug=slug,
            name=str(row.get("name") or slug)[:64],
            category=row.get("category")
            if row.get("category") in dict(LuantiCityPreset.CATEGORY_CHOICES)
            else LuantiCityPreset.CATEGORY_WORLD,
            description=str(row.get("description") or "")[:5000],
            steps=steps,
            sort_order=int(row.get("sort_order") or 0),
            enabled=bool(row.get("enabled", True)),
            is_system=False,
            moderator_can_run=bool(row.get("moderator_can_run", False)),
            requires_confirmation=bool(row.get("requires_confirmation", True)),
        )
        created += 1
    messages.success(request, _("%(n)s Preset(s) importiert.") % {"n": created})
    return redirect("admin:luanti_preset_list")


@_luanti_city_access
@require_POST
def luanti_run_preset(request, preset_id: int):
    preset = get_object_or_404(LuantiCityPreset, pk=preset_id, enabled=True)
    if not user_can_run_city_preset(request.user, preset):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    ok, msg = run_city_preset(preset, user=request.user)
    return JsonResponse({"ok": ok, "output": msg, "message": msg}, status=200 if ok else 502)


@_luanti_city_access
@require_POST
def luanti_preset_ensure_seeds(request):
    """Admin helper: create missing seed presets without overwriting GUI edits."""
    if not user_can_manage_city_presets(request.user):
        raise PermissionDenied
    created = upsert_seed_presets()
    if created:
        messages.success(request, _("Seeds angelegt: %(s)s") % {"s": ", ".join(created)})
    else:
        messages.info(request, _("Alle Seed-Presets waren schon vorhanden."))
    return redirect("admin:luanti_preset_list")
