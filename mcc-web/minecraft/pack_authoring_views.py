# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    pack_authoring_views.py
# @note    Admin UI: merge vehicle models into a selectable resource pack ZIP.

from __future__ import annotations

import re
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from minecraft.services.preset_permissions import user_can_manage_vehiclesplus_packs
from minecraft.services.vehiclesplus_catalog import (
    list_vehiclesplus_models,
    vehiclesplus_vehicles_dir,
)
from minecraft.services.vehiclesplus_pack_authoring import (
    DEFAULT_LEATHER_ITEM,
    LEATHER_ITEMS,
    PackAuthoringError,
    PackMergeResult,
    ServerPackApplyResult,
    VendorZipInspection,
    apply_resource_pack_to_server,
    build_vehicle_export_zip,
    default_source_pack_name,
    discard_staged_vendor_zip,
    import_model_from_vendor_zip,
    inspect_staged_vendor_zip,
    list_pack_zip_names,
    list_vehicle_model_stems_in_pack,
    merge_model_into_pack,
    next_custom_model_data,
    paper_server_properties_path,
    resource_pack_http_base,
    resource_packs_dir,
    scaffold_lastenrad_hjson,
    sha1_file,
    stage_vendor_zip,
    validate_pack_filename,
)


def _require_packs(view_func):
    @staff_member_required
    def wrapper(request, *args, **kwargs):
        if not user_can_manage_vehiclesplus_packs(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def _suggested_cmd(source_name: str) -> int | None:
    try:
        name = validate_pack_filename(source_name, field="Quell-Pack")
    except PackAuthoringError:
        return None
    path = resource_packs_dir() / name
    if not path.is_file():
        return None
    import tempfile
    from minecraft.services.vehiclesplus_pack_authoring import _extract_source_zip

    with tempfile.TemporaryDirectory(prefix="mcc-vp-cmd-") as tmp:
        work = Path(tmp) / "pack"
        work.mkdir()
        try:
            _extract_source_zip(path, work)
            return next_custom_model_data(work, item=DEFAULT_LEATHER_ITEM)
        except Exception:
            return None


def _default_form(packs: list[str]) -> dict:
    default_source = default_source_pack_name()
    if default_source not in packs and packs:
        default_source = packs[0]
    return {
        "source_pack": default_source,
        "output_pack": default_source or "VPExample-v3-1.21.7-1.21.8_MCC.zip",
        # Empty until ZIP analysis or manual Blockbench entry — no fake defaults.
        "model_stem": "",
        "custom_model_data": "",
        "leather_item": "",
        "write_hjson": "1",
        "overwrite_output": "1",
        "replace_existing": "",
        "update_server_properties": "1",
        "selected_model_path": "",
        "staging_token": "",
        "export_vehicle_id": "",
    }


def _read_form(request) -> dict:
    return {
        "source_pack": (request.POST.get("source_pack") or "").strip(),
        "output_pack": (request.POST.get("output_pack") or "").strip(),
        "model_stem": (request.POST.get("model_stem") or "").strip(),
        "custom_model_data": (request.POST.get("custom_model_data") or "").strip(),
        "leather_item": (request.POST.get("leather_item") or "").strip(),
        "write_hjson": "1" if request.POST.get("write_hjson") == "1" else "",
        "overwrite_output": "1" if request.POST.get("overwrite_output") == "1" else "",
        "replace_existing": "1" if request.POST.get("replace_existing") == "1" else "",
        "update_server_properties": (
            "1" if request.POST.get("update_server_properties") == "1" else ""
        ),
        "selected_model_path": (request.POST.get("selected_model_path") or "").strip(),
        "staging_token": (request.POST.get("staging_token") or "").strip(),
        "export_vehicle_id": (request.POST.get("export_vehicle_id") or "").strip(),
    }


def _apply_zip_candidate_defaults(form: dict, candidate) -> None:
    """Fill empty form fields from the selected ZIP model (no inventing names)."""
    form["model_stem"] = candidate.stem or ""
    form["custom_model_data"] = ""  # always next free in target pack
    if candidate.leather_item:
        form["leather_item"] = candidate.leather_item
    else:
        form["leather_item"] = ""


def _resolve_import_leather_item(form: dict) -> str:
    item = (form.get("leather_item") or "").strip()
    if item in LEATHER_ITEMS:
        return item
    if item.startswith("leather_") and item:
        # Unknown leather_* from vendor — map to boots for MCC VP packs
        return DEFAULT_LEATHER_ITEM
    return DEFAULT_LEATHER_ITEM


def _resolve_import_model_stem(form: dict, zip_inspection: VendorZipInspection | None) -> str:
    stem = (form.get("model_stem") or "").strip()
    if stem:
        return stem
    if zip_inspection:
        chosen = (form.get("selected_model_path") or "").strip()
        for model in zip_inspection.models:
            if model.path == chosen:
                return model.stem
        if zip_inspection.models:
            return zip_inspection.models[0].stem
    raise PackAuthoringError(str(_("Modell-ID fehlt — ZIP analysieren oder ID eingeben.")))



def _maybe_write_hjson(request, form: dict, merged: PackMergeResult) -> str:
    model_id = form["model_stem"] or "vehicle"
    # Prefer vendor VehiclesPlusPro HJSON (correct offsets / typeId); bike scaffold only as fallback.
    if merged.vendor_hjson:
        hjson_preview = merged.vendor_hjson
        subdir = (merged.vendor_hjson_subdir or "cars").strip() or "cars"
    else:
        hjson_preview = scaffold_lastenrad_hjson(
            model_id=model_id,
            custom_model_data=merged.custom_model_data,
        )
        subdir = "bikes"
    if form["write_hjson"]:
        from django.conf import settings as dj_settings

        vehicles_dir = Path(
            getattr(dj_settings, "MCC_MINECRAFT_VEHICLESPLUS_VEHICLES_DIR", "") or ""
        )
        if vehicles_dir:
            # Keep folder name safe
            safe_subdir = re.sub(r"[^A-Za-z0-9_-]", "", subdir) or "cars"
            out_hjson = vehicles_dir / safe_subdir / f"{model_id}.hjson"
            out_hjson.parent.mkdir(parents=True, exist_ok=True)
            out_hjson.write_text(hjson_preview, encoding="utf-8")
            # Remove mistaken bike scaffold if we now write cars/
            if safe_subdir != "bikes":
                legacy = vehicles_dir / "bikes" / f"{model_id}.hjson"
                if legacy.is_file():
                    try:
                        legacy.unlink()
                    except OSError:
                        pass
            messages.success(
                request,
                _("HJSON geschrieben: %(path)s") % {"path": str(out_hjson)},
            )
    return hjson_preview


def _maybe_apply_server_properties(
    request, form: dict, merged: PackMergeResult
) -> ServerPackApplyResult | None:
    if not form.get("update_server_properties"):
        return None
    applied = apply_resource_pack_to_server(
        pack_http_url=merged.http_url,
        sha1=merged.sha1,
        update_vehiclesplus=True,
    )
    messages.success(
        request,
        _(
            "server.properties aktualisiert (Backup %(bak)s). "
            "Paper neu starten, damit Clients das Pack laden."
        )
        % {"bak": applied.properties_backup.name},
    )
    if applied.vehiclesplus_backup is not None:
        messages.success(
            request,
            _("VehiclesPlus resourcePackUrl aktualisiert (Backup %(bak)s).")
            % {"bak": applied.vehiclesplus_backup.name},
        )
    return applied


def _success_message(request, merged: PackMergeResult) -> None:
    messages.success(
        request,
        _(
            "Pack erzeugt: %(name)s (SHA1 %(sha1)s, custom_model_data=%(cmd)s)."
        )
        % {
            "name": merged.output_path.name,
            "sha1": merged.sha1,
            "cmd": merged.custom_model_data,
        },
    )


@_require_packs
@require_http_methods(["GET", "POST"])
def minecraft_vehiclesplus_pack_authoring(request):
    packs = list_pack_zip_names()
    form = _default_form(packs)
    result = None
    hjson_preview = ""
    error = ""
    zip_inspection: VendorZipInspection | None = None
    server_apply: ServerPackApplyResult | None = None

    if request.method == "POST":
        form = _read_form(request)
        action = (request.POST.get("action") or "merge_json").strip()

        try:
            if action == "export_vehicle":
                vehicle_id = form.get("export_vehicle_id") or ""
                if not vehicle_id:
                    raise PackAuthoringError(
                        str(_("Bitte ein Fahrzeug für den Export wählen."))
                    )
                exported = build_vehicle_export_zip(
                    model_id=vehicle_id,
                    source_pack_name=form.get("source_pack") or "",
                )
                response = HttpResponse(
                    exported.payload,
                    content_type="application/zip",
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="{exported.filename}"'
                )
                response["Content-Length"] = str(len(exported.payload))
                return response

            if action == "analyze_zip":
                upload = request.FILES.get("vendor_zip")
                if upload is None:
                    raise PackAuthoringError(
                        str(_("Bitte ein Modell-/Resourcepack-ZIP hochladen."))
                    )
                token = stage_vendor_zip(
                    payload=upload.read(),
                    original_name=upload.name,
                )
                zip_inspection = inspect_staged_vendor_zip(token)
                form["staging_token"] = token
                if zip_inspection.models:
                    first = zip_inspection.models[0]
                    form["selected_model_path"] = first.path
                    _apply_zip_candidate_defaults(form, first)
                messages.info(
                    request,
                    _(
                        "ZIP analysiert: %(n)s Modell(e) gefunden — Felder aus dem Archiv "
                        "übernommen (CMD bleibt leer = nächste freie Nummer im Ziel-Pack)."
                    )
                    % {"n": len(zip_inspection.models)},
                )

            elif action == "cancel_zip":
                if form["staging_token"]:
                    discard_staged_vendor_zip(form["staging_token"])
                form["staging_token"] = ""
                form["selected_model_path"] = ""
                messages.info(request, _("ZIP-Import abgebrochen."))

            elif action == "import_zip":
                if not form["staging_token"]:
                    raise PackAuthoringError(
                        str(_("Kein Staging-Token — ZIP bitte erneut analysieren."))
                    )
                cmd_raw = form["custom_model_data"]
                cmd = int(cmd_raw) if cmd_raw else None
                # Refresh inspection for stem fallback / leather hints
                zip_inspection = inspect_staged_vendor_zip(form["staging_token"])
                # If user selected another radio, sync fields from that candidate when empty
                for model in zip_inspection.models:
                    if model.path == form["selected_model_path"]:
                        if not form["model_stem"]:
                            form["model_stem"] = model.stem
                        if not form["leather_item"] and model.leather_item:
                            form["leather_item"] = model.leather_item
                        break
                stem = _resolve_import_model_stem(form, zip_inspection)
                form["model_stem"] = stem
                merged = import_model_from_vendor_zip(
                    staging_token=form["staging_token"],
                    model_path=form["selected_model_path"],
                    source_pack_name=form["source_pack"],
                    output_pack_name=form["output_pack"],
                    model_stem=stem,
                    custom_model_data=cmd,
                    leather_item=_resolve_import_leather_item(form),
                    overwrite_output=bool(form["overwrite_output"]),
                    replace_existing=bool(form["replace_existing"]),
                )
                result = merged
                hjson_preview = _maybe_write_hjson(request, form, merged)
                server_apply = _maybe_apply_server_properties(request, form, merged)
                form["staging_token"] = ""
                form["selected_model_path"] = ""
                _success_message(request, merged)

            else:
                # merge_json (legacy Blockbench path)
                upload = request.FILES.get("model_json")
                texture_files: list[tuple[str, bytes]] = []
                for tex in request.FILES.getlist("textures"):
                    texture_files.append((tex.name, tex.read()))
                if upload is None:
                    raise PackAuthoringError(
                        str(_("Bitte eine Modell-JSON-Datei hochladen."))
                    )
                if not form["model_stem"]:
                    raise PackAuthoringError(
                        str(_("Modell-ID fehlt (für Blockbench-JSON erforderlich)."))
                    )
                cmd_raw = form["custom_model_data"]
                cmd = int(cmd_raw) if cmd_raw else None
                merged = merge_model_into_pack(
                    source_pack_name=form["source_pack"],
                    output_pack_name=form["output_pack"],
                    model_stem=form["model_stem"],
                    model_json_bytes=upload.read(),
                    custom_model_data=cmd,
                    leather_item=_resolve_import_leather_item(form),
                    texture_files=texture_files,
                    overwrite_output=bool(form["overwrite_output"]),
                    replace_existing=bool(form["replace_existing"]),
                )
                result = merged
                hjson_preview = _maybe_write_hjson(request, form, merged)
                server_apply = _maybe_apply_server_properties(request, form, merged)
                _success_message(request, merged)

        except PackAuthoringError as exc:
            error = str(exc)
            messages.error(request, error)
            if form.get("staging_token") and action in {"analyze_zip", "import_zip"}:
                try:
                    zip_inspection = inspect_staged_vendor_zip(form["staging_token"])
                except PackAuthoringError:
                    form["staging_token"] = ""
        except OSError as exc:
            error = str(exc)
            messages.error(request, error)

    if zip_inspection is None and form.get("staging_token"):
        try:
            zip_inspection = inspect_staged_vendor_zip(form["staging_token"])
        except PackAuthoringError:
            form["staging_token"] = ""

    packs = list_pack_zip_names()
    suggested_cmd = _suggested_cmd(form["source_pack"]) if form["source_pack"] else None
    existing_stems = (
        list_vehicle_model_stems_in_pack(form["source_pack"])
        if form["source_pack"]
        else []
    )
    export_vehicles = list_vehiclesplus_models()
    if not form.get("export_vehicle_id") and export_vehicles:
        form["export_vehicle_id"] = export_vehicles[0].model_id
    pack_rows = []
    for name in packs:
        path = resource_packs_dir() / name
        try:
            digest = sha1_file(path)
            size = path.stat().st_size
        except OSError:
            digest = ""
            size = 0
        pack_rows.append({"name": name, "sha1": digest, "size": size})

    context = {
        "title": _("VehiclesPlus Resourcepack"),
        "packs": packs,
        "pack_rows": pack_rows,
        "form": form,
        "leather_items": LEATHER_ITEMS,
        "packs_dir": str(resource_packs_dir()),
        "http_base": resource_pack_http_base(),
        "suggested_cmd": suggested_cmd,
        "existing_stems": existing_stems,
        "export_vehicles": export_vehicles,
        "vehicles_dir": str(vehiclesplus_vehicles_dir()),
        "result": result,
        "hjson_preview": hjson_preview,
        "zip_inspection": zip_inspection,
        "server_apply": server_apply,
        "server_properties_path": str(paper_server_properties_path()),
        "blockbench_url": "https://web.blockbench.net/",
        "blockbench_download_url": "https://www.blockbench.net/",
        "vp_generator_url": "https://vprpgenerator.sbdevelopment.tech/",
        "error": error,
    }
    return render(
        request,
        "admin/minecraft/minecraft_vehiclesplus_pack.html",
        context,
    )
