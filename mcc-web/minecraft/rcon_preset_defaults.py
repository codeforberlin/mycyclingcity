# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Default RCON preset command lists (Minecraft 1.21+ gamerule names)."""

CITY_MODE_PRESET = {
    "slug": "city-gamerules",
    "name": "Stadtmodus (Spielregeln)",
    "category": "gamerule",
    "sort_order": 10,
    "description": (
        "Sichere Bau-Welt: kein Schleim/Monster, kein Fallschaden, kein PvP, "
        "Inventar behalten, Blöcke droppen beim Abbauen."
    ),
    "commands": [
        "difficulty peaceful",
        "gamerule spawn_monsters false",
        "gamerule mob_griefing false",
        "gamerule fall_damage false",
        "gamerule fire_damage false",
        "gamerule drowning_damage false",
        "gamerule freeze_damage false",
        "gamerule pvp false",
        "gamerule keep_inventory true",
        "gamerule block_drops true",
        "gamerule natural_health_regeneration true",
        "gamerule tnt_explodes false",
        "gamerule fire_spread_radius_around_player 0",
        "gamerule mob_drops false",
        "kill @e[type=minecraft:slime]",
        "kill @e[type=minecraft:magma_cube]",
    ],
}

BUILDER_SESSION_BOOTSTRAP_PRESET = {
    "slug": "builder-session-bootstrap",
    "name": "Bau-Session Bootstrap",
    "category": "gamerule",
    "sort_order": 5,
    "description": (
        "Wird automatisch beim Start einer Bau-Session ausgeführt: stellt den "
        "sicheren Stadtmodus her, ohne manuelle Stadtsteuerung im Admin."
    ),
    "commands": list(CITY_MODE_PRESET["commands"]),
}

PLAYER_SESSION_BOOTSTRAP_PRESET = {
    "slug": "player-session-bootstrap",
    "name": "Spieler-Session Bootstrap",
    "category": "gamerule",
    "sort_order": 6,
    "description": (
        "Wird automatisch beim Start einer Spieler-Session ausgeführt: stellt den "
        "sicheren Stadtmodus her. Adventure Mode setzt die Session-Steuerung "
        "danach zwingend per RCON."
    ),
    "commands": list(CITY_MODE_PRESET["commands"]),
}

# Minecraft 1.21.11+: doDaylightCycle -> advance_time, doWeatherCycle -> advance_weather
WORLD_WEATHER_PRESETS: dict[str, dict] = {
    "day-clear": {
        "description": "Heller Tag, klares Wetter, Zeit und Wetter pausiert.",
        "commands": [
            "time set day",
            "weather clear",
            "gamerule advance_time false",
            "gamerule advance_weather false",
        ],
    },
    "day-cycle": {
        "description": "Tag, klares Wetter, Tageszyklus läuft weiter.",
        "commands": [
            "time set day",
            "weather clear",
            "gamerule advance_time true",
            "gamerule advance_weather false",
        ],
    },
    "noon": {
        "description": "Mittagshelligkeit für Screenshots und Präsentationen.",
        "commands": [
            "time set noon",
            "weather clear",
            "gamerule advance_time false",
            "gamerule advance_weather false",
        ],
    },
    "night": {
        "description": "Nacht, klares Wetter, Zeit und Wetter pausiert.",
        "commands": [
            "time set night",
            "weather clear",
            "gamerule advance_time false",
            "gamerule advance_weather false",
        ],
    },
}
