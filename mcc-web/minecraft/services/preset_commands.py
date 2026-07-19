# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re

from django.utils.translation import gettext_lazy as _


MAX_COMMANDS = 50
MAX_COMMAND_LENGTH = 256

DEPRECATED_GAMERULE_HINTS: dict[str, str] = {
    "mobGriefing": "mob_griefing",
    "doMobSpawning": "spawn_monsters",
    "doFireTick": "fire_spread_radius_around_player",
    "keepInventory": "keep_inventory",
    "doTileDrops": "block_drops",
    "naturalRegeneration": "natural_health_regeneration",
    "doEntityDrops": "entity_drops",
    "doMobLoot": "mob_drops",
}


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
