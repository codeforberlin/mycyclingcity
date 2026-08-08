# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    auth_failover_views.py
# @note    Admin GUI for Auth-Failover playerdata migration and ops mode.

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig, MinecraftPlayerdataTransferLog
from minecraft.services.playerdata_migrate import (
    MigrateDirection,
    account_diff_to_dict,
    diff_for_direction,
    run_migration,
)
from minecraft.services.preset_permissions import user_can_manage_auth_failover

logger = get_logger("minecraft")

VALID_DIRECTIONS = {d.value for d in MigrateDirection}
VALID_MODES = {
    MinecraftIntegrationConfig.AUTH_OPS_ONLINE,
    MinecraftIntegrationConfig.AUTH_OPS_FAILOVER,
    MinecraftIntegrationConfig.AUTH_OPS_RECOVERY,
}


def can_manage_auth_failover(user):
    return user_can_manage_auth_failover(user)


def _failover_script_path() -> Path:
    return Path(settings.BASE_DIR) / "scripts" / "minecraft_auth_failover.sh"


def _run_failover_script(*args: str) -> tuple[bool, str]:
    script = _failover_script_path()
    if not script.is_file():
        return False, f"Script fehlt: {script}"
    try:
        completed = subprocess.run(
            [str(script), *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, out.strip() or f"exit={completed.returncode}"


def _active_session_count() -> int:
    from minecraft.models import MCSession

    return MCSession.objects.filter(status=MCSession.STATUS_ACTIVE).count()


@user_passes_test(can_manage_auth_failover)
@staff_member_required
@require_http_methods(["GET", "POST"])
def minecraft_auth_failover(request):
    config = MinecraftIntegrationConfig.get_config()
    direction_param = (
        request.POST.get("direction")
        or request.GET.get("direction")
        or MigrateDirection.LEGACY_TO_TWIN.value
    )
    if direction_param not in VALID_DIRECTIONS:
        direction_param = MigrateDirection.LEGACY_TO_TWIN.value
    direction = MigrateDirection(direction_param)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        selected = {
            (name or "").strip()
            for name in request.POST.getlist("account_ref")
            if (name or "").strip()
        }

        if action == "set_mode":
            mode = (request.POST.get("auth_ops_mode") or "").strip()
            if mode not in VALID_MODES:
                messages.error(request, _("Ungültiger Auth-Modus."))
            else:
                config.auth_ops_mode = mode
                if mode == MinecraftIntegrationConfig.AUTH_OPS_FAILOVER:
                    config.auth_failover_at = timezone.now()
                if mode == MinecraftIntegrationConfig.AUTH_OPS_ONLINE:
                    config.auth_failback_at = timezone.now()
                config.updated_by = request.user
                config.save()
                messages.success(
                    request,
                    _("Auth-Betriebsmodus gesetzt: %(mode)s") % {"mode": mode},
                )
            return redirect("admin:minecraft_auth_failover")

        if action == "velocity_online_mode":
            flag = (request.POST.get("online_mode") or "").strip().lower()
            if flag not in {"true", "false"}:
                messages.error(request, _("online_mode muss true oder false sein."))
            else:
                ok, out = _run_failover_script("set-online-mode", flag)
                if ok:
                    messages.success(
                        request,
                        _("Velocity online-mode=%(flag)s gesetzt.") % {"flag": flag},
                    )
                    ok2, out2 = _run_failover_script("restart-velocity")
                    if ok2:
                        messages.info(request, _("Velocity neu gestartet."))
                    else:
                        messages.warning(
                            request,
                            _("online-mode gesetzt, Restart fehlgeschlagen: %(err)s")
                            % {"err": out2[:500]},
                        )
                else:
                    messages.error(
                        request,
                        _("Velocity-Umschaltung fehlgeschlagen: %(err)s")
                        % {"err": out[:500]},
                    )
            return redirect(
                f"{request.path}?direction={direction.value}"
            )

        if action in {"migrate_dry", "migrate_run"}:
            dry_run = action == "migrate_dry"
            active_n = _active_session_count()
            if not dry_run and active_n > 0:
                messages.error(
                    request,
                    _(
                        "Es sind noch %(n)s aktive Session(s). "
                        "Bitte zuerst alle kicken, dann erneut ausführen."
                    )
                    % {"n": active_n},
                )
                return redirect(f"{request.path}?direction={direction.value}")

            result = run_migration(
                direction,
                dry_run=dry_run,
                account_refs=selected or None,
                user=request.user,
            )
            MinecraftPlayerdataTransferLog.objects.create(
                direction=direction.value,
                dry_run=dry_run,
                ok=result.ok,
                backup_dir=result.backup_dir,
                detail=json.dumps(
                    {"rows": result.rows, "errors": result.errors},
                    ensure_ascii=False,
                )[:20000],
                created_by=request.user,
            )
            if not dry_run and result.backup_dir:
                config.auth_last_snapshot_dir = result.backup_dir
                config.updated_by = request.user
                config.save(update_fields=["auth_last_snapshot_dir", "updated_by", "updated_at"])

            copied_accounts = sum(1 for r in result.rows if r.get("ok"))
            label = _("Dry-Run") if dry_run else _("Migration")
            if result.ok:
                messages.success(
                    request,
                    _("%(label)s OK: %(n)s Account(s). Backup: %(path)s")
                    % {
                        "label": label,
                        "n": copied_accounts,
                        "path": result.backup_dir or "—",
                    },
                )
            else:
                messages.warning(
                    request,
                    _("%(label)s mit Fehlern (%(n)s Accounts, %(e)s Fehler).")
                    % {
                        "label": label,
                        "n": copied_accounts,
                        "e": len(result.errors),
                    },
                )
                for err in result.errors[:5]:
                    messages.error(request, err)
            return redirect(f"{request.path}?direction={direction.value}")

        messages.error(request, _("Unbekannte Aktion."))
        return redirect("admin:minecraft_auth_failover")

    diffs = [account_diff_to_dict(d) for d in diff_for_direction(direction)]
    script_ok, velocity_status = _run_failover_script("status")
    recent_logs = list(
        MinecraftPlayerdataTransferLog.objects.all()[:8]
    )

    return render(
        request,
        "admin/minecraft/minecraft_auth_failover.html",
        {
            "title": _("Auth-Failover / Playerdata"),
            "config": config,
            "direction": direction.value,
            "directions": [
                (MigrateDirection.LEGACY_TO_TWIN.value, _("Legacy Offline → MS-Offline-Twin")),
                (MigrateDirection.ONLINE_TO_OFFLINE.value, _("Online → Offline-Twin")),
                (MigrateDirection.OFFLINE_TO_ONLINE.value, _("Offline-Twin → Online")),
            ],
            "diffs": diffs,
            "active_session_count": _active_session_count(),
            "world_root": getattr(
                settings,
                "MCC_MINECRAFT_PAPER_WORLD_ROOT",
                "/data/games/mcc/mc-srv/MyCyclingCity",
            ),
            "backup_root": getattr(
                settings,
                "MCC_MINECRAFT_FAILOVER_BACKUP_ROOT",
                "/data/var/mcc/failover-backups",
            ),
            "velocity_status_ok": script_ok,
            "velocity_status": velocity_status,
            "recent_logs": recent_logs,
            "mode_choices": MinecraftIntegrationConfig.AUTH_OPS_MODE_CHOICES,
        },
    )
