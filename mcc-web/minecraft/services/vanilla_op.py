# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    vanilla_op.py
# @note    Vanilla Minecraft /op and /deop via RCON; list from ops.json (server truth).

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from mcrcon import MCRconException

from config.logger_utils import get_logger
from minecraft.models import MinecraftVanillaOpLog
from minecraft.services import rcon_client

logger = get_logger("minecraft")

# Short in-process cache so Admin polls don't hammer the filesystem.
_CACHE_TTL_SEC = 20.0
_ops_cache: tuple[float, list["VanillaOperator"]] | None = None


class VanillaOpError(Exception):
    """Raised when op/deop or ops listing fails."""


@dataclass(frozen=True)
class VanillaOperator:
    name: str
    uuid: str = ""
    level: int | None = None
    bypasses_player_limit: bool | None = None

    @property
    def name_key(self) -> str:
        return (self.name or "").strip().lower()


def _paper_dir() -> Path:
    raw = getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    return Path(raw)


def ops_json_path() -> Path:
    return _paper_dir() / "ops.json"


def invalidate_ops_cache() -> None:
    global _ops_cache
    _ops_cache = None


def _parse_ops_entries(raw: Any) -> list[VanillaOperator]:
    if not isinstance(raw, list):
        return []
    out: list[VanillaOperator] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        level_raw = entry.get("level")
        try:
            level = int(level_raw) if level_raw is not None else None
        except (TypeError, ValueError):
            level = None
        bypass = entry.get("bypassesPlayerLimit")
        if bypass is not None:
            bypass = bool(bypass)
        out.append(
            VanillaOperator(
                name=name,
                uuid=str(entry.get("uuid") or "").strip(),
                level=level,
                bypasses_player_limit=bypass,
            )
        )
    out.sort(key=lambda o: o.name_key)
    return out


def read_ops_from_file(path: Path | None = None) -> list[VanillaOperator]:
    """Read Vanilla operators from ops.json (Paper server root)."""
    target = path or ops_json_path()
    if not target.is_file():
        raise VanillaOpError(
            f"ops.json nicht gefunden ({target}). "
            "MCC_MINECRAFT_PAPER_DIR prüfen bzw. Server starten."
        )
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VanillaOpError(f"ops.json konnte nicht gelesen werden: {exc}") from exc
    return _parse_ops_entries(data)


def list_operators(*, use_cache: bool = True) -> list[VanillaOperator]:
    """
    Current Vanilla operators.

    Source of truth is ops.json (Vanilla has no RCON list-ops command).
    After op/deop the server rewrites the file; cache is short-lived.
    """
    global _ops_cache
    now = time.monotonic()
    if use_cache and _ops_cache is not None:
        cached_at, cached = _ops_cache
        if (now - cached_at) < _CACHE_TTL_SEC:
            return list(cached)
    ops = read_ops_from_file()
    _ops_cache = (now, ops)
    return list(ops)


def operator_name_set(ops: list[VanillaOperator] | None = None) -> set[str]:
    items = ops if ops is not None else list_operators()
    return {o.name_key for o in items}


def is_operator(player_name: str, *, ops: list[VanillaOperator] | None = None) -> bool:
    key = (player_name or "").strip().lower()
    if not key:
        return False
    return key in operator_name_set(ops)


def _validate_player_name(player_name: str) -> str:
    name = (player_name or "").strip()
    if not name:
        raise VanillaOpError("Spielername fehlt.")
    if len(name) > 32:
        raise VanillaOpError("Spielername zu lang (max. 32).")
    if any(ch.isspace() for ch in name):
        raise VanillaOpError("Spielername darf keine Leerzeichen enthalten.")
    # Reject RCON injection / path tricks
    if any(ch in name for ch in ('"', "'", ";", "\n", "\r", "\\")):
        raise VanillaOpError("Spielername enthält ungültige Zeichen.")
    return name


def _rcon_op_command(action: str, player_name: str) -> str:
    name = _validate_player_name(player_name)
    if action not in (MinecraftVanillaOpLog.ACTION_OP, MinecraftVanillaOpLog.ACTION_DEOP):
        raise VanillaOpError(f"Unbekannte Aktion: {action}")
    try:
        response = rcon_client.run_command(f"{action} {name}")
    except MCRconException as exc:
        raise VanillaOpError(str(exc)) from exc
    return (response or "").strip()


def grant_op(
    player_name: str,
    *,
    user=None,
    account_type: str = "",
    account_ref: str = "",
) -> tuple[bool, str]:
    """Run Vanilla /op <player> and audit the attempt."""
    name = _validate_player_name(player_name)
    ok = False
    detail = ""
    try:
        detail = _rcon_op_command(MinecraftVanillaOpLog.ACTION_OP, name)
        ok = True
        invalidate_ops_cache()
    except VanillaOpError as exc:
        detail = str(exc)
        ok = False
    MinecraftVanillaOpLog.objects.create(
        action=MinecraftVanillaOpLog.ACTION_OP,
        player_name=name,
        account_type=(account_type or "")[:16],
        account_ref=(account_ref or "")[:64],
        ok=ok,
        detail=detail[:2000],
        created_by=user if getattr(user, "pk", None) else None,
    )
    if not ok:
        raise VanillaOpError(detail)
    logger.info("[vanilla_op] op %s by user=%s detail=%r", name, getattr(user, "pk", None), detail)
    return True, detail


def revoke_op(
    player_name: str,
    *,
    user=None,
    account_type: str = "",
    account_ref: str = "",
) -> tuple[bool, str]:
    """Run Vanilla /deop <player> and audit the attempt."""
    name = _validate_player_name(player_name)
    ok = False
    detail = ""
    try:
        detail = _rcon_op_command(MinecraftVanillaOpLog.ACTION_DEOP, name)
        ok = True
        invalidate_ops_cache()
    except VanillaOpError as exc:
        detail = str(exc)
        ok = False
    MinecraftVanillaOpLog.objects.create(
        action=MinecraftVanillaOpLog.ACTION_DEOP,
        player_name=name,
        account_type=(account_type or "")[:16],
        account_ref=(account_ref or "")[:64],
        ok=ok,
        detail=detail[:2000],
        created_by=user if getattr(user, "pk", None) else None,
    )
    if not ok:
        raise VanillaOpError(detail)
    logger.info(
        "[vanilla_op] deop %s by user=%s detail=%r", name, getattr(user, "pk", None), detail
    )
    return True, detail
