# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    views_deployment.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Views for deployment and backup management.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from pathlib import Path
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# kind -> (subdir relative to backups root, glob patterns, allowed suffixes)
BACKUP_KINDS = {
    "database": {
        "subdir": "database",
        "patterns": ("db_backup_*.sqlite3", "db_backup_*.db", "*.sqlite3", "*.db", "*.sqlite3.gz", "*.db.gz"),
        "suffixes": (".sqlite3", ".db", ".sqlite3.gz", ".db.gz"),
        "label": _("Datenbank-Backups"),
    },
    "minecraft": {
        "subdir": "minecraft",
        "patterns": ("mc_world_*.tar.gz", "*.tar.gz"),
        "suffixes": (".tar.gz",),
        "label": _("Minecraft Welt-Backups"),
    },
    "luanti": {
        "subdir": "luanti",
        "patterns": ("luanti_world_*.tar.gz", "*.tar.gz"),
        "suffixes": (".tar.gz",),
        "label": _("Luanti Welt-Backups"),
    },
}


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


def get_backups_root() -> Path:
    """
    Backup root: DATA_DIR/backups (prod: /data/var/mcc/backups).
    Falls back to BASE_DIR/data/backups when DATA_DIR is unavailable.
    """
    data_dir = getattr(settings, "DATA_DIR", None)
    if data_dir is not None:
        return Path(data_dir) / "backups"
    if "/data/appl/mcc" in str(settings.BASE_DIR) or os.environ.get("MCC_ENV") == "production":
        return Path("/data/var/mcc/backups")
    return Path(settings.BASE_DIR) / "data" / "backups"


def get_kind_dir(kind: str) -> Path:
    """Resolved directory for a backup kind (creates if missing)."""
    meta = BACKUP_KINDS.get(kind)
    if meta is None:
        raise KeyError(kind)
    root = get_backups_root()
    sub = meta["subdir"]
    target = root / sub if sub else root
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Cannot create backup dir %s: %s", target, exc)
    return target


def _is_allowed_backup_name(name: str, suffixes: tuple[str, ...]) -> bool:
    if name.endswith("-wal") or name.endswith("-shm"):
        return False
    if "/" in name or "\\" in name or name in (".", ".."):
        return False
    lower = name.lower()
    return any(lower.endswith(suf) for suf in suffixes)


def list_kind_backups(kind: str) -> list[dict]:
    """List backup files for one kind, newest first."""
    meta = BACKUP_KINDS[kind]
    backups_dir = get_kind_dir(kind)
    found: dict[str, Path] = {}
    try:
        if not backups_dir.is_dir():
            logger.warning("Backup dir missing or not a directory: %s", backups_dir)
            return []
        for pattern in meta["patterns"]:
            for path in backups_dir.glob(pattern):
                try:
                    if path.is_file() and _is_allowed_backup_name(path.name, meta["suffixes"]):
                        found[path.name] = path
                except OSError:
                    continue
        # Legacy: DB files previously lived directly under backups/
        if kind == "database":
            root = get_backups_root()
            if root != backups_dir and root.is_dir():
                for pattern in meta["patterns"]:
                    for path in root.glob(pattern):
                        try:
                            if path.is_file() and _is_allowed_backup_name(
                                path.name, meta["suffixes"]
                            ):
                                # Prefer files already under database/; skip if name clash
                                found.setdefault(path.name, path)
                        except OSError:
                            continue
    except OSError as exc:
        logger.exception("Failed listing backups in %s: %s", backups_dir, exc)
        return []

    rows = []
    for path in sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
            rows.append(
                {
                    "filename": path.name,
                    "size_mb": round(stat.st_size / 1024 / 1024, 3),
                    "size_bytes": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_mtime),
                    "created_ts": int(stat.st_mtime),
                    "path": str(path),
                    "kind": kind,
                }
            )
        except (OSError, ValueError):
            continue
    return rows


@user_passes_test(is_superuser)
@staff_member_required
def backup_control(request):
    """Backup management page (database + Minecraft + Luanti archives)."""
    backups_dir = get_backups_root()
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    from django.urls import reverse

    database_backups = list_kind_backups("database")
    minecraft_backups = list_kind_backups("minecraft")
    luanti_backups = list_kind_backups("luanti")

    def _catalog_rows(rows):
        return [
            {
                "filename": r["filename"],
                "size_mb": r["size_mb"],
                "size_bytes": r["size_bytes"],
                "created_ts": r["created_ts"],
                "path": r["path"],
                "kind": r["kind"],
            }
            for r in rows
        ]

    download_urls = {}
    for kind in ("database", "minecraft", "luanti"):
        # Placeholder filename replaced client-side
        download_urls[kind] = reverse(
            "admin:mgmt_backup_download",
            kwargs={"kind": kind, "filename": "__FILE__"},
        )

    context = {
        "title": _("Backup Management"),
        "backups_dir": str(backups_dir),
        "database_dir": str(get_kind_dir("database")),
        "minecraft_dir": str(get_kind_dir("minecraft")),
        "luanti_dir": str(get_kind_dir("luanti")),
        "database_backups": database_backups,
        "minecraft_backups": minecraft_backups,
        "luanti_backups": luanti_backups,
        "database_count": len(database_backups),
        "minecraft_count": len(minecraft_backups),
        "luanti_count": len(luanti_backups),
        "backup_catalog": {
            "database": _catalog_rows(database_backups),
            "minecraft": _catalog_rows(minecraft_backups),
            "luanti": _catalog_rows(luanti_backups),
        },
        "download_urls": download_urls,
        "backups": database_backups,
    }
    return render(request, "admin/mgmt/backup_control.html", context)


def resolve_backup_file(kind: str, filename: str) -> Path:
    """
    Resolve a single backup file under the kind directory (or legacy DB root).
    Raises ValueError on invalid kind/name/path.
    """
    kind = (kind or "database").strip().lower()
    if kind not in BACKUP_KINDS:
        raise ValueError("unknown_kind")
    meta = BACKUP_KINDS[kind]
    if not _is_allowed_backup_name(filename, meta["suffixes"]):
        raise ValueError("invalid_filename")

    backups_dir = get_kind_dir(kind)
    backup_path = backups_dir / filename
    if (
        kind == "database"
        and (not backup_path.exists())
        and _is_allowed_backup_name(filename, meta["suffixes"])
    ):
        legacy = get_backups_root() / filename
        if legacy.is_file():
            backup_path = legacy
            backups_dir = get_backups_root()

    try:
        backup_path_resolved = backup_path.resolve()
        backups_dir_resolved = backups_dir.resolve()
        if not str(backup_path_resolved).startswith(str(backups_dir_resolved)):
            raise ValueError("path_escape")
    except (ValueError, OSError) as exc:
        raise ValueError("invalid_path") from exc

    if not backup_path.exists() or not backup_path.is_file():
        raise ValueError("not_found")
    return backup_path


@user_passes_test(is_superuser)
@staff_member_required
def create_backup(request):
    """Create a database backup."""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    try:
        from utils.backup_database import create_backup as backup_func, get_database_path

        project_dir = Path(settings.BASE_DIR)
        db_path = get_database_path(project_dir)
        if not db_path:
            return JsonResponse(
                {
                    "success": False,
                    "error": _("Could not determine database path"),
                },
                status=500,
            )

        backup_dir = get_kind_dir("database")
        backup_path = backup_func(db_path, backup_dir, compress=False)

        if not backup_path:
            return JsonResponse(
                {
                    "success": False,
                    "error": _("Failed to create backup"),
                },
                status=500,
            )

        return JsonResponse(
            {
                "success": True,
                "message": _("Backup created successfully"),
                "backup_path": str(backup_path),
            }
        )
    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )


@user_passes_test(is_superuser)
@staff_member_required
def download_backup(request, filename, kind="database"):
    """Download a backup file (database | minecraft | luanti)."""
    from django.http import FileResponse, Http404
    from urllib.parse import quote

    try:
        backup_path = resolve_backup_file(kind, filename)
    except ValueError:
        raise Http404("Backup file not found")

    try:
        file_handle = open(backup_path, "rb")
        response = FileResponse(
            file_handle,
            content_type="application/octet-stream",
            as_attachment=True,
            filename=backup_path.name,
        )
        encoded_filename = quote(backup_path.name)
        response["Content-Disposition"] = (
            f'attachment; filename="{encoded_filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        )
        return response
    except (IOError, OSError) as e:
        raise Http404(f"Backup file could not be opened: {e}")


@user_passes_test(is_superuser)
@staff_member_required
def delete_backup(request):
    """Delete one backup archive (JSON POST: kind + filename)."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Only POST allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        payload = {
            "kind": request.POST.get("kind"),
            "filename": request.POST.get("filename"),
        }

    kind = str(payload.get("kind") or "").strip()
    filename = str(payload.get("filename") or "").strip()
    if not kind or not filename:
        return JsonResponse(
            {"success": False, "error": _("kind und filename erforderlich")},
            status=400,
        )

    try:
        backup_path = resolve_backup_file(kind, filename)
    except ValueError as exc:
        code = str(exc) or "not_found"
        return JsonResponse(
            {"success": False, "error": _("Datei nicht gefunden (%(code)s)") % {"code": code}},
            status=404,
        )

    deleted = [backup_path.name]
    try:
        backup_path.unlink()
        # Companion SQLite sidecar files (legacy create_backup copies).
        if kind == "database":
            for suffix in ("-wal", "-shm"):
                side = Path(str(backup_path) + suffix)
                if side.is_file():
                    try:
                        side_resolved = side.resolve()
                        parent_resolved = backup_path.parent.resolve()
                        if str(side_resolved).startswith(str(parent_resolved)):
                            side.unlink()
                            deleted.append(side.name)
                    except OSError:
                        logger.warning("Could not delete sidecar %s", side)
    except OSError as exc:
        logger.exception("Backup delete failed: %s", backup_path)
        return JsonResponse(
            {"success": False, "error": str(exc)},
            status=500,
        )

    logger.info(
        "Backup deleted by user=%s kind=%s file=%s",
        getattr(request.user, "pk", None),
        kind,
        filename,
    )
    return JsonResponse(
        {
            "success": True,
            "message": _("Backup gelöscht"),
            "deleted": deleted,
            "kind": kind,
            "filename": filename,
        }
    )
