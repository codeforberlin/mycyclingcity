# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    chunky_pregen.py
# @note    Chunky pre-generation via Paper RCON (Stadtsteuerung).

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _

from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services import rcon_client

logger = get_logger("minecraft")

DEFAULT_CHUNKY_QUIET_SECONDS = 30


def _fmt_coord(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def paper_world_name() -> str:
    return (getattr(settings, "MCC_MINECRAFT_PAPER_WORLD", None) or "MyCyclingCity").strip()


def border_size_to_chunky_radius(size: int) -> int:
    """Vanilla border diameter → Chunky radius (half edge length)."""
    return max(1, int(size) // 2)


def border_to_chunky_selection(
    config: MinecraftIntegrationConfig | None = None,
    *,
    radius_override: int | None = None,
    world: str | None = None,
) -> dict[str, Any]:
    """Map World-Border config to a Chunky square selection."""
    cfg = config or MinecraftIntegrationConfig.get_config()
    size = int(cfg.world_border_size)
    radius = int(radius_override) if radius_override is not None else border_size_to_chunky_radius(size)
    if radius < 1:
        radius = 1
    return {
        "world": (world or paper_world_name()).strip() or paper_world_name(),
        "shape": "square",
        "center_x": float(cfg.world_border_center_x),
        "center_z": float(cfg.world_border_center_z),
        "radius": radius,
        "border_size": size,
        "edge": radius * 2,
    }


def build_chunky_start_commands(
    selection: dict[str, Any],
    *,
    quiet: int = DEFAULT_CHUNKY_QUIET_SECONDS,
    use_live_worldborder: bool = False,
) -> list[str]:
    """
    Build RCON commands to configure and start Chunky.

    When use_live_worldborder is True, center/radius come from Vanilla border
    via ``chunky worldborder`` instead of the selection numbers.
    """
    quiet_sec = max(1, int(quiet))
    world = str(selection.get("world") or paper_world_name())
    commands = [
        f"chunky quiet {quiet_sec}",
        f"chunky world {world}",
        "chunky shape square",
    ]
    if use_live_worldborder:
        commands.append("chunky worldborder")
    else:
        cx = _fmt_coord(float(selection["center_x"]))
        cz = _fmt_coord(float(selection["center_z"]))
        radius = int(selection["radius"])
        commands.extend(
            [
                f"chunky center {cx} {cz}",
                f"chunky radius {radius}",
            ]
        )
    commands.append("chunky start")
    return commands


def start_pregen(
    config: MinecraftIntegrationConfig | None = None,
    *,
    radius_override: int | None = None,
    quiet: int = DEFAULT_CHUNKY_QUIET_SECONDS,
    use_live_worldborder: bool = False,
) -> tuple[bool, str, dict[str, Any]]:
    """Start Chunky pregen; returns (ok, output, selection)."""
    selection = border_to_chunky_selection(config, radius_override=radius_override)
    commands = build_chunky_start_commands(
        selection, quiet=quiet, use_live_worldborder=use_live_worldborder
    )
    logger.info("[chunky_pregen] start commands=%s selection=%s", commands, selection)
    ok, output = rcon_client.run_commands(commands)
    return ok, output, selection


def pause_pregen() -> tuple[bool, str]:
    return rcon_client.run_commands(["chunky pause"])


def continue_pregen() -> tuple[bool, str]:
    return rcon_client.run_commands(["chunky continue"])


def cancel_pregen() -> tuple[bool, str]:
    return rcon_client.run_commands(["chunky cancel"])


def read_progress() -> dict[str, Any]:
    ok, output = rcon_client.run_commands(["chunky progress"])
    return {
        "ok": ok,
        "raw": (output or "").strip(),
        "error": None if ok else (output or _("RCON fehlgeschlagen")),
    }
