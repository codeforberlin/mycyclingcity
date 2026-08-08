# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    world_border.py
# @note    Vanilla worldborder apply/read via Paper RCON for Stadtsteuerung.

from __future__ import annotations

import re
from typing import Any

from django.utils.translation import gettext as _

from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services import rcon_client

logger = get_logger("minecraft")

# Vanilla maximum world border diameter (effectively "disabled").
WORLD_BORDER_DISABLED_SIZE = 59_999_968
WORLD_BORDER_SIZE_PRESETS = (500, 1000, 2000)

_GET_SIZE_RE = re.compile(
    r"(?:The world border is currently|world border is|border is(?: currently)?)\s+"
    r"([\d.]+)\s*(?:blocks?\s*wide)?",
    re.IGNORECASE,
)
_GET_SIZE_FALLBACK_RE = re.compile(r"([\d.]+)")
_SPAWN_X_RE = re.compile(r"^spawn-x\s*=\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_SPAWN_Y_RE = re.compile(r"^spawn-y\s*=\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_SPAWN_Z_RE = re.compile(r"^spawn-z\s*=\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def _fmt_coord(value: float) -> str:
    # Prefer compact integers when whole numbers; otherwise trim float noise.
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def build_world_border_commands(
    *,
    center_x: float,
    center_z: float,
    size: int,
    warning_distance: int = 5,
    damage_amount: float = 0.2,
    enabled: bool = True,
) -> list[str]:
    """Build RCON commands to set (or disable) the vanilla world border."""
    diameter = int(size) if enabled else WORLD_BORDER_DISABLED_SIZE
    if diameter < 1:
        diameter = 1
    if diameter > WORLD_BORDER_DISABLED_SIZE:
        diameter = WORLD_BORDER_DISABLED_SIZE
    warn = max(0, int(warning_distance))
    damage = max(0.0, float(damage_amount))
    return [
        f"worldborder center {_fmt_coord(center_x)} {_fmt_coord(center_z)}",
        f"worldborder set {diameter}",
        f"worldborder warning distance {warn}",
        f"worldborder damage amount {damage}",
    ]


def build_world_border_commands_from_config(
    config: MinecraftIntegrationConfig | None = None,
    *,
    enabled: bool | None = None,
    size: int | None = None,
) -> list[str]:
    cfg = config or MinecraftIntegrationConfig.get_config()
    return build_world_border_commands(
        center_x=float(cfg.world_border_center_x),
        center_z=float(cfg.world_border_center_z),
        size=int(size if size is not None else cfg.world_border_size),
        warning_distance=int(cfg.world_border_warning_distance),
        damage_amount=float(cfg.world_border_damage_amount),
        enabled=bool(cfg.world_border_enabled if enabled is None else enabled),
    )


def apply_world_border(
    config: MinecraftIntegrationConfig | None = None,
    *,
    enabled: bool | None = None,
    size: int | None = None,
) -> tuple[bool, str]:
    """Apply configured world border via RCON."""
    commands = build_world_border_commands_from_config(
        config, enabled=enabled, size=size
    )
    logger.info("[world_border] applying commands=%s", commands)
    return rcon_client.run_commands(commands)


def parse_world_border_get(output: str) -> dict[str, Any]:
    """Parse `worldborder get` RCON output into a status dict."""
    text = (output or "").strip()
    size = None
    match = _GET_SIZE_RE.search(text)
    if match:
        try:
            size = float(match.group(1))
        except ValueError:
            size = None
    if size is None:
        # Fallback: first number in the response
        fallback = _GET_SIZE_FALLBACK_RE.search(text)
        if fallback:
            try:
                size = float(fallback.group(1))
            except ValueError:
                size = None
    enabled = None
    if size is not None:
        enabled = size < (WORLD_BORDER_DISABLED_SIZE * 0.99)
    return {
        "raw": text,
        "size": size,
        "enabled": enabled,
    }


def read_world_border_status() -> dict[str, Any]:
    """Query current world border size from Paper."""
    ok, output = rcon_client.run_commands(["worldborder get"])
    parsed = parse_world_border_get(output)
    parsed["ok"] = ok
    if not ok:
        parsed["error"] = output or _("RCON fehlgeschlagen")
    return parsed


def preview_half_extent(size: int) -> float:
    """Half of the square edge length (± from center)."""
    return max(0, int(size)) / 2.0


def read_spawn_from_server_properties(paper_dir: str | None = None) -> tuple[float, float] | None:
    """Read spawn-x/spawn-z from Paper server.properties, if present."""
    xyz = read_world_spawn_xyz(paper_dir)
    if xyz is None:
        return None
    return xyz[0], xyz[2]


def read_world_spawn_xyz(paper_dir: str | None = None) -> tuple[float, float, float] | None:
    """Read spawn-x/y/z from Paper server.properties (y optional, default 64)."""
    from django.conf import settings
    from pathlib import Path

    root = paper_dir or getattr(settings, "MCC_MINECRAFT_PAPER_DIR", "") or ""
    props = Path(root) / "server.properties"
    if not props.is_file():
        return None
    try:
        text = props.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    mx = _SPAWN_X_RE.search(text)
    mz = _SPAWN_Z_RE.search(text)
    if not mx or not mz:
        return None
    try:
        x = float(mx.group(1).strip())
        z = float(mz.group(1).strip())
        my = _SPAWN_Y_RE.search(text)
        y = float(my.group(1).strip()) if my else 64.0
        return x, y, z
    except ValueError:
        return None
