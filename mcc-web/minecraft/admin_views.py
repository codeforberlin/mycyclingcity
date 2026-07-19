import os
import subprocess
from pathlib import Path

from django.contrib import messages
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from config.logger_utils import get_logger
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftOutboxEvent,
    MinecraftPlayerScoreboardSnapshot,
    MinecraftTeamRegistration,
    MinecraftWorkerState,
)
from minecraft.services.outbox import queue_ensure_objectives, queue_full_sync
from minecraft.services.rcon_client import check_connection
from minecraft.services.outbox_cleanup import cleanup_outbox
from minecraft.services.scoreboard import refresh_scoreboard_snapshot
from minecraft.services.shop_catalog import build_shop_catalog_payload, category_count, item_count
from minecraft.services.shop_import import (
    collect_yaml_files,
    import_esgui_catalog,
    is_shop_yaml_path,
    normalize_section_upload_relative_path,
    normalize_shop_upload_relative_path,
    shop_relative_path,
)
from minecraft.services.bridge_connection import get_connected_server_ids
from minecraft.services.shop_push import push_shop_catalog_to_minecraft
from minecraft.services.shop_readiness import check_shop_readiness
from minecraft.services.ws_url import build_ws_events_url
from minecraft.services.preset_permissions import user_can_access_minecraft_control
from minecraft.services.rcon_presets import presets_grouped
from minecraft.services.team_registration import (
    active_registrations,
    deactivate_registration,
    deactivated_registrations,
    pending_team_candidates,
    register_group_for_minecraft,
    reactivate_registration,
)


logger = get_logger("minecraft")


def is_superuser(user):
    return user.is_superuser


def can_access_minecraft_control(user):
    return user_can_access_minecraft_control(user)


def _get_script_path() -> Path:
    script_path = Path(settings.BASE_DIR) / "scripts" / "minecraft.sh"
    if script_path.exists():
        return script_path.resolve()

    base_dir_resolved = Path(settings.BASE_DIR).resolve()
    if base_dir_resolved != Path(settings.BASE_DIR):
        alt_path = base_dir_resolved / "scripts" / "minecraft.sh"
        if alt_path.exists():
            return alt_path.resolve()

    return script_path


def _get_ws_script_path() -> Path:
    script_path = Path(settings.BASE_DIR) / "scripts" / "minecraft_ws.sh"
    if script_path.exists():
        return script_path.resolve()

    base_dir_resolved = Path(settings.BASE_DIR).resolve()
    if base_dir_resolved != Path(settings.BASE_DIR):
        alt_path = base_dir_resolved / "scripts" / "minecraft_ws.sh"
        if alt_path.exists():
            return alt_path.resolve()

    return script_path


def _run_script_status(script_path: Path, action: str = "status") -> dict:
    if not script_path.exists():
        return {"running": False, "error": _("Script not found")}

    if not os.access(script_path, os.X_OK):
        return {"running": False, "error": _("Script not executable")}

    try:
        result = subprocess.run(
            [str(script_path), action],
            capture_output=True,
            text=True,
            timeout=10,
        )
        running = result.returncode == 0
        output = result.stdout + result.stderr
        return {"running": running, "output": output}
    except Exception as exc:
        return {"running": False, "error": str(exc)}


def _get_worker_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "status")


def _get_snapshot_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "snapshot-status")


def _get_ws_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "status")


def _ws_events_url() -> str:
    """Public WebSocket URL for MCC-Bridge (from .env / ALLOWED_HOSTS + port)."""
    return build_ws_events_url()


def _ws_status_without_script_url(status: dict) -> dict:
    output = status.get("output")
    if not output:
        return status
    filtered = "\n".join(
        line for line in output.splitlines() if not line.strip().startswith("URL:")
    )
    return {**status, "output": filtered}


def _build_registered_accounts(snapshots: dict) -> list[dict]:
    accounts = []
    for registration in active_registrations():
        group = registration.group
        snapshot = snapshots.get(registration.mc_username)
        accounts.append(
            {
                "registration_id": registration.id,
                "player": registration.mc_username,
                "group": group,
                "velos_total": int(group.velos_total or 0),
                "velos_spendable": int(group.velos_spendable or 0),
                "snapshot_spendable": snapshot.velos_spendable if snapshot else None,
                "snapshot_time": snapshot.captured_at if snapshot else None,
            }
        )
    return accounts


@user_passes_test(can_access_minecraft_control)
@staff_member_required
def minecraft_control(request):
    script_path = _get_script_path()
    ws_script_path = _get_ws_script_path()
    worker_status = _get_worker_status(script_path)
    snapshot_status = _get_snapshot_status(script_path)
    ws_status = _ws_status_without_script_url(_get_ws_status(ws_script_path))
    integration_config = MinecraftIntegrationConfig.get_config()

    if request.method == "POST" and request.POST.get("form_type") == "config":
        integration_config.team_display_name = request.POST.get(
            "team_display_name", integration_config.team_display_name
        )[:64]
        integration_config.objective_spendable = request.POST.get(
            "objective_spendable", ""
        )[:64]
        integration_config.sync_on_earn = request.POST.get("sync_on_earn") == "on"
        integration_config.sidebar_enabled = request.POST.get("sidebar_enabled") == "on"
        integration_config.updated_by = request.user
        integration_config.save()
        queue_ensure_objectives(reason="admin_config_update")
        return redirect("admin:minecraft_control")

    outbox_counts = {
        "pending": MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_PENDING).count(),
        "processing": MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_PROCESSING).count(),
        "failed": MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_FAILED).count(),
    }
    show_outbox = request.GET.get("show_outbox") == "1"
    outbox_failed = []
    outbox_active = []
    if show_outbox:
        outbox_failed = list(
            MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_FAILED)
            .order_by("-created_at")[:10]
        )
        outbox_active = list(
            MinecraftOutboxEvent.objects.filter(
                status__in=[MinecraftOutboxEvent.STATUS_PENDING, MinecraftOutboxEvent.STATUS_PROCESSING]
            )
            .order_by("created_at")[:50]
        )

    snapshots = {
        snapshot.player_name: snapshot
        for snapshot in MinecraftPlayerScoreboardSnapshot.objects.all()
    }

    pending_teams = [
        {
            "group": group,
            "player": group.mc_username,
            "velos_total": int(group.velos_total or 0),
            "velos_spendable": int(group.velos_spendable or 0),
        }
        for group in pending_team_candidates()
    ]

    registered_teams = _build_registered_accounts(snapshots)
    deactivated_teams = [
        {
            "registration": registration,
            "group": registration.group,
            "player": registration.mc_username,
            "deactivated_at": registration.deactivated_at,
            "reason": _("Ausgeblendet") if not registration.group.is_visible else _("Deaktiviert"),
        }
        for registration in deactivated_registrations()
    ]

    state = MinecraftWorkerState.get_state()
    rcon_ok, rcon_error, rcon_mode = check_connection()
    script_path_str = str(script_path)
    script_exists = script_path.exists()
    script_executable = script_path.exists() and os.access(script_path, os.X_OK)

    ws_script_path_str = str(ws_script_path)
    ws_script_exists = ws_script_path.exists()
    ws_script_executable = ws_script_path.exists() and os.access(ws_script_path, os.X_OK)

    context = {
        "title": _("Minecraft Control"),
        "worker_status": worker_status,
        "snapshot_status": snapshot_status,
        "ws_status": ws_status,
        "ws_events_url": _ws_events_url(),
        "ws_bind_host": settings.MCC_MINECRAFT_WS_BIND_HOST,
        "script_path": script_path,
        "ws_script_path": ws_script_path,
        "script_path_str": script_path_str,
        "ws_script_path_str": ws_script_path_str,
        "script_exists": script_exists,
        "script_executable": script_executable,
        "ws_script_exists": ws_script_exists,
        "ws_script_executable": ws_script_executable,
        "outbox_counts": outbox_counts,
        "integration_config": integration_config,
        "pending_teams": pending_teams,
        "registered_teams": registered_teams,
        "deactivated_teams": deactivated_teams,
        "ws_enabled": settings.MCC_MINECRAFT_WS_ENABLED,
        "worker_state": state,
        "rcon_ok": rcon_ok,
        "rcon_error": rcon_error,
        "rcon_mode": rcon_mode,
        "show_outbox": show_outbox,
        "outbox_failed": outbox_failed,
        "outbox_active": outbox_active,
        "default_objective": settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE,
        "shop_category_count": category_count(),
        "shop_item_count": item_count(),
        "shop_catalog_preview": build_shop_catalog_payload(),
        "shop_bridge_connected": bool(get_connected_server_ids()),
        "shop_bridge_servers": get_connected_server_ids(),
        "rcon_preset_groups": presets_grouped(),
    }
    return render(request, "admin/minecraft/minecraft_control.html", context)


def _apply_shop_import_result(request, result) -> None:
    if result.errors:
        messages.warning(
            request,
            _(
                "Import mit Hinweisen: %(categories_created)s Kategorien neu, "
                "%(categories_updated)s aktualisiert, %(items_created)s Artikel neu, "
                "%(items_updated)s Artikel aktualisiert. Fehler: %(errors)s"
            )
            % {
                "categories_created": result.categories_created,
                "categories_updated": result.categories_updated,
                "items_created": result.items_created,
                "items_updated": result.items_updated,
                "errors": "; ".join(result.errors),
            },
        )
    else:
        messages.success(
            request,
            _(
                "Import erfolgreich: %(categories_created)s Kategorien neu, "
                "%(categories_updated)s aktualisiert, %(items_created)s Artikel neu, "
                "%(items_updated)s Artikel aktualisiert."
            )
            % {
                "categories_created": result.categories_created,
                "categories_updated": result.categories_updated,
                "items_created": result.items_created,
                "items_updated": result.items_updated,
            },
        )


def _read_uploaded_yaml_files(
    uploads,
    *,
    normalize_path,
) -> tuple[dict[str, str], str | None]:
    files: dict[str, str] = {}
    for upload in uploads:
        rel_path = normalize_path(shop_relative_path(upload.name))
        if rel_path is None:
            continue
        if not is_shop_yaml_path(rel_path):
            continue
        try:
            content = upload.read().decode("utf-8")
        except UnicodeDecodeError:
            return {}, _("Datei %(name)s ist keine gültige UTF-8-YAML-Datei.") % {"name": rel_path}
        if rel_path in files:
            if files[rel_path] == content:
                continue
            return {}, _(
                "Doppelter Shop-Pfad: %(path)s — mehrere verschiedene Dateien mit "
                "gleichem Namen. Bitte nur den shops/-Ordner wählen oder "
                "„Vom MC-Server importieren“ nutzen."
            ) % {"path": rel_path}
        files[rel_path] = content
    return files, None


@user_passes_test(is_superuser)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_import_shop(request):
    esgui_shops_dir = settings.MCC_MINECRAFT_ESGUI_SHOPS_DIR
    esgui_sections_dir = settings.MCC_MINECRAFT_ESGUI_SECTIONS_DIR

    if request.method == "GET":
        context = {
            "title": _("EconomyShopGUI importieren"),
            "shop_category_count": category_count(),
            "shop_item_count": item_count(),
            "esgui_shops_dir": esgui_shops_dir,
            "esgui_sections_dir": esgui_sections_dir,
            "server_import_enabled": bool(esgui_shops_dir),
        }
        return render(request, "admin/minecraft/minecraft_shop_import.html", context)

    replace_items = request.POST.get("replace_items") == "on"
    import_source = request.POST.get("import_source", "upload")

    if import_source == "server":
        if not esgui_shops_dir:
            messages.error(request, _("Server-Import nicht konfiguriert (MCC_MINECRAFT_ESGUI_SHOPS_DIR)."))
            return redirect("admin:minecraft_import_shop")

        shops_path = Path(esgui_shops_dir)
        if not shops_path.is_dir():
            messages.error(
                request,
                _("Shop-Verzeichnis nicht gefunden: %(path)s") % {"path": esgui_shops_dir},
            )
            return redirect("admin:minecraft_import_shop")

        shop_files = collect_yaml_files(shops_path)
        section_files = (
            collect_yaml_files(Path(esgui_sections_dir))
            if esgui_sections_dir and Path(esgui_sections_dir).is_dir()
            else {}
        )
        if not shop_files:
            messages.error(
                request,
                _("Keine Shop-YAML-Dateien unter %(path)s gefunden.") % {"path": esgui_shops_dir},
            )
            return redirect("admin:minecraft_import_shop")
    else:
        shop_uploads = request.FILES.getlist("shop_files")
        section_uploads = request.FILES.getlist("section_files")

        if not shop_uploads:
            messages.error(
                request,
                _("Bitte mindestens eine Shop-YAML-Datei oder ein shops/-Verzeichnis wählen."),
            )
            return redirect("admin:minecraft_import_shop")

        shop_files, shop_error = _read_uploaded_yaml_files(
            shop_uploads,
            normalize_path=normalize_shop_upload_relative_path,
        )
        if shop_error:
            messages.error(request, shop_error)
            return redirect("admin:minecraft_import_shop")

        if not shop_files:
            messages.error(
                request,
                _(
                    "Keine gültigen Shop-YAML-Dateien (.yml/.yaml) unter shops/ gefunden. "
                    "Andere Dateien (z. B. transactions.db) und sections/ werden ignoriert."
                ),
            )
            return redirect("admin:minecraft_import_shop")

        section_files, section_error = _read_uploaded_yaml_files(
            section_uploads,
            normalize_path=normalize_section_upload_relative_path,
        )
        if section_error:
            messages.error(request, section_error)
            return redirect("admin:minecraft_import_shop")

    try:
        result = import_esgui_catalog(
            shop_files=shop_files,
            section_files=section_files,
            replace_items=replace_items,
        )
    except Exception as exc:
        logger.error("[minecraft_control] shop import failed: %s", exc, exc_info=True)
        messages.error(request, _("Import fehlgeschlagen: %(error)s") % {"error": exc})
        return redirect("admin:minecraft_import_shop")

    _apply_shop_import_result(request, result)
    return redirect("admin:minecraft_import_shop")


@user_passes_test(is_superuser)
@staff_member_required
@require_POST
def minecraft_register_team(request, group_id):
    from api.models import Group

    try:
        group = Group.objects.get(pk=group_id)
        register_group_for_minecraft(group, user=request.user)
        return JsonResponse({
            "success": True,
            "message": _(
                "Team registriert. LuckPerms-Gruppe und Shop-Zuordnung werden "
                "vom Minecraft-Worker synchronisiert."
            ),
        })
    except Group.DoesNotExist:
        return JsonResponse({"success": False, "error": _("Gruppe nicht gefunden")}, status=404)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.error(f"[minecraft_control] register failed: {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@user_passes_test(is_superuser)
@staff_member_required
@require_POST
def minecraft_deactivate_team(request, registration_id):
    try:
        registration = MinecraftTeamRegistration.objects.select_related("group").get(pk=registration_id)
        deactivate_registration(registration, reason="manual_deactivate")
        return JsonResponse({"success": True, "message": _("Team deaktiviert")})
    except MinecraftTeamRegistration.DoesNotExist:
        return JsonResponse({"success": False, "error": _("Registrierung nicht gefunden")}, status=404)
    except Exception as exc:
        logger.error(f"[minecraft_control] deactivate failed: {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@user_passes_test(is_superuser)
@staff_member_required
@require_POST
def minecraft_reactivate_team(request, registration_id):
    try:
        registration = MinecraftTeamRegistration.objects.select_related("group").get(pk=registration_id)
        reactivate_registration(registration)
        return JsonResponse({"success": True, "message": _("Team reaktiviert")})
    except MinecraftTeamRegistration.DoesNotExist:
        return JsonResponse({"success": False, "error": _("Registrierung nicht gefunden")}, status=404)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.error(f"[minecraft_control] reactivate failed: {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@user_passes_test(is_superuser)
@staff_member_required
def minecraft_action(request, action):
    if request.method != "POST":
        return JsonResponse({"error": _("Only POST allowed")}, status=405)

    if action not in [
        "start",
        "stop",
        "status",
        "sync",
        "snapshot",
        "rcon-test",
        "cleanup",
        "push-shop",
        "snapshot-start",
        "snapshot-stop",
        "snapshot-status",
        "ensure-objectives",
        "ws-start",
        "ws-stop",
        "ws-restart",
        "ws-status",
        "shop-check",
    ]:
        return JsonResponse({"error": _("Invalid action")}, status=400)

    if action == "push-shop":
        try:
            server_id = request.POST.get("server_id") or None
            ok, message = push_shop_catalog_to_minecraft(server_id=server_id)
            if ok:
                return JsonResponse({"success": True, "message": message})
            return JsonResponse({"success": False, "error": message}, status=400)
        except Exception as exc:
            logger.error(f"[minecraft_control] push-shop failed: {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    if action == "shop-check":
        try:
            script_path = _get_script_path()
            ws_script_path = _get_ws_script_path()
            report = check_shop_readiness(
                worker_running=_get_worker_status(script_path).get("running"),
                snapshot_worker_running=_get_snapshot_status(script_path).get("running"),
                ws_running=_get_ws_status(ws_script_path).get("running"),
            )
            return JsonResponse({"success": True, **report.to_dict()})
        except Exception as exc:
            logger.error(f"[minecraft_control] shop-check failed: {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    if action == "sync":
        try:
            queue_full_sync(reason="manual_admin_sync")
            return JsonResponse({"success": True, "message": _("Sync queued")})
        except Exception as exc:
            logger.error(f"[minecraft_control] sync failed: {exc}")
            return JsonResponse({"success": False, "error": _("Sync failed: %(error)s") % {"error": exc}}, status=500)

    if action == "ensure-objectives":
        try:
            queue_ensure_objectives(reason="manual_admin_ensure")
            return JsonResponse({"success": True, "message": _("Objectives queued")})
        except Exception as exc:
            logger.error(f"[minecraft_control] ensure-objectives failed: {exc}")
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    if action == "snapshot":
        try:
            logger.info(f"[minecraft_control] snapshot action started by user={request.user}")
            updated = refresh_scoreboard_snapshot()
            message = _("Snapshot updated: %(count)s teams updated") % {"count": updated}
            logger.info(f"[minecraft_control] snapshot completed: {updated} teams updated")
            return JsonResponse({"success": True, "message": message})
        except Exception as exc:
            logger.error(f"[minecraft_control] snapshot failed: {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": _("Snapshot failed: %(error)s") % {"error": exc}}, status=500)

    if action == "rcon-test":
        try:
            ok, error, mode = check_connection()
            if ok and mode == "auth":
                return JsonResponse({"success": True, "message": _("RCON connection OK")})
            if ok and mode != "auth":
                return JsonResponse({"success": True, "message": _("RCON port reachable (Auth not checked)")})
            return JsonResponse({"success": False, "error": _("RCON error: %(error)s") % {"error": error}}, status=500)
        except Exception as exc:
            logger.error(f"[minecraft_control] rcon-test failed: {exc}")
            return JsonResponse({"success": False, "error": _("RCON test failed: %(error)s") % {"error": exc}}, status=500)

    if action == "cleanup":
        try:
            result = cleanup_outbox()
            message = (
                f"Cleanup done: "
                f"done={result['deleted_done']} "
                f"failed={result['deleted_failed']} "
                f"overflow={result['deleted_overflow']}"
            )
            return JsonResponse({"success": True, "message": message})
        except Exception as exc:
            logger.error(f"[minecraft_control] cleanup failed: {exc}")
            return JsonResponse({"success": False, "error": f"Cleanup fehlgeschlagen: {exc}"}, status=500)

    if action.startswith("ws-"):
        script_path = _get_ws_script_path()
        ws_action = action[3:]
        if ws_action not in ("start", "stop", "restart", "status"):
            return JsonResponse({"error": _("Invalid action")}, status=400)
    else:
        script_path = _get_script_path()
        ws_action = None

    if not script_path.exists():
        abs_path = str(script_path.resolve() if script_path.exists() else script_path.absolute())
        return JsonResponse({
            "error": _("Script not found: %(path)s") % {"path": abs_path},
            "success": False,
            "script_path": abs_path,
            "base_dir": str(settings.BASE_DIR),
        }, status=404)

    if not os.access(script_path, os.X_OK):
        return JsonResponse({"error": _("Script not executable"), "success": False}, status=403)

    try:
        script_action = ws_action if ws_action else action
        run_in_background = (
            (ws_action is not None and ws_action in ("start", "stop"))
            or (ws_action is None and action in ("start", "stop", "snapshot-start", "snapshot-stop"))
        )
        if run_in_background:
            if hasattr(settings, 'LOGS_DIR'):
                logs_dir = Path(settings.LOGS_DIR)
            else:
                logs_dir = Path(settings.BASE_DIR) / "data" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            action_log = logs_dir / "minecraft_action.log"

            try:
                with open(action_log, "a") as log_handle:
                    log_handle.write(f"\n--- {action} started by {request.user} ---\n")
                    log_handle.flush()
                    subprocess.Popen(
                        [str(script_path), script_action],
                        stdout=log_handle,
                        stderr=log_handle,
                        start_new_session=True,
                        close_fds=True,
                    )
            except Exception as log_exc:
                logger.error(f"[minecraft_control] Failed to write to log file {action_log}: {log_exc}")

            action_log_str = str(action_log.resolve() if action_log.exists() else action_log)
            return JsonResponse(
                {
                    "success": True,
                    "message": _("Action '%(action)s' started in background") % {"action": action},
                    "output": _("Background execution. Details in %(log)s") % {"log": action_log_str},
                },
                status=202,
            )

        result = subprocess.run(
            [str(script_path), script_action],
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if ws_action:
            status_info = _get_ws_status(script_path)
        else:
            status_info = _get_worker_status(script_path)
        return JsonResponse(
            {
                "success": success,
                "message": _("Action '%(action)s' executed") % {"action": action},
                "output": output,
                "status": status_info,
            },
            status=200 if success else 500,
        )
    except Exception as exc:
        logger.error(f"[minecraft_control] action failed: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
