# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re

from django.conf import settings
from django.utils.translation import gettext_lazy as _


MAX_COMMANDS = 50
MAX_COMMAND_LENGTH = 256

DEPRECATED_GAMERULE_HINTS: dict[str, str] = {
    "doDaylightCycle": "advance_time",
    "doWeatherCycle": "advance_weather",
    "mobGriefing": "mob_griefing",
    "doMobSpawning": "spawn_monsters",
    "doFireTick": "fire_spread_radius_around_player",
    "keepInventory": "keep_inventory",
    "doTileDrops": "block_drops",
    "naturalRegeneration": "natural_health_regeneration",
    "doEntityDrops": "entity_drops",
    "doMobLoot": "mob_drops",
}

# WorldGuard console/RCON has no player world context unless -w is set (or WorldEdit
# previously selected a world on the same console session).
_RG_COMMAND_RE = re.compile(r"^rg\s+", re.IGNORECASE)
_RG_HAS_WORLD_RE = re.compile(r"(?:^|\s)-w\s+\S+", re.IGNORECASE)


def paper_world_for_presets() -> str:
    return (getattr(settings, "MCC_MINECRAFT_PAPER_WORLD", None) or "MyCyclingCity").strip()


def ensure_worldguard_world_flag(command: str, *, world: str | None = None) -> str:
    """
    Inject ``-w <paper_world>`` into WorldGuard ``rg …`` commands that lack it.

    Without ``-w``, RCON typically returns: "Please specify the world with -w world_name."
    Preferred form matches Stadtsteuerung: ``rg <sub> -w <world> …``.
    """
    text = (command or "").strip()
    if not text or not _RG_COMMAND_RE.match(text):
        return command
    if _RG_HAS_WORLD_RE.search(text):
        return command
    world_name = (world or paper_world_for_presets()).strip()
    if not world_name:
        return command
    # rg <subcommand> rest  →  rg <subcommand> -w WORLD rest
    match = re.match(r"^(rg\s+\S+)(\s+)(.+)$", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} -w {world_name} {match.group(3)}"
    # rg <subcommand> (no args)
    match = re.match(r"^(rg\s+\S+)\s*$", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} -w {world_name}"
    return f"rg -w {world_name} {text[2:].strip()}"


def normalize_preset_commands(commands: list[str] | None) -> list[str]:
    """Map legacy camelCase gamerule names to Minecraft 1.21.11+ snake_case."""
    normalized: list[str] = []
    for command in commands or []:
        updated = command
        for deprecated, modern in DEPRECATED_GAMERULE_HINTS.items():
            updated = re.sub(rf"\b{re.escape(deprecated)}\b", modern, updated)
        updated = ensure_worldguard_world_flag(updated)
        normalized.append(updated)
    return normalized


def commands_to_text(commands: list[str] | None) -> str:
    return "\n".join(commands or [])


def parse_commands_text(text: str) -> list[str]:
    """Parse one RCON command per line from admin textarea input."""
    commands: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            line = line[1:].strip()
        if line:
            commands.append(line)
    return commands


def validate_commands(commands: list[str]) -> tuple[list[str], list[str]]:
    """
    Validate command list.

    Returns (errors, warnings). Errors block save; warnings are shown in the form.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not commands:
        errors.append(str(_("Mindestens ein RCON-Befehl ist erforderlich.")))
        return errors, warnings

    if len(commands) > MAX_COMMANDS:
        errors.append(
            str(_("Maximal %(max)s Befehle erlaubt.") % {"max": MAX_COMMANDS})
        )

    for index, command in enumerate(commands, start=1):
        if len(command) > MAX_COMMAND_LENGTH:
            errors.append(
                str(_("Zeile %(line)s: Befehl zu lang (max. %(max)s Zeichen)."))
                % {"line": index, "max": MAX_COMMAND_LENGTH}
            )

        for deprecated, modern in DEPRECATED_GAMERULE_HINTS.items():
            if re.search(rf"\b{re.escape(deprecated)}\b", command):
                warnings.append(
                    str(
                        _("Zeile %(line)s: „%(old)s“ ist veraltet — Vorschlag: „%(new)s“.")
                        % {"line": index, "old": deprecated, "new": modern}
                    )
                )

    return errors, warnings
