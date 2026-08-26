# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Seed / fallback definitions for Luanti city presets.
# Runtime execution always prefers DB rows edited in the Admin GUI.

from __future__ import annotations

# Minecraft-style ticks: 0=midnight, 6000=noon, 18000=night. time_speed 0 freezes cycle.

DAYTIME_STEPS: list[dict] = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "set_time_speed", "value": 72},
    {"op": "chat", "message": "Es ist Tag."},
]

# Noon locked: stays bright (no day→night progression).
NOON_LOCKED_STEPS: list[dict] = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "set_time_speed", "value": 0},
    {"op": "chat", "message": "Mittag — Zeit eingefroren, bleibt hell."},
]

NIGHTTIME_STEPS: list[dict] = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 0},
    {"op": "set_time_speed", "value": 72},
    {"op": "chat", "message": "Es ist Nacht."},
]

# Same world state as daytime — runs automatically on session start.
SESSION_BOOTSTRAP_STEPS: list[dict] = list(DAYTIME_STEPS)

CITY_PRESET_SEEDS: tuple[dict, ...] = (
    {
        "slug": "daytime",
        "name": "Tag",
        "category": "world",
        "description": "Helle Tageszeit, klares Wetter, Tageszyklus läuft weiter",
        "steps": DAYTIME_STEPS,
        "sort_order": 10,
        "enabled": True,
        "is_system": True,
        "moderator_can_run": True,
        "requires_confirmation": False,
    },
    {
        "slug": "daytime-noon",
        "name": "Tag (Mittag)",
        "category": "world",
        "description": "Mittagshelligkeit ohne Zeitwechsel — bleibt dauerhaft hell",
        "steps": NOON_LOCKED_STEPS,
        "sort_order": 15,
        "enabled": True,
        "is_system": True,
        "moderator_can_run": True,
        "requires_confirmation": False,
    },
    {
        "slug": "nighttime",
        "name": "Nacht",
        "category": "world",
        "description": "Mitternacht, klares Wetter",
        "steps": NIGHTTIME_STEPS,
        "sort_order": 20,
        "enabled": True,
        "is_system": True,
        "moderator_can_run": True,
        "requires_confirmation": False,
    },
    {
        "slug": "session-bootstrap",
        "name": "Session-Start (Tag)",
        "category": "world",
        "description": "Wird beim Start einer Luanti-Session automatisch ausgeführt.",
        "steps": SESSION_BOOTSTRAP_STEPS,
        "sort_order": 5,
        "enabled": True,
        "is_system": True,
        "moderator_can_run": False,
        "requires_confirmation": False,
    },
)
