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

from config.logger_utils import get_logger
from minecraft.models import MinecraftRconPreset
from minecraft.services.preset_commands import (
    commands_to_text,
    parse_commands_text,
    validate_commands,
)
from minecraft.services.preset_permissions import (
    user_can_access_minecraft_control,
    user_can_delete_preset,
    user_can_edit_preset,
    user_can_export_presets,
    user_can_manage_presets,
    user_can_run_preset,
)
from minecraft.services.rcon_presets import (
    duplicate_preset,
    export_presets_json,
    filter_presets_for_list,
    run_preset,
    unique_slug_from_name,
)


logger = get_logger("minecraft")


def _minecraft_access_required(view_func):
    @staff_member_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_minecraft_control(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def _preset_form_context(
    request,
    preset: MinecraftRconPreset | None,
    *,
    commands_text: str = "",
    command_warnings: list[str] | None = None,
) -> dict:
    can_edit_system_fields = request.user.is_superuser or request.user.has_perm(
        "minecraft.change_system_rconpreset"
    )
    return {
        "title": _("RCON-Preset bearbeiten") if preset else _("RCON-Preset anlegen"),
        "preset": preset,
        "category_choices": MinecraftRconPreset.CATEGORY_CHOICES,
        "commands_text": commands_text or (commands_to_text(preset.commands) if preset else ""),
        "command_warnings": command_warnings or [],
        "can_edit_system_fields": can_edit_system_fields,
        "can_edit_slug": preset is None or (not preset.is_system or can_edit_system_fields),
        "can_delete": preset is not None and user_can_delete_preset(request.user, preset),
        "can_run": preset is not None and user_can_run_preset(request.user, preset),
        "next_url": request.GET.get("next") or reverse("admin:minecraft_preset_list"),
    }


def _apply_post_to_preset(
    request,
    preset: MinecraftRconPreset | None,
) -> tuple[MinecraftRconPreset | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if preset is None:
        if not user_can_edit_preset(request.user, None):
            raise PermissionDenied
        preset = MinecraftRconPreset()
    elif not user_can_edit_preset(request.user, preset):
        raise PermissionDenied

    name = (request.POST.get("name") or "").strip()
    if not name:
        errors.append(str(_("Name ist erforderlich.")))
    preset.name = name[:64]

    slug = (request.POST.get("slug") or "").strip()
    if not slug:
        slug = unique_slug_from_name(preset.name, exclude_pk=preset.pk)
    if preset.is_system and not (
        request.user.is_superuser
        or request.user.has_perm("minecraft.change_system_rconpreset")
    ):
        pass
    else:
        preset.slug = slug[:64]

    preset.category = request.POST.get("category") or MinecraftRconPreset.CATEGORY_WORLD
    if preset.category not in dict(MinecraftRconPreset.CATEGORY_CHOICES):
        preset.category = MinecraftRconPreset.CATEGORY_WORLD

    try:
        preset.sort_order = max(0, int(request.POST.get("sort_order") or 0))
    except (TypeError, ValueError):
        preset.sort_order = 0

    preset.enabled = request.POST.get("enabled") == "on"
    preset.description = (request.POST.get("description") or "").strip()
    preset.moderator_can_run = request.POST.get("moderator_can_run") == "on"
    preset.requires_confirmation = request.POST.get("requires_confirmation") == "on"
    preset.stop_on_error = request.POST.get("stop_on_error") == "on"

    if request.user.is_superuser or request.user.has_perm(
        "minecraft.change_system_rconpreset"
    ):
        if preset.pk is None:
            preset.is_system = request.POST.get("is_system") == "on"
        elif not preset.is_system:
            preset.is_system = request.POST.get("is_system") == "on"

    commands_text = request.POST.get("commands") or ""
    commands = parse_commands_text(commands_text)
    command_errors, command_warnings = validate_commands(commands)
    errors.extend(command_errors)
    warnings.extend(command_warnings)

    if errors:
        return None, errors, warnings

    preset.commands = commands
    preset.save()
    return preset, errors, warnings


@_minecraft_access_required
@require_http_methods(["GET"])
def minecraft_preset_list(request):
    if not user_can_manage_presets(request.user) and not request.user.has_perm(
        "minecraft.run_rconpreset"
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

    context = {
        "title": _("RCON-Presets"),
        "presets": presets,
        "category_choices": MinecraftRconPreset.CATEGORY_CHOICES,
        "filter_category": category,
        "filter_enabled": enabled,
        "filter_query": query,
        "can_add": user_can_edit_preset(request.user, None),
        "can_export": user_can_export_presets(request.user),
    }
    return render(request, "admin/minecraft/minecraft_rcon_preset_list.html", context)


@_minecraft_access_required
@require_http_methods(["GET", "POST"])
def minecraft_preset_add(request):
    if not user_can_edit_preset(request.user, None):
        raise PermissionDenied

    if request.method == "GET":
        context = _preset_form_context(request, None)
        return render(request, "admin/minecraft/minecraft_rcon_preset_form.html", context)

    preset, errors, warnings = _apply_post_to_preset(request, None)
    commands_text = request.POST.get("commands") or ""
    if errors:
        for error in errors:
            messages.error(request, error)
        context = _preset_form_context(
            request,
            None,
            commands_text=commands_text,
            command_warnings=warnings,
        )
        context["form_data"] = request.POST
        return render(request, "admin/minecraft/minecraft_rcon_preset_form.html", context)

    for warning in warnings:
        messages.warning(request, warning)

    action = request.POST.get("action") or "save"
    if action == "save_and_run" and preset and user_can_run_preset(request.user, preset):
        success, message = run_preset(preset.id, user=request.user)
        if success:
            messages.success(request, _("Preset gespeichert und ausgeführt."))
        else:
            messages.error(request, message)
    else:
        messages.success(request, _("Preset gespeichert."))

    next_url = request.POST.get("next") or reverse("admin:minecraft_preset_list")
    return redirect(next_url)


@_minecraft_access_required
@require_http_methods(["GET", "POST"])
def minecraft_preset_edit(request, preset_id: int):
    preset = get_object_or_404(MinecraftRconPreset, pk=preset_id)

    if request.method == "GET":
        if not user_can_edit_preset(request.user, preset) and not user_can_run_preset(
            request.user, preset
        ):
            raise PermissionDenied
        context = _preset_form_context(request, preset)
        return render(request, "admin/minecraft/minecraft_rcon_preset_form.html", context)

    if not user_can_edit_preset(request.user, preset):
        raise PermissionDenied

    preset, errors, warnings = _apply_post_to_preset(request, preset)
    commands_text = request.POST.get("commands") or ""
    if errors:
        for error in errors:
            messages.error(request, error)
        context = _preset_form_context(
            request,
            get_object_or_404(MinecraftRconPreset, pk=preset_id),
            commands_text=commands_text,
            command_warnings=warnings,
        )
        context["form_data"] = request.POST
        return render(request, "admin/minecraft/minecraft_rcon_preset_form.html", context)

    for warning in warnings:
        messages.warning(request, warning)

    action = request.POST.get("action") or "save"
    if action == "save_and_run" and preset and user_can_run_preset(request.user, preset):
        success, message = run_preset(preset.id, user=request.user)
        if success:
            messages.success(request, _("Preset gespeichert und ausgeführt."))
        else:
            messages.error(request, message)
    elif action == "test_first" and preset and user_can_run_preset(request.user, preset):
        success, message = run_preset(preset.id, user=request.user, test_first_only=True)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        next_url = request.POST.get("next") or reverse(
            "admin:minecraft_preset_edit", args=[preset.id]
        )
        return redirect(next_url)
    else:
        messages.success(request, _("Preset gespeichert."))

    next_url = request.POST.get("next") or reverse("admin:minecraft_preset_list")
    return redirect(next_url)


@_minecraft_access_required
@require_POST
def minecraft_preset_duplicate(request, preset_id: int):
    if not user_can_edit_preset(request.user, None):
        raise PermissionDenied

    source = get_object_or_404(MinecraftRconPreset, pk=preset_id)
    copy = duplicate_preset(source)
    messages.success(
        request,
        _("Preset „%(name)s“ dupliziert.") % {"name": source.name},
    )
    return redirect(reverse("admin:minecraft_preset_edit", args=[copy.id]))


@_minecraft_access_required
@require_POST
def minecraft_preset_delete(request, preset_id: int):
    preset = get_object_or_404(MinecraftRconPreset, pk=preset_id)
    if not user_can_delete_preset(request.user, preset):
        raise PermissionDenied

    name = preset.name
    preset.delete()
    messages.success(request, _("Preset „%(name)s“ gelöscht.") % {"name": name})
    return redirect(reverse("admin:minecraft_preset_list"))


@_minecraft_access_required
@require_http_methods(["GET"])
def minecraft_preset_export(request):
    if not user_can_export_presets(request.user):
        raise PermissionDenied

    presets = MinecraftRconPreset.objects.all().order_by("category", "sort_order", "name")
    payload = export_presets_json(presets)
    response = HttpResponse(payload, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="minecraft-rcon-presets.json"'
    return response


@_minecraft_access_required
@require_POST
def minecraft_preset_import(request):
    if not user_can_edit_preset(request.user, None):
        raise PermissionDenied

    upload = request.FILES.get("import_file")
    if not upload:
        messages.error(request, _("Bitte eine JSON-Datei wählen."))
        return redirect(reverse("admin:minecraft_preset_list"))

    try:
        data = json.loads(upload.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        messages.error(request, _("Ungültige JSON-Datei: %(error)s") % {"error": exc})
        return redirect(reverse("admin:minecraft_preset_list"))

    if not isinstance(data, list):
        messages.error(request, _("JSON muss eine Liste von Presets sein."))
        return redirect(reverse("admin:minecraft_preset_list"))

    created = 0
    updated = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        slug = (item.get("slug") or "").strip()
        if not slug:
            continue
        defaults = {
            "name": (item.get("name") or slug)[:64],
            "category": item.get("category") or MinecraftRconPreset.CATEGORY_OTHER,
            "description": item.get("description") or "",
            "commands": item.get("commands") or [],
            "sort_order": int(item.get("sort_order") or 0),
            "enabled": bool(item.get("enabled", True)),
            "moderator_can_run": bool(item.get("moderator_can_run", False)),
            "requires_confirmation": bool(item.get("requires_confirmation", True)),
            "stop_on_error": bool(item.get("stop_on_error", True)),
            "is_system": False,
        }
        _obj, was_created = MinecraftRconPreset.objects.update_or_create(
            slug=slug,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    messages.success(
        request,
        _("Import abgeschlossen: %(created)s neu, %(updated)s aktualisiert.")
        % {"created": created, "updated": updated},
    )
    return redirect(reverse("admin:minecraft_preset_list"))


@_minecraft_access_required
@require_POST
def minecraft_run_preset(request, preset_id: int):
    try:
        preset = MinecraftRconPreset.objects.get(pk=preset_id)
    except MinecraftRconPreset.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": _("Preset nicht gefunden.")},
            status=404,
        )

    if not user_can_run_preset(request.user, preset):
        return JsonResponse(
            {"success": False, "error": _("Keine Berechtigung.")},
            status=403,
        )

    try:
        success, message = run_preset(preset_id, user=request.user)
        if success:
            return JsonResponse({"success": True, "message": message, "output": message})
        return JsonResponse({"success": False, "error": message, "output": message}, status=500)
    except Exception as exc:
        logger.error("[minecraft_preset] run failed: %s", exc, exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
