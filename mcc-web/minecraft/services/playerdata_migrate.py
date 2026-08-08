# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    playerdata_migrate.py
# @note    Copy vanilla playerdata between online / offline / legacy UUIDs.

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable
from uuid import UUID

from django.conf import settings
from django.utils import timezone as dj_timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftPlayAccount
from minecraft.services.playerdata_uuid import (
    detect_playerdata_layout,
    offline_player_uuid,
    parse_ms_uuid,
    playerdata_relative_files,
    resolve_source_player_file,
    resolve_world_file,
    uuid_dashed,
)
from minecraft.services.team_registration import active_registrations

logger = get_logger("minecraft")


class DiffStatus(str, Enum):
    MISSING_BOTH = "missing_both"
    MISSING_SOURCE = "missing_source"
    MISSING_TARGET = "missing_target"
    SOURCE_NEWER = "source_newer"
    TARGET_NEWER = "target_newer"
    EQUAL = "equal"


class MigrateDirection(str, Enum):
    ONLINE_TO_OFFLINE = "online_to_offline"
    OFFLINE_TO_ONLINE = "offline_to_online"
    LEGACY_TO_TWIN = "legacy_to_twin"


@dataclass(frozen=True)
class MappedAccount:
    kind: str  # player | builder
    account_ref: str
    label: str
    ms_username: str
    legacy_name: str  # short_name / mc_username (AuthMe-era join name)
    online_uuid: UUID | None
    offline_uuid: UUID
    legacy_offline_uuid: UUID


@dataclass
class FileDiff:
    key: str
    source_path: str
    target_path: str
    source_exists: bool
    target_exists: bool
    source_mtime: float | None = None
    target_mtime: float | None = None
    status: DiffStatus = DiffStatus.MISSING_BOTH


@dataclass
class AccountDiff:
    account: MappedAccount
    files: list[FileDiff] = field(default_factory=list)
    overall: DiffStatus = DiffStatus.MISSING_BOTH
    warnings: list[str] = field(default_factory=list)


@dataclass
class MigrateResult:
    ok: bool
    direction: str
    dry_run: bool
    backup_dir: str
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def paper_world_roots() -> list[Path]:
    """Overworld + optional nether/end roots from settings."""
    primary = Path(
        getattr(
            settings,
            "MCC_MINECRAFT_PAPER_WORLD_ROOT",
            "/data/games/mcc/mc-srv/MyCyclingCity",
        )
    )
    extra = getattr(settings, "MCC_MINECRAFT_PAPER_EXTRA_WORLD_ROOTS", None) or []
    roots = [primary]
    for item in extra:
        path = Path(item)
        if path not in roots:
            roots.append(path)
    # Conventional siblings next to overworld if they exist
    for sibling in ("world_nether", "world_the_end"):
        candidate = primary.parent / sibling
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def failover_backup_root() -> Path:
    return Path(
        getattr(
            settings,
            "MCC_MINECRAFT_FAILOVER_BACKUP_ROOT",
            "/data/var/mcc/failover-backups",
        )
    )


def iter_mapped_accounts() -> list[MappedAccount]:
    rows: list[MappedAccount] = []
    for account in MinecraftPlayAccount.objects.filter(is_active=True).order_by(
        "sort_order", "short_name"
    ):
        ms = (account.ms_username or "").strip()
        if not ms:
            continue
        legacy = (account.short_name or "").strip()
        online = None
        warnings_uuid = (account.ms_uuid or "").strip()
        if warnings_uuid:
            try:
                online = parse_ms_uuid(warnings_uuid)
            except ValueError:
                online = None
        rows.append(
            MappedAccount(
                kind="player",
                account_ref=legacy,
                label=account.label,
                ms_username=ms,
                legacy_name=legacy,
                online_uuid=online,
                offline_uuid=offline_player_uuid(ms),
                legacy_offline_uuid=offline_player_uuid(legacy),
            )
        )
    for registration in active_registrations().order_by("mc_username"):
        ms = (registration.ms_username or "").strip()
        if not ms:
            continue
        legacy = (registration.mc_username or "").strip()
        online = None
        raw_uuid = (registration.ms_uuid or "").strip()
        if raw_uuid:
            try:
                online = parse_ms_uuid(raw_uuid)
            except ValueError:
                online = None
        label = registration.group.name if registration.group_id else legacy
        rows.append(
            MappedAccount(
                kind="builder",
                account_ref=legacy,
                label=label,
                ms_username=ms,
                legacy_name=legacy,
                online_uuid=online,
                offline_uuid=offline_player_uuid(ms),
                legacy_offline_uuid=offline_player_uuid(legacy),
            )
        )
    return rows


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime if path.is_file() else None
    except OSError:
        return None


def _status_for_pair(src: Path, dst: Path) -> DiffStatus:
    src_ok = src.is_file()
    dst_ok = dst.is_file()
    if not src_ok and not dst_ok:
        return DiffStatus.MISSING_BOTH
    if not src_ok:
        return DiffStatus.MISSING_SOURCE
    if not dst_ok:
        return DiffStatus.MISSING_TARGET
    sm = src.stat().st_mtime
    tm = dst.stat().st_mtime
    if abs(sm - tm) < 0.01 and src.stat().st_size == dst.stat().st_size:
        return DiffStatus.EQUAL
    if sm >= tm:
        return DiffStatus.SOURCE_NEWER
    return DiffStatus.TARGET_NEWER


def _overall_status(files: list[FileDiff]) -> DiffStatus:
    if not files:
        return DiffStatus.MISSING_BOTH
    statuses = {f.status for f in files}
    if DiffStatus.SOURCE_NEWER in statuses or DiffStatus.MISSING_TARGET in statuses:
        if any(
            f.status in {DiffStatus.SOURCE_NEWER, DiffStatus.MISSING_TARGET}
            and f.source_exists
            for f in files
        ):
            return DiffStatus.SOURCE_NEWER if DiffStatus.SOURCE_NEWER in statuses else DiffStatus.MISSING_TARGET
    if statuses == {DiffStatus.EQUAL}:
        return DiffStatus.EQUAL
    if DiffStatus.TARGET_NEWER in statuses:
        return DiffStatus.TARGET_NEWER
    if DiffStatus.MISSING_SOURCE in statuses and not any(f.source_exists for f in files):
        return DiffStatus.MISSING_SOURCE
    if DiffStatus.MISSING_BOTH in statuses and len(statuses) == 1:
        return DiffStatus.MISSING_BOTH
    # Prefer actionable source-side copy when mixed
    if any(f.source_exists for f in files):
        return DiffStatus.SOURCE_NEWER
    return DiffStatus.MISSING_SOURCE


def build_account_diff(
    account: MappedAccount,
    *,
    source_uuid: UUID,
    target_uuid: UUID,
    world_roots: Iterable[Path] | None = None,
) -> AccountDiff:
    warnings: list[str] = []
    files: list[FileDiff] = []
    roots = list(world_roots or paper_world_roots())
    for world in roots:
        layout = detect_playerdata_layout(world)
        rels = playerdata_relative_files(source_uuid, layout=layout)
        target_rels = playerdata_relative_files(target_uuid, layout=layout)
        for key, src_rel in rels.items():
            dst_rel = target_rels[key]
            src = resolve_source_player_file(world, src_rel)
            dst = resolve_world_file(world, dst_rel)
            status = _status_for_pair(src, dst)
            files.append(
                FileDiff(
                    key=f"{world.name}:{key}",
                    source_path=str(src),
                    target_path=str(dst),
                    source_exists=src.is_file(),
                    target_exists=dst.is_file(),
                    source_mtime=_mtime(src),
                    target_mtime=_mtime(dst),
                    status=status,
                )
            )
    if account.online_uuid is None:
        warnings.append("ms_uuid fehlt (Online-Seite unvollständig)")
    return AccountDiff(
        account=account,
        files=files,
        overall=_overall_status(files),
        warnings=warnings,
    )


def diff_for_direction(
    direction: MigrateDirection,
    *,
    world_roots: Iterable[Path] | None = None,
) -> list[AccountDiff]:
    roots = list(world_roots or paper_world_roots())
    out: list[AccountDiff] = []
    for account in iter_mapped_accounts():
        if direction == MigrateDirection.ONLINE_TO_OFFLINE:
            if account.online_uuid is None:
                diff = AccountDiff(
                    account=account,
                    files=[],
                    overall=DiffStatus.MISSING_SOURCE,
                    warnings=["ms_uuid fehlt — Online→Offline übersprungen"],
                )
            else:
                diff = build_account_diff(
                    account,
                    source_uuid=account.online_uuid,
                    target_uuid=account.offline_uuid,
                    world_roots=roots,
                )
        elif direction == MigrateDirection.OFFLINE_TO_ONLINE:
            if account.online_uuid is None:
                diff = AccountDiff(
                    account=account,
                    files=[],
                    overall=DiffStatus.MISSING_TARGET,
                    warnings=["ms_uuid fehlt — Offline→Online übersprungen"],
                )
            else:
                diff = build_account_diff(
                    account,
                    source_uuid=account.offline_uuid,
                    target_uuid=account.online_uuid,
                    world_roots=roots,
                )
        else:  # LEGACY_TO_TWIN
            diff = build_account_diff(
                account,
                source_uuid=account.legacy_offline_uuid,
                target_uuid=account.offline_uuid,
                world_roots=roots,
            )
            if account.legacy_name.lower() == account.ms_username.lower():
                diff.warnings.append("Legacy-Name == MS-Name (kein getrennter Legacy-Stand)")
        out.append(diff)
    return out


def _copy_file(src: Path, dst: Path, *, backup_dir: Path, dry_run: bool) -> dict:
    detail = {
        "source": str(src),
        "target": str(dst),
        "copied": False,
        "backed_up": False,
        "skipped": False,
        "reason": "",
    }
    if not src.is_file():
        detail["skipped"] = True
        detail["reason"] = "source_missing"
        return detail
    if dry_run:
        detail["reason"] = "dry_run"
        detail["copied"] = True  # would copy
        return detail
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file():
        rel_backup = backup_dir / "target_before" / dst.name
        # Keep path structure under backup
        rel_backup = backup_dir / "target_before" / Path(*dst.parts[-3:])
        rel_backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, rel_backup)
        detail["backed_up"] = True
    src_backup = backup_dir / "source" / Path(*src.parts[-3:])
    src_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, src_backup)
    shutil.copy2(src, dst)
    detail["copied"] = True
    return detail


def run_migration(
    direction: MigrateDirection,
    *,
    dry_run: bool = True,
    account_refs: set[str] | None = None,
    world_roots: Iterable[Path] | None = None,
    user=None,
) -> MigrateResult:
    """
    Copy playerdata for mapped accounts in the given direction.

    account_refs filters by account_ref (short_name / mc_username), case-insensitive.
    """
    roots = list(world_roots or paper_world_roots())
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = failover_backup_root() / ts / direction.value
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    diffs = diff_for_direction(direction, world_roots=roots)
    rows: list[dict] = []
    errors: list[str] = []
    filter_refs = {r.lower() for r in account_refs} if account_refs else None

    for diff in diffs:
        acc = diff.account
        if filter_refs is not None and acc.account_ref.lower() not in filter_refs:
            continue
        if direction in {
            MigrateDirection.ONLINE_TO_OFFLINE,
            MigrateDirection.OFFLINE_TO_ONLINE,
        } and acc.online_uuid is None:
            errors.append(f"{acc.account_ref}: ms_uuid fehlt")
            rows.append(
                {
                    "account_ref": acc.account_ref,
                    "ms_username": acc.ms_username,
                    "ok": False,
                    "detail": "ms_uuid missing",
                    "files": [],
                }
            )
            continue

        if direction == MigrateDirection.ONLINE_TO_OFFLINE:
            source_uuid, target_uuid = acc.online_uuid, acc.offline_uuid
        elif direction == MigrateDirection.OFFLINE_TO_ONLINE:
            source_uuid, target_uuid = acc.offline_uuid, acc.online_uuid
        else:
            source_uuid, target_uuid = acc.legacy_offline_uuid, acc.offline_uuid

        assert source_uuid is not None and target_uuid is not None
        if source_uuid == target_uuid:
            rows.append(
                {
                    "account_ref": acc.account_ref,
                    "ms_username": acc.ms_username,
                    "ok": True,
                    "detail": "source_equals_target",
                    "files": [],
                }
            )
            continue

        file_results = []
        account_ok = True
        for world in roots:
            layout = detect_playerdata_layout(world)
            src_rels = playerdata_relative_files(source_uuid, layout=layout)
            dst_rels = playerdata_relative_files(target_uuid, layout=layout)
            for key, src_rel in src_rels.items():
                src = resolve_source_player_file(world, src_rel)
                dst = resolve_world_file(world, dst_rels[key])
                try:
                    file_results.append(
                        _copy_file(
                            src,
                            dst,
                            backup_dir=backup_dir / acc.account_ref,
                            dry_run=dry_run,
                        )
                    )
                except OSError as exc:
                    account_ok = False
                    errors.append(f"{acc.account_ref}:{key}: {exc}")
                    file_results.append(
                        {
                            "source": str(src),
                            "target": str(dst),
                            "copied": False,
                            "error": str(exc),
                        }
                    )
        rows.append(
            {
                "account_ref": acc.account_ref,
                "kind": acc.kind,
                "ms_username": acc.ms_username,
                "source_uuid": uuid_dashed(source_uuid),
                "target_uuid": uuid_dashed(target_uuid),
                "ok": account_ok,
                "files": file_results,
            }
        )

    result = MigrateResult(
        ok=not errors,
        direction=direction.value,
        dry_run=dry_run,
        backup_dir=str(backup_dir),
        rows=rows,
        errors=errors,
    )
    if not dry_run:
        manifest_path = backup_dir / "manifest.json"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "created_at": dj_timezone.now().isoformat(),
                "direction": direction.value,
                "user": getattr(user, "username", "") if user else "",
                "rows": rows,
                "errors": errors,
            }
            manifest_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("[playerdata_migrate] manifest write failed: %s", exc)
            result.errors.append(f"manifest: {exc}")
            result.ok = False

    logger.info(
        "[playerdata_migrate] direction=%s dry_run=%s accounts=%s errors=%s backup=%s",
        direction.value,
        dry_run,
        len(rows),
        len(errors),
        result.backup_dir,
    )
    return result


def account_diff_to_dict(diff: AccountDiff) -> dict:
    acc = diff.account
    return {
        "kind": acc.kind,
        "account_ref": acc.account_ref,
        "label": acc.label,
        "ms_username": acc.ms_username,
        "legacy_name": acc.legacy_name,
        "online_uuid": uuid_dashed(acc.online_uuid) if acc.online_uuid else "",
        "offline_uuid": uuid_dashed(acc.offline_uuid),
        "legacy_offline_uuid": uuid_dashed(acc.legacy_offline_uuid),
        "overall": diff.overall.value,
        "warnings": list(diff.warnings),
        "files": [asdict(f) | {"status": f.status.value} for f in diff.files],
    }
