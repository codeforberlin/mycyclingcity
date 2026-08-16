# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Default RCON preset command lists (Minecraft 1.21+ gamerule names)."""

# WorldGuard city policy on __global__ (-w injected by normalize_preset_commands).
# VehiclesPlus place/drive needs vehicles-* plus use/interact; build stays denied.
_CITY_WORLDGUARD_FLAGS = [
    "rg flag __global__ build deny",
    "rg flag __global__ use allow",
    "rg flag __global__ interact allow",
    "rg flag __global__ vehicles-spawn allow",
    "rg flag __global__ vehicles-drive allow",
]

# VehiclesPlus model permissions (see vehicles/*.hjson + config.yml wildcards).
# Without these, players see: "You don't have permission to drive this vehicle!"
_CITY_VEHICLESPLUS_LP = [
    "lp group default permission set vp.ride.* true",
    "lp group default permission set vp.spawn.* true",
    "lp group default permission set vp.buy.* true",
    "lp group default permission set vp.adjust.* true",
]

CITY_MODE_PRESET = {
    "slug": "city-gamerules",
    "name": "Stadtmodus (Spielregeln)",
    "category": "gamerule",
    "sort_order": 10,
    "description": (
        "Sichere Bau-Welt: kein Schleim/Monster, kein Fallschaden, kein PvP, "
        "Inventar behalten, Blöcke droppen; VehiclesPlus platzieren/fahren "
        "(__global__ + LuckPerms default)."
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
        *_CITY_WORLDGUARD_FLAGS,
        *_CITY_VEHICLESPLUS_LP,
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
