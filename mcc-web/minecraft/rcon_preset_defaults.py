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
