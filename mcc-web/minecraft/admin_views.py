import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from api.models import Cyclist
from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent, MinecraftPlayerScoreboardSnapshot, MinecraftWorkerState
from minecraft.services.outbox import queue_full_sync
from minecraft.services.rcon_client import check_connection
from minecraft.services.outbox_cleanup import cleanup_outbox
from minecraft.services.scoreboard import refresh_scoreboard_snapshot


logger = get_logger("minecraft")


def is_superuser(user):
    return user.is_superuser


def _get_script_path() -> Path:
    """
    Get the path to the minecraft.sh script.
    
    Tries multiple locations:
    1. BASE_DIR/scripts/minecraft.sh (standard location)
    2. Alternative paths for production deployments
    """
    # Primary path: BASE_DIR/scripts/minecraft.sh
    script_path = Path(settings.BASE_DIR) / "scripts" / "minecraft.sh"
    
    # If script exists, return resolved absolute path
    if script_path.exists():
        return script_path.resolve()
    
    # Try alternative: if BASE_DIR is a symlink, try to find the actual script
    # In production, BASE_DIR might be /data/appl/mcc/mcc-web (symlink)
    # The script should be in the actual versioned directory
    base_dir_resolved = Path(settings.BASE_DIR).resolve()
    if base_dir_resolved != Path(settings.BASE_DIR):
        alt_path = base_dir_resolved / "scripts" / "minecraft.sh"
        if alt_path.exists():
            return alt_path.resolve()
    
    # Return the original path (even if it doesn't exist) for error reporting
    return script_path


def _get_worker_status(script_path: Path) -> dict:
    if not script_path.exists():
        return {"running": False, "error": _("Script not found")}

    if not os.access(script_path, os.X_OK):
        return {"running": False, "error": _("Script not executable")}

    try:
        result = subprocess.run(
            [str(script_path), "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        running = result.returncode == 0
        output = result.stdout + result.stderr
        return {"running": running, "output": output}
    except Exception as exc:
        return {"running": False, "error": str(exc)}


def _get_snapshot_status(script_path: Path) -> dict:
    if not script_path.exists():
        return {"running": False, "error": _("Script not found")}

    if not os.access(script_path, os.X_OK):
        return {"running": False, "error": _("Script not executable")}

    try:
        result = subprocess.run(
            [str(script_path), "snapshot-status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        running = result.returncode == 0
        output = result.stdout + result.stderr
        return {"running": running, "output": output}
    except Exception as exc:
        return {"running": False, "error": str(exc)}


@user_passes_test(is_superuser)
@staff_member_required
def minecraft_control(request):
    script_path = _get_script_path()
    worker_status = _get_worker_status(script_path)
    snapshot_status = _get_snapshot_status(script_path)

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

    players = []
    for cyclist in Cyclist.objects.filter(mc_username__isnull=False).order_by("mc_username"):
        if not cyclist.mc_username:
            continue
        snapshot = snapshots.get(cyclist.mc_username)
        players.append(
            {
                "player": cyclist.mc_username,
                "cyclist": cyclist,
                "coins_total": cyclist.coins_total,
                "coins_spendable": cyclist.coins_spendable,
                "snapshot_total": snapshot.coins_total if snapshot else None,
                "snapshot_spendable": snapshot.coins_spendable if snapshot else None,
                "snapshot_time": snapshot.captured_at if snapshot else None,
            }
        )

    state = MinecraftWorkerState.get_state()

    rcon_ok, rcon_error, rcon_mode = check_connection()

    # Add script path info for debugging
    script_path_str = str(script_path)
    script_exists = script_path.exists()
    script_executable = script_path.exists() and os.access(script_path, os.X_OK)
    
    context = {
        "title": _("Minecraft Control"),
        "worker_status": worker_status,
        "snapshot_status": snapshot_status,
        "script_path": script_path,
        "script_path_str": script_path_str,
        "script_exists": script_exists,
        "script_executable": script_executable,
        "outbox_counts": outbox_counts,
        "players": players,
        "ws_enabled": settings.MCC_MINECRAFT_WS_ENABLED,
        "worker_state": state,
        "rcon_ok": rcon_ok,
        "rcon_error": rcon_error,
        "rcon_mode": rcon_mode,
        "show_outbox": show_outbox,
        "outbox_failed": outbox_failed,
        "outbox_active": outbox_active,
    }
    return render(request, "admin/minecraft/minecraft_control.html", context)


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
        "snapshot-start",
        "snapshot-stop",
        "snapshot-status",
    ]:
        return JsonResponse({"error": _("Invalid action")}, status=400)

    if action == "sync":
        try:
            queue_full_sync(reason="manual_admin_sync")
            return JsonResponse({"success": True, "message": _("Sync queued")})
        except Exception as exc:
            logger.error(f"[minecraft_control] sync failed: {exc}")
            return JsonResponse({"success": False, "error": _("Sync failed: %(error)s") % {"error": exc}}, status=500)

    if action == "snapshot":
        try:
            logger.info(f"[minecraft_control] snapshot action started by user={request.user}")
            # Call the function directly instead of using subprocess to avoid PYTHONPATH conflicts
            updated = refresh_scoreboard_snapshot()
            message = _("Snapshot updated: %(count)s players updated") % {"count": updated}
            logger.info(f"[minecraft_control] snapshot completed: {updated} players updated")
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

    script_path = _get_script_path()
    if not script_path.exists():
        # Return absolute path for better debugging
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
        if action in ["start", "stop", "snapshot-start", "snapshot-stop"]:
            # Use LOGS_DIR from settings (production: /data/var/mcc/logs, dev: BASE_DIR/logs)
            if hasattr(settings, 'LOGS_DIR'):
                logs_dir = Path(settings.LOGS_DIR)
            else:
                logs_dir = Path(settings.BASE_DIR) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            action_log = logs_dir / "minecraft_action.log"
            
            try:
                with open(action_log, "a") as log_handle:
                    log_handle.write(f"\n--- {action} started by {request.user} ---\n")
                    log_handle.flush()
                    subprocess.Popen(
                        [str(script_path), action],
                        stdout=log_handle,
                        stderr=log_handle,
                        start_new_session=True,
                        close_fds=True,
                    )
            except Exception as log_exc:
                logger.error(f"[minecraft_control] Failed to write to log file {action_log}: {log_exc}")
                # Continue anyway, but log the error
            
            # Return message with absolute path for better visibility
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
            [str(script_path), action],
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        status = _get_worker_status(script_path)
        return JsonResponse(
            {
                "success": success,
                "message": _("Action '%(action)s' executed") % {"action": action},
                "output": output,
                "status": status,
            },
            status=200 if success else 500,
        )
    except Exception as exc:
        logger.error(f"[minecraft_control] action failed: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
