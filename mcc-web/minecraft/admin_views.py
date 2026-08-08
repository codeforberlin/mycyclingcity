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
    MinecraftProtectedRegion,
    MinecraftTeamRegistration,
    MinecraftWorkerState,
)
from minecraft.services.outbox import queue_ensure_objectives, queue_full_sync
from minecraft.services.rcon_client import check_connection, run_command
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
from minecraft.services.preset_permissions import (
    user_can_access_minecraft_city,
    user_can_access_minecraft_control,
    user_can_access_minecraft_shop,
    user_can_manage_coreprotect,
    user_can_manage_minecraft_proxy,
    user_can_manage_protected_regions,
    user_can_run_free_rcon,
)
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

SHOP_ACTIONS = frozenset({"push-shop", "shop-check"})
PROXY_ACTIONS = frozenset(
    {
        "velocity-start",
        "velocity-stop",
        "velocity-status",
        "limbo-start",
        "limbo-stop",
        "limbo-status",
    }
)
PAPER_ACTIONS = frozenset(
    {
        "paper-start",
        "paper-stop",
        "paper-status",
    }
)
PAPER_SCRIPT_ARGS = {
    "paper-start": "start",
    "paper-stop": "stop",
    "paper-status": "status",
}


def can_access_minecraft_control(user):
    return user_can_access_minecraft_control(user)


def can_access_minecraft_city(user):
    return user_can_access_minecraft_city(user)


def can_access_minecraft_shop(user):
    return user_can_access_minecraft_shop(user)


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


def _get_proxy_script_path() -> Path:
    script_path = Path(settings.BASE_DIR) / "scripts" / "minecraft_proxy.sh"
    if script_path.exists():
        return script_path.resolve()

    base_dir_resolved = Path(settings.BASE_DIR).resolve()
    if base_dir_resolved != Path(settings.BASE_DIR):
        alt_path = base_dir_resolved / "scripts" / "minecraft_proxy.sh"
        if alt_path.exists():
            return alt_path.resolve()

    return script_path


def _get_paper_script_path() -> Path:
    script_path = Path(settings.BASE_DIR) / "scripts" / "minecraft_paper.sh"
    if script_path.exists():
        return script_path.resolve()

    base_dir_resolved = Path(settings.BASE_DIR).resolve()
    if base_dir_resolved != Path(settings.BASE_DIR):
        alt_path = base_dir_resolved / "scripts" / "minecraft_paper.sh"
        if alt_path.exists():
            return alt_path.resolve()

    return script_path


def _proxy_script_env() -> dict[str, str]:
    """Env for minecraft_proxy.sh so Django settings override script defaults."""
    env = os.environ.copy()
    env["MCC_MINECRAFT_VELOCITY_DIR"] = str(
        getattr(settings, "MCC_MINECRAFT_VELOCITY_DIR", "") or ""
    )
    env["MCC_MINECRAFT_LIMBO_DIR"] = str(
        getattr(settings, "MCC_MINECRAFT_LIMBO_DIR", "") or ""
    )
    env["MCC_MINECRAFT_VELOCITY_PIDFILE"] = str(
        getattr(settings, "MCC_MINECRAFT_VELOCITY_PIDFILE", "") or ""
    )
    env["MCC_MINECRAFT_LIMBO_PIDFILE"] = str(
        getattr(settings, "MCC_MINECRAFT_LIMBO_PIDFILE", "") or ""
    )
    env["MCC_MINECRAFT_VELOCITY_LOG"] = str(
        getattr(settings, "MCC_MINECRAFT_VELOCITY_LOG", "") or ""
    )
    env["MCC_MINECRAFT_LIMBO_LOG"] = str(
        getattr(settings, "MCC_MINECRAFT_LIMBO_LOG", "") or ""
    )
    return env


def _paper_script_env() -> dict[str, str]:
    """Env for minecraft_paper.sh so Django settings override script defaults."""
    env = os.environ.copy()
    env["MCC_MINECRAFT_PAPER_DIR"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    )
    env["MCC_MINECRAFT_PAPER_PIDFILE"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_PIDFILE", "") or ""
    )
    env["MCC_MINECRAFT_PAPER_LOG"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_LOG", "") or ""
    )
    env["MCC_MINECRAFT_PAPER_JAR_MATCH"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_JAR_MATCH", "paper-") or "paper-"
    )
    env["MCC_MINECRAFT_PAPER_JAR_NAME"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_JAR_NAME", "") or ""
    )
    env["MCC_MINECRAFT_PAPER_STOP_WAIT"] = str(
        getattr(settings, "MCC_MINECRAFT_PAPER_STOP_WAIT", 90)
    )
    java_opts = getattr(settings, "MCC_MINECRAFT_PAPER_JAVA_OPTS", None)
    if java_opts:
        env["MCC_MINECRAFT_PAPER_JAVA_OPTS"] = str(java_opts)
    env["MCC_MINECRAFT_RCON_HOST"] = str(
        getattr(settings, "MCC_MINECRAFT_RCON_HOST", "127.0.0.1")
    )
    env["MCC_MINECRAFT_RCON_PORT"] = str(
        getattr(settings, "MCC_MINECRAFT_RCON_PORT", 25575)
    )
    env["MCC_MINECRAFT_RCON_PASSWORD"] = str(
        getattr(settings, "MCC_MINECRAFT_RCON_PASSWORD", "") or ""
    )
    return env


def _run_script_status(
    script_path: Path,
    action: str = "status",
    *,
    env: dict[str, str] | None = None,
) -> dict:
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
            env=env,
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


def _get_session_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "session-status")


def _get_arena_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "arena-status")


def _get_ws_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "status")


def _get_velocity_status(script_path: Path) -> dict:
    return _run_script_status(
        script_path, "velocity-status", env=_proxy_script_env()
    )


def _get_limbo_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "limbo-status", env=_proxy_script_env())


def _get_paper_status(script_path: Path) -> dict:
    return _run_script_status(script_path, "status", env=_paper_script_env())


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


def _handle_free_rcon_post(request):
    """Process free RCON form POST; returns redirect response."""
    if not user_can_run_free_rcon(request.user):
        messages.error(request, _("Keine Berechtigung für freie RCON-Befehle."))
        return redirect("admin:minecraft_control")

    command = (request.POST.get("rcon_command") or "").strip()
    if not command:
        messages.error(request, _("RCON-Befehl darf nicht leer sein."))
        return redirect("admin:minecraft_control")

    logger.info(
        "[minecraft_control] free_rcon user=%s command=%r",
        request.user,
        command,
    )
    try:
        response = run_command(command)
        messages.success(
            request,
            _("RCON OK: %(cmd)s → %(response)s")
            % {"cmd": command, "response": response or "(ok)"},
        )
    except Exception as exc:
        logger.error(
            "[minecraft_control] free_rcon failed user=%s command=%r: %s",
            request.user,
            command,
            exc,
            exc_info=True,
        )
        messages.error(
            request,
            _("RCON fehlgeschlagen: %(cmd)s → %(error)s")
            % {"cmd": command, "error": exc},
        )
    return redirect("admin:minecraft_control")


@user_passes_test(can_access_minecraft_control)
@staff_member_required
def minecraft_control(request):
    integration_config = MinecraftIntegrationConfig.get_config()

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        if form_type == "config":
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
        if form_type == "free_rcon":
            return _handle_free_rcon_post(request)

    script_path = _get_script_path()
    ws_script_path = _get_ws_script_path()
    proxy_script_path = _get_proxy_script_path()
    paper_script_path = _get_paper_script_path()
    worker_status = _get_worker_status(script_path)
    snapshot_status = _get_snapshot_status(script_path)
    session_status = _get_session_status(script_path)
    arena_status = _get_arena_status(script_path)
    ws_status = _ws_status_without_script_url(_get_ws_status(ws_script_path))
    can_manage_proxy = user_can_manage_minecraft_proxy(request.user)
    velocity_status = (
        _get_velocity_status(proxy_script_path) if can_manage_proxy else {"running": False}
    )
    limbo_status = (
        _get_limbo_status(proxy_script_path) if can_manage_proxy else {"running": False}
    )
    paper_status = (
        _get_paper_status(paper_script_path) if can_manage_proxy else {"running": False}
    )

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
    velocity_rcon_ok = False
    velocity_rcon_error = ""
    velocity_rcon_mode = ""
    velocity_rcon_endpoint = ""
    if can_manage_proxy:
        from minecraft.services.velocity_rcon import (
            check_connection as check_velocity_rcon,
            get_velocity_rcon_config,
        )

        try:
            velocity_rcon_ok, velocity_rcon_error, velocity_rcon_mode = check_velocity_rcon()
            cfg = get_velocity_rcon_config()
            velocity_rcon_endpoint = f"{cfg.host}:{cfg.port}"
        except Exception as exc:
            logger.exception("[minecraft_control] velocity RCON check failed")
            velocity_rcon_ok = False
            velocity_rcon_error = str(exc)
            velocity_rcon_mode = "auth"
            try:
                cfg = get_velocity_rcon_config()
                velocity_rcon_endpoint = f"{cfg.host}:{cfg.port}"
            except Exception:
                velocity_rcon_endpoint = ""
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
        "session_status": session_status,
        "arena_status": arena_status,
        "ws_status": ws_status,
        "velocity_status": velocity_status,
        "limbo_status": limbo_status,
        "paper_status": paper_status,
        "can_manage_minecraft_proxy": can_manage_proxy,
        "velocity_log_key": "minecraft_velocity",
        "limbo_log_key": "minecraft_limbo",
        "paper_log_key": "minecraft_paper",
        "ws_events_url": _ws_events_url(),
        "ws_bind_host": settings.MCC_MINECRAFT_WS_BIND_HOST,
        "script_path": script_path,
        "ws_script_path": ws_script_path,
        "proxy_script_path": proxy_script_path,
        "paper_script_path": paper_script_path,
        "script_path_str": script_path_str,
        "ws_script_path_str": ws_script_path_str,
        "script_exists": script_exists,
        "script_executable": script_executable,
        "ws_script_exists": ws_script_exists,
        "ws_script_executable": ws_script_executable,
        "proxy_script_exists": proxy_script_path.exists(),
        "proxy_script_executable": proxy_script_path.exists()
        and os.access(proxy_script_path, os.X_OK),
        "paper_script_exists": paper_script_path.exists(),
        "paper_script_executable": paper_script_path.exists()
        and os.access(paper_script_path, os.X_OK),
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
        "velocity_rcon_ok": velocity_rcon_ok,
        "velocity_rcon_error": velocity_rcon_error,
        "velocity_rcon_mode": velocity_rcon_mode,
        "velocity_rcon_endpoint": velocity_rcon_endpoint,
        "show_outbox": show_outbox,
        "outbox_failed": outbox_failed,
        "outbox_active": outbox_active,
        "default_objective": settings.MCC_MINECRAFT_SCOREBOARD_TEAM_SPENDABLE,
        "can_run_free_rcon": user_can_run_free_rcon(request.user),
    }
    return render(request, "admin/minecraft/minecraft_control.html", context)


@user_passes_test(can_access_minecraft_city)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_city(request):
    from minecraft.services.chunky_pregen import (
        DEFAULT_CHUNKY_QUIET_SECONDS,
        border_to_chunky_selection,
        cancel_pregen,
        continue_pregen,
        pause_pregen,
        read_progress,
        start_pregen,
    )
    from minecraft.services.coreprotect_ops import (
        TIME_PRESETS,
        allowed_radii,
        list_known_ms_logins,
        run_co_apply,
        run_co_preview,
        run_co_undo,
    )
    from minecraft.services.region_ops import (
        apply_region_full,
        default_region_max_y,
        default_region_min_y,
        fetch_player_block_pos,
        normalize_region_id,
        paper_world,
        parse_int_coord,
        remove_region_from_server,
        sync_region_members,
    )
    from minecraft.services.world_border import (
        WORLD_BORDER_SIZE_PRESETS,
        apply_world_border,
        preview_half_extent,
        read_spawn_from_server_properties,
        read_world_border_status,
    )

    integration_config = MinecraftIntegrationConfig.get_config()
    border_status = None
    border_message = ""
    chunky_progress = None
    chunky_selection = border_to_chunky_selection(integration_config)
    co_output = None
    can_coreprotect = user_can_manage_coreprotect(request.user)
    can_regions = user_can_manage_protected_regions(request.user)
    region_output = None
    region_draft = None

    if request.method == "POST":
        form_type = (request.POST.get("form_type") or "").strip()
        if form_type == "world_border":
            action = (request.POST.get("action") or "").strip()
            try:
                if action in {"save", "apply", "preset", "center_spawn", "disable"}:
                    if action == "preset":
                        size = int(request.POST.get("preset_size") or 0)
                        if size in WORLD_BORDER_SIZE_PRESETS:
                            integration_config.world_border_size = size
                    elif action != "center_spawn":
                        integration_config.world_border_center_x = float(
                            request.POST.get("world_border_center_x", integration_config.world_border_center_x)
                        )
                        integration_config.world_border_center_z = float(
                            request.POST.get("world_border_center_z", integration_config.world_border_center_z)
                        )
                        size = int(
                            request.POST.get("world_border_size", integration_config.world_border_size)
                        )
                        if size >= 1:
                            integration_config.world_border_size = size
                        warn = int(
                            request.POST.get(
                                "world_border_warning_distance",
                                integration_config.world_border_warning_distance,
                            )
                        )
                        if warn >= 0:
                            integration_config.world_border_warning_distance = warn
                        damage = float(
                            request.POST.get(
                                "world_border_damage_amount",
                                integration_config.world_border_damage_amount,
                            )
                        )
                        if damage >= 0:
                            integration_config.world_border_damage_amount = damage

                    if action == "center_spawn":
                        spawn = read_spawn_from_server_properties()
                        if spawn is None:
                            messages.warning(
                                request,
                                _(
                                    "Spawn-Koordinaten nicht aus server.properties lesbar. "
                                    "Zentrum bitte manuell setzen."
                                ),
                            )
                        else:
                            integration_config.world_border_center_x = spawn[0]
                            integration_config.world_border_center_z = spawn[1]
                            messages.success(
                                request,
                                _("Zentrum auf Spawn (%(x)s / %(z)s) gesetzt.")
                                % {"x": spawn[0], "z": spawn[1]},
                            )

                    if action == "disable":
                        integration_config.world_border_enabled = False
                    elif action in {"apply", "preset", "save", "center_spawn"}:
                        if action == "apply" or action == "preset":
                            integration_config.world_border_enabled = True

                    integration_config.updated_by = request.user
                    integration_config.save()

                    if action in {"apply", "preset", "disable"}:
                        enabled = action != "disable"
                        ok, output = apply_world_border(
                            integration_config, enabled=enabled
                        )
                        if ok:
                            messages.success(
                                request,
                                _("World Border angewendet.")
                                if enabled
                                else _("World Border deaktiviert (Maximum)."),
                            )
                            if output:
                                border_message = output
                        else:
                            messages.error(
                                request,
                                _("World Border RCON fehlgeschlagen: %(err)s")
                                % {"err": output},
                            )
                    elif action == "save":
                        messages.success(request, _("World-Border-Einstellungen gespeichert."))

                elif action == "status":
                    border_status = read_world_border_status()
                    if border_status.get("ok"):
                        size = border_status.get("size")
                        messages.info(
                            request,
                            _("Aktuelle Border-Größe: %(size)s Blöcke")
                            % {"size": size if size is not None else "—"},
                        )
                    else:
                        messages.error(
                            request,
                            _("Status lesen fehlgeschlagen: %(err)s")
                            % {"err": border_status.get("error") or border_status.get("raw")},
                        )
                else:
                    messages.error(request, _("Unbekannte World-Border-Aktion."))
                    return redirect("admin:minecraft_city")
            except (TypeError, ValueError) as exc:
                messages.error(request, _("Ungültige Border-Werte: %(err)s") % {"err": exc})
                return redirect("admin:minecraft_city")

            if action != "status":
                return redirect("admin:minecraft_city")

        elif form_type == "chunky_pregen":
            action = (request.POST.get("action") or "").strip()
            try:
                radius_raw = (request.POST.get("chunky_radius") or "").strip()
                radius_override = int(radius_raw) if radius_raw else None
                if radius_override is not None and radius_override < 1:
                    raise ValueError("radius must be >= 1")
                use_live = request.POST.get("use_live_worldborder") == "on"
                quiet_raw = (request.POST.get("chunky_quiet") or "").strip()
                quiet = int(quiet_raw) if quiet_raw else DEFAULT_CHUNKY_QUIET_SECONDS
                if quiet < 1:
                    quiet = DEFAULT_CHUNKY_QUIET_SECONDS

                if action == "start":
                    ok, output, selection = start_pregen(
                        integration_config,
                        radius_override=radius_override,
                        quiet=quiet,
                        use_live_worldborder=use_live,
                    )
                    chunky_selection = selection
                    if ok:
                        messages.success(
                            request,
                            _(
                                "Chunky gestartet: %(world)s square, Zentrum (%(x)s/%(z)s), "
                                "Radius %(r)s (ca. %(edge)s×%(edge)s)."
                            )
                            % {
                                "world": selection["world"],
                                "x": selection["center_x"],
                                "z": selection["center_z"],
                                "r": selection["radius"],
                                "edge": selection["edge"],
                            },
                        )
                    else:
                        messages.error(
                            request,
                            _("Chunky Start fehlgeschlagen: %(err)s") % {"err": output},
                        )
                    return redirect("admin:minecraft_city")

                if action == "pause":
                    ok, output = pause_pregen()
                    if ok:
                        messages.success(request, _("Chunky pausiert."))
                    else:
                        messages.error(request, _("Chunky Pause fehlgeschlagen: %(err)s") % {"err": output})
                    return redirect("admin:minecraft_city")

                if action == "continue":
                    ok, output = continue_pregen()
                    if ok:
                        messages.success(request, _("Chunky fortgesetzt."))
                    else:
                        messages.error(
                            request,
                            _("Chunky Continue fehlgeschlagen: %(err)s") % {"err": output},
                        )
                    return redirect("admin:minecraft_city")

                if action == "cancel":
                    ok, output = cancel_pregen()
                    if ok:
                        messages.success(request, _("Chunky abgebrochen."))
                    else:
                        messages.error(
                            request,
                            _("Chunky Cancel fehlgeschlagen: %(err)s") % {"err": output},
                        )
                    return redirect("admin:minecraft_city")

                if action == "progress":
                    chunky_progress = read_progress()
                    if chunky_progress.get("ok"):
                        messages.info(request, _("Chunky-Fortschritt gelesen."))
                    else:
                        messages.error(
                            request,
                            _("Chunky Progress fehlgeschlagen: %(err)s")
                            % {"err": chunky_progress.get("error")},
                        )
                    chunky_selection = border_to_chunky_selection(
                        integration_config, radius_override=radius_override
                    )
                else:
                    messages.error(request, _("Unbekannte Chunky-Aktion."))
                    return redirect("admin:minecraft_city")
            except (TypeError, ValueError) as exc:
                messages.error(request, _("Ungültige Chunky-Werte: %(err)s") % {"err": exc})
                return redirect("admin:minecraft_city")

        elif form_type == "coreprotect":
            if not can_coreprotect:
                messages.error(request, _("Keine Berechtigung für CoreProtect."))
                return redirect("admin:minecraft_city")
            action = (request.POST.get("action") or "").strip()
            try:
                if action == "undo":
                    ok, output = run_co_undo(admin_user=str(request.user))
                    co_output = output
                    if ok:
                        messages.success(request, _("CoreProtect Undo ausgeführt."))
                    else:
                        messages.error(
                            request,
                            _("CoreProtect Undo fehlgeschlagen: %(err)s") % {"err": output},
                        )
                    # keep output on page
                elif action in {"preview", "apply"}:
                    player = (request.POST.get("co_user") or "").strip()
                    time_spec = (request.POST.get("co_time") or "").strip()
                    if not time_spec:
                        time_spec = (request.POST.get("co_time_preset") or "").strip()
                    radius = (request.POST.get("co_radius") or "#global").strip()
                    co_action = (request.POST.get("co_action") or "rollback").strip()
                    if co_action not in ("rollback", "restore"):
                        co_action = "rollback"
                    blocks_only = request.POST.get("co_blocks_only") == "on"
                    admin_name = str(request.user)
                    if action == "preview":
                        ok, output, cmd = run_co_preview(
                            co_action,
                            player,
                            time_spec,
                            radius=radius,
                            blocks_only=blocks_only,
                            admin_user=admin_name,
                        )
                        co_output = f"$ {cmd}\n{output}".strip()
                        if ok:
                            messages.info(request, _("CoreProtect-Vorschau ausgeführt."))
                        else:
                            messages.error(
                                request,
                                _("CoreProtect-Vorschau fehlgeschlagen: %(err)s")
                                % {"err": output},
                            )
                    else:
                        ok, output, cmd = run_co_apply(
                            co_action,
                            player,
                            time_spec,
                            radius=radius,
                            blocks_only=blocks_only,
                            admin_user=admin_name,
                        )
                        co_output = f"$ {cmd}\n{output}".strip()
                        if ok:
                            messages.success(
                                request,
                                _("CoreProtect %(action)s ausgeführt.")
                                % {"action": co_action},
                            )
                        else:
                            messages.error(
                                request,
                                _("CoreProtect fehlgeschlagen: %(err)s") % {"err": output},
                            )
                else:
                    messages.error(request, _("Unbekannte CoreProtect-Aktion."))
                    return redirect("admin:minecraft_city")
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("admin:minecraft_city")
            except Exception as exc:
                messages.error(request, _("CoreProtect-Fehler: %(err)s") % {"err": exc})
                return redirect("admin:minecraft_city")

        elif form_type == "protected_region":
            if not can_regions:
                messages.error(request, _("Keine Berechtigung für geschützte Regionen."))
                return redirect("admin:minecraft_city")
            action = (request.POST.get("action") or "").strip()
            try:
                if action == "capture_pos":
                    player = (request.POST.get("rg_player") or "").strip()
                    corner = (request.POST.get("rg_corner") or "min").strip()
                    x, y, z = fetch_player_block_pos(player)
                    min_y_default = default_region_min_y()
                    max_y_default = default_region_max_y()

                    def _keep_y(raw, default: int) -> int:
                        text = str(raw if raw is not None else "").strip()
                        if text == "":
                            return default
                        try:
                            return int(float(text))
                        except (TypeError, ValueError):
                            return default

                    region_draft = {
                        "pk": (request.POST.get("rg_pk") or "").strip(),
                        "region_id": (request.POST.get("rg_region_id") or "").strip(),
                        "display_name": (request.POST.get("rg_display_name") or "").strip(),
                        "world": (request.POST.get("rg_world") or paper_world()).strip(),
                        "min_x": request.POST.get("rg_min_x") or "",
                        "min_y": _keep_y(request.POST.get("rg_min_y"), min_y_default),
                        "min_z": request.POST.get("rg_min_z") or "",
                        "max_x": request.POST.get("rg_max_x") or "",
                        "max_y": _keep_y(request.POST.get("rg_max_y"), max_y_default),
                        "max_z": request.POST.get("rg_max_z") or "",
                        "protect_build": request.POST.get("rg_protect_build") == "on",
                        "notes": (request.POST.get("rg_notes") or "").strip(),
                        "builder_ids": [
                            int(v) for v in request.POST.getlist("rg_builders") if str(v).isdigit()
                        ],
                        "player": player,
                    }
                    # Player capture sets horizontal corners only — keep full-height Y
                    # so floor/ceiling stay protected unless the operator edits Y.
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
                    region = MinecraftProtectedRegion.objects.get(pk=pk)
                    region_draft = {
                        "pk": str(region.pk),
                        "region_id": region.region_id,
                        "display_name": region.display_name,
                        "world": region.world,
                        "min_x": region.min_x,
                        "min_y": region.min_y,
                        "min_z": region.min_z,
                        "max_x": region.max_x,
                        "max_y": region.max_y,
                        "max_z": region.max_z,
                        "protect_build": region.protect_build,
                        "notes": region.notes,
                        "builder_ids": list(region.builders.values_list("pk", flat=True)),
                        "player": "",
                    }
                    messages.info(
                        request,
                        _("Region „%(id)s“ geladen.") % {"id": region.region_id},
                    )

                elif action in {"save", "apply", "sync_members"}:
                    pk_raw = (request.POST.get("rg_pk") or "").strip()
                    region_id = normalize_region_id(request.POST.get("rg_region_id") or "")
                    world = (request.POST.get("rg_world") or paper_world()).strip() or paper_world()
                    display_name = (request.POST.get("rg_display_name") or "").strip()
                    notes = (request.POST.get("rg_notes") or "").strip()
                    protect_build = request.POST.get("rg_protect_build") == "on"
                    min_x = parse_int_coord(request.POST.get("rg_min_x"), "min_x")
                    min_y = parse_int_coord(request.POST.get("rg_min_y"), "min_y")
                    min_z = parse_int_coord(request.POST.get("rg_min_z"), "min_z")
                    max_x = parse_int_coord(request.POST.get("rg_max_x"), "max_x")
                    max_y = parse_int_coord(request.POST.get("rg_max_y"), "max_y")
                    max_z = parse_int_coord(request.POST.get("rg_max_z"), "max_z")
                    builder_ids = [
                        int(v) for v in request.POST.getlist("rg_builders") if str(v).isdigit()
                    ]

                    if pk_raw:
                        region = MinecraftProtectedRegion.objects.get(pk=int(pk_raw))
                        # region_id is the WG key — allow rename only if unique
                        if region.region_id != region_id:
                            if MinecraftProtectedRegion.objects.filter(region_id=region_id).exists():
                                raise ValueError(
                                    _("Region-ID „%(id)s“ existiert bereits.")
                                    % {"id": region_id}
                                )
                            region.region_id = region_id
                    else:
                        region, _created = MinecraftProtectedRegion.objects.get_or_create(
                            region_id=region_id,
                            defaults={
                                "min_x": min_x,
                                "min_y": min_y,
                                "min_z": min_z,
                                "max_x": max_x,
                                "max_y": max_y,
                                "max_z": max_z,
                                "world": world,
                            },
                        )

                    region.display_name = display_name
                    region.world = world
                    region.min_x = min_x
                    region.min_y = min_y
                    region.min_z = min_z
                    region.max_x = max_x
                    region.max_y = max_y
                    region.max_z = max_z
                    region.protect_build = protect_build
                    region.notes = notes
                    region.updated_by = request.user
                    region.save()
                    region.builders.set(
                        MinecraftTeamRegistration.objects.filter(
                            pk__in=builder_ids, is_active=True
                        )
                    )

                    if action == "save":
                        messages.success(
                            request,
                            _("Region „%(id)s“ gespeichert (nur Datenbank).")
                            % {"id": region.region_id},
                        )
                        return redirect("admin:minecraft_city")

                    if action == "sync_members":
                        ok, output = sync_region_members(region)
                        region_output = output
                        if ok:
                            messages.success(
                                request,
                                _("Members für „%(id)s“ synchronisiert.")
                                % {"id": region.region_id},
                            )
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
                        else:
                            messages.error(
                                request,
                                _("Anwenden fehlgeschlagen: %(err)s") % {"err": output},
                            )

                elif action == "delete":
                    pk = int(request.POST.get("rg_pk") or 0)
                    region = MinecraftProtectedRegion.objects.get(pk=pk)
                    region_id = region.region_id
                    remove_server = request.POST.get("rg_remove_server") == "on"
                    server_log = ""
                    if remove_server:
                        ok, server_log = remove_region_from_server(region)
                        region_output = server_log
                        if not ok:
                            messages.error(
                                request,
                                _("Löschen auf dem Server fehlgeschlagen: %(err)s")
                                % {"err": server_log},
                            )
                            return redirect("admin:minecraft_city")
                    region.delete()
                    messages.success(
                        request,
                        _("Region „%(id)s“ gelöscht%(suffix)s.")
                        % {
                            "id": region_id,
                            "suffix": _(" (auch WorldGuard)") if remove_server else "",
                        },
                    )
                    return redirect("admin:minecraft_city")

                else:
                    messages.error(request, _("Unbekannte Regionen-Aktion."))
                    return redirect("admin:minecraft_city")
            except MinecraftProtectedRegion.DoesNotExist:
                messages.error(request, _("Region nicht gefunden."))
                return redirect("admin:minecraft_city")
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("admin:minecraft_city")
            except Exception as exc:
                messages.error(
                    request, _("Regionen-Fehler: %(err)s") % {"err": exc}
                )
                return redirect("admin:minecraft_city")

    half = preview_half_extent(integration_config.world_border_size)
    # Refresh selection after possible border edits kept on page (status)
    if request.method != "POST" or (request.POST.get("form_type") or "") != "chunky_pregen":
        chunky_selection = border_to_chunky_selection(integration_config)
    rcon_ok, rcon_error, rcon_mode = check_connection()
    context = {
        "title": _("Stadtsteuerung"),
        "rcon_ok": rcon_ok,
        "rcon_error": rcon_error,
        "rcon_mode": rcon_mode,
        "rcon_preset_groups": presets_grouped(),
        "world_border": integration_config,
        "world_border_presets": WORLD_BORDER_SIZE_PRESETS,
        "world_border_half": half,
        "world_border_status": border_status,
        "world_border_message": border_message,
        "chunky_selection": chunky_selection,
        "chunky_progress": chunky_progress,
        "chunky_quiet_default": DEFAULT_CHUNKY_QUIET_SECONDS,
        "can_manage_coreprotect": can_coreprotect,
        "co_time_presets": TIME_PRESETS,
        "co_radii": allowed_radii(),
        "co_known_users": list_known_ms_logins() if can_coreprotect else [],
        "co_output": co_output,
        "can_manage_protected_regions": can_regions,
        "protected_regions": (
            list(
                MinecraftProtectedRegion.objects.prefetch_related("builders").all()
            )
            if can_regions
            else []
        ),
        "rg_builder_choices": (
            list(
                MinecraftTeamRegistration.objects.filter(is_active=True)
                .exclude(ms_username="")
                .select_related("group")
                .order_by("ms_username", "mc_username")
            )
            if can_regions
            else []
        ),
        "rg_draft": region_draft
        or {
            "pk": "",
            "region_id": "",
            "display_name": "",
            "world": paper_world() if can_regions else "MyCyclingCity",
            "min_x": "",
            "min_y": default_region_min_y() if can_regions else -64,
            "min_z": "",
            "max_x": "",
            "max_y": default_region_max_y() if can_regions else 320,
            "max_z": "",
            "protect_build": True,
            "notes": "",
            "builder_ids": [],
            "player": "",
        },
        "rg_output": region_output,
        "rg_paper_world": paper_world(),
        "rg_world_min_y": default_region_min_y() if can_regions else -64,
        "rg_world_max_y": default_region_max_y() if can_regions else 320,
    }
    return render(request, "admin/minecraft/minecraft_city.html", context)


@user_passes_test(can_access_minecraft_shop)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_shop_ops(request):
    from minecraft.services.shop_pricing import (
        DEFAULT_MINIMUM_VELOS,
        assign_minimum_velos,
        count_zero_price_items,
        zero_price_items_queryset,
    )

    if request.method == "POST" and request.POST.get("action") == "assign_min_velos":
        updated = assign_minimum_velos(minimum=DEFAULT_MINIMUM_VELOS)
        if updated:
            messages.success(
                request,
                _(
                    "%(count)s Shop-Artikel auf mindestens %(min)s Velo gesetzt."
                )
                % {"count": updated, "min": DEFAULT_MINIMUM_VELOS},
            )
        else:
            messages.info(
                request,
                _("Keine Artikel mit 0 Velos gefunden — Katalog ist bereits in Ordnung."),
            )
        return redirect("admin:minecraft_shop_ops")

    zero_items = list(zero_price_items_queryset()[:200])
    zero_count = count_zero_price_items()
    context = {
        "title": _("Shop-Betrieb"),
        "shop_category_count": category_count(),
        "shop_item_count": item_count(),
        "shop_catalog_preview": build_shop_catalog_payload(),
        "shop_bridge_connected": bool(get_connected_server_ids()),
        "shop_bridge_servers": get_connected_server_ids(),
        "zero_price_items": zero_items,
        "zero_price_count": zero_count,
        "zero_price_truncated": max(0, zero_count - len(zero_items)),
        "min_velos": DEFAULT_MINIMUM_VELOS,
    }
    return render(request, "admin/minecraft/minecraft_shop_ops.html", context)


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


@user_passes_test(can_access_minecraft_shop)
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


@user_passes_test(can_access_minecraft_control)
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


@user_passes_test(can_access_minecraft_control)
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


@user_passes_test(can_access_minecraft_control)
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
        "session-start",
        "session-stop",
        "session-status",
        "arena-start",
        "arena-stop",
        "arena-status",
        "ensure-objectives",
        "ws-start",
        "ws-stop",
        "ws-restart",
        "ws-status",
        "shop-check",
        "velocity-start",
        "velocity-stop",
        "velocity-status",
        "limbo-start",
        "limbo-stop",
        "limbo-status",
        "paper-start",
        "paper-stop",
        "paper-status",
    ]:
        return JsonResponse({"error": _("Invalid action")}, status=400)

    if action in SHOP_ACTIONS:
        if not user_can_access_minecraft_shop(request.user):
            return JsonResponse({"error": _("Permission denied")}, status=403)
    elif action in PROXY_ACTIONS or action in PAPER_ACTIONS:
        if not user_can_manage_minecraft_proxy(request.user):
            return JsonResponse({"error": _("Permission denied")}, status=403)
    elif not user_can_access_minecraft_control(request.user):
        return JsonResponse({"error": _("Permission denied")}, status=403)

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
        script_env = None
    elif action in PROXY_ACTIONS:
        script_path = _get_proxy_script_path()
        ws_action = None
        script_env = _proxy_script_env()
    elif action in PAPER_ACTIONS:
        script_path = _get_paper_script_path()
        ws_action = None
        script_env = _paper_script_env()
    else:
        script_path = _get_script_path()
        ws_action = None
        script_env = None

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
        if action in PAPER_ACTIONS:
            script_action = PAPER_SCRIPT_ARGS[action]
        else:
            script_action = ws_action if ws_action else action
        run_in_background = (
            (ws_action is not None and ws_action in ("start", "stop"))
            or (
                ws_action is None
                and action in (
                    "start",
                    "stop",
                    "snapshot-start",
                    "snapshot-stop",
                    "session-start",
                    "session-stop",
                    "arena-start",
                    "arena-stop",
                    "velocity-start",
                    "velocity-stop",
                    "limbo-start",
                    "limbo-stop",
                    "paper-start",
                    "paper-stop",
                )
            )
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
                        env=script_env,
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
            env=script_env,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if ws_action:
            status_info = _get_ws_status(script_path)
        elif action.startswith("snapshot-"):
            status_info = _get_snapshot_status(script_path)
        elif action.startswith("session-"):
            status_info = _get_session_status(script_path)
        elif action.startswith("arena-"):
            status_info = _get_arena_status(script_path)
        elif action.startswith("velocity-"):
            status_info = _get_velocity_status(script_path)
        elif action.startswith("limbo-"):
            status_info = _get_limbo_status(script_path)
        elif action.startswith("paper-"):
            status_info = _get_paper_status(script_path)
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
