# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    material_map.py
# @note    Map Bukkit/Minecraft materials to Mineclonia itemstrings.

from __future__ import annotations

import re

# Explicit overrides where Mineclonia names diverge from a naive lowercase map.
MATERIAL_OVERRIDES: dict[str, str] = {
    "COBBLESTONE": "mcl_core:cobble",
    "MOSSY_COBBLESTONE": "mcl_core:mossycobble",
    "OAK_LOG": "mcl_core:tree",
    "OAK_WOOD": "mcl_core:tree",
    "OAK_PLANKS": "mcl_core:wood",
    "SPRUCE_LOG": "mcl_core:sprucetree",
    "SPRUCE_PLANKS": "mcl_core:sprucewood",
    "BIRCH_LOG": "mcl_core:birchtree",
    "BIRCH_PLANKS": "mcl_core:birchwood",
    "JUNGLE_LOG": "mcl_core:jungletree",
    "JUNGLE_PLANKS": "mcl_core:junglewood",
    "ACACIA_LOG": "mcl_core:acaciatree",
    "ACACIA_PLANKS": "mcl_core:acaciawood",
    "DARK_OAK_LOG": "mcl_core:darktree",
    "DARK_OAK_PLANKS": "mcl_core:darkwood",
    "GRASS_BLOCK": "mcl_core:dirt_with_grass",
    "DIRT": "mcl_core:dirt",
    "STONE": "mcl_core:stone",
    "GRANITE": "mcl_core:granite",
    "DIORITE": "mcl_core:diorite",
    "ANDESITE": "mcl_core:andesite",
    "SAND": "mcl_core:sand",
    "RED_SAND": "mcl_core:redsand",
    "GRAVEL": "mcl_core:gravel",
    "GLASS": "mcl_core:glass",
    "SANDSTONE": "mcl_core:sandstone",
    "OBSIDIAN": "mcl_core:obsidian",
    "BEDROCK": "mcl_core:bedrock",
    "NETHERRACK": "mcl_nether:netherrack",
    "GLOWSTONE": "mcl_nether:glowstone",
    "TORCH": "mcl_torches:torch",
    "CRAFTING_TABLE": "mcl_crafting_table:crafting_table",
    "FURNACE": "mcl_furnaces:furnace",
    "CHEST": "mcl_chests:chest",
    "BUCKET": "mcl_buckets:bucket_empty",
    "WATER_BUCKET": "mcl_buckets:bucket_water",
    "LAVA_BUCKET": "mcl_buckets:bucket_lava",
    "STICK": "mcl_core:stick",
    "COAL": "mcl_core:coal_lump",
    "CHARCOAL": "mcl_core:charcoal",
    "DIAMOND": "mcl_core:diamond",
    "IRON_INGOT": "mcl_core:iron_ingot",
    "GOLD_INGOT": "mcl_core:gold_ingot",
    "COPPER_INGOT": "mcl_copper:copper_ingot",
    "NETHERITE_INGOT": "mcl_nether:netherite_ingot",
    "APPLE": "mcl_core:apple",
    "BREAD": "mcl_farming:bread",
    "WHEAT": "mcl_farming:wheat_item",
    "STRING": "mcl_mobitems:string",
    "FEATHER": "mcl_mobitems:feather",
    "LEATHER": "mcl_mobitems:leather",
    "BONE": "mcl_mobitems:bone",
    "GUNPOWDER": "mcl_mobitems:gunpowder",
    "FLINT": "mcl_core:flint",
    "BRICK": "mcl_core:brick",
    "CLAY_BALL": "mcl_core:clay_lump",
    "PAPER": "mcl_core:paper",
    "BOOK": "mcl_books:book",
    "COMPASS": "mcl_compass:compass",
    "CLOCK": "mcl_clock:clock",
    "SHEARS": "mcl_tools:shears",
}

_TOOL_SUFFIX = {
    "PICKAXE": "pick",
    "AXE": "axe",
    "SHOVEL": "shovel",
    "HOE": "hoe",
    "SWORD": "sword",
}

_ARMOR_SUFFIX = {
    "HELMET": "helmet",
    "CHESTPLATE": "chestplate",
    "LEGGINGS": "leggings",
    "BOOTS": "boots",
}

_TIER_ALIAS = {
    "WOODEN": "wood",
    "GOLDEN": "gold",
    "CHAINMAIL": "chain",
    "LEATHER": "leather",
    "STONE": "stone",
    "IRON": "iron",
    "DIAMOND": "diamond",
    "NETHERITE": "netherite",
    "COPPER": "copper",
}

_WOOL_COLORS = {
    "WHITE",
    "ORANGE",
    "MAGENTA",
    "LIGHT_BLUE",
    "YELLOW",
    "LIME",
    "PINK",
    "GRAY",
    "LIGHT_GRAY",
    "CYAN",
    "PURPLE",
    "BLUE",
    "BROWN",
    "GREEN",
    "RED",
    "BLACK",
}


def normalize_material(material: str) -> str:
    raw = (material or "").strip().upper()
    if raw.startswith("MINECRAFT:"):
        raw = raw[len("MINECRAFT:") :]
    return raw


def _snake(material: str) -> str:
    return material.lower()


def candidates_for_material(material: str) -> list[str]:
    """Ordered Mineclonia itemstring candidates for a Bukkit material."""
    mat = normalize_material(material)
    if not mat:
        return []
    if mat in MATERIAL_OVERRIDES:
        return [MATERIAL_OVERRIDES[mat]]

    out: list[str] = []

    # Tools: DIAMOND_PICKAXE -> mcl_tools:pick_diamond
    for suffix, tool in _TOOL_SUFFIX.items():
        if mat.endswith("_" + suffix):
            tier = mat[: -(len(suffix) + 1)]
            tier_key = _TIER_ALIAS.get(tier, tier.lower())
            out.append(f"mcl_tools:{tool}_{tier_key}")
            break

    # Armor: IRON_CHESTPLATE / CHAINMAIL_HELMET
    for suffix, piece in _ARMOR_SUFFIX.items():
        if mat.endswith("_" + suffix):
            tier = mat[: -(len(suffix) + 1)]
            tier_key = _TIER_ALIAS.get(tier, tier.lower())
            out.append(f"mcl_armor:{piece}_{tier_key}")
            break

    # Wool: WHITE_WOOL -> mcl_wool:white (and variants)
    if mat.endswith("_WOOL"):
        color = mat[: -len("_WOOL")].lower()
        out.extend(
            [
                f"mcl_wool:{color}",
                f"mcl_wool:{color}_wool",
                f"mcl_core:{color}_wool",
            ]
        )

    # Stained glass: RED_STAINED_GLASS
    if mat.endswith("_STAINED_GLASS"):
        color = mat[: -len("_STAINED_GLASS")].lower()
        out.extend(
            [
                f"mcl_core:{color}_stained_glass",
                f"mcl_core:glass_{color}",
            ]
        )

    snake = _snake(mat)
    # Generic guesses across common mods
    for mod in (
        "mcl_core",
        "mcl_farming",
        "mcl_nether",
        "mcl_ocean",
        "mcl_copper",
        "mcl_amethyst",
        "mcl_deepslate",
        "mcl_mangrove",
        "mcl_cherry_blossom",
        "mcl_bamboo",
        "mcl_flowers",
        "mcl_torches",
        "mcl_chests",
        "mcl_furnaces",
        "mcl_hoppers",
        "mcl_mobitems",
        "mcl_raw_ores",
        "mcl_redstone",
        "mesecons",
    ):
        out.append(f"{mod}:{snake}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in out:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def resolve_material(
    material: str,
    *,
    registry: set[str] | None = None,
) -> str | None:
    """
    Pick best Mineclonia itemstring.

    With a registry set, only return names that exist in-game.
    Without registry, return the first heuristic candidate (optimistic).
    """
    cands = candidates_for_material(material)
    if not cands:
        return None
    if not registry:
        return cands[0]
    for name in cands:
        if name in registry:
            return name
    # Fuzzy: any registry item whose local name equals snake material
    snake = _snake(normalize_material(material))
    for name in registry:
        if ":" in name and name.split(":", 1)[1] == snake:
            return name
    return None


def registry_search(query: str, names: list[str], *, limit: int = 50) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return names[:limit]
    tokens = [t for t in re.split(r"\s+", q) if t]
    hits = []
    for name in names:
        low = name.lower()
        if all(t in low for t in tokens):
            hits.append(name)
            if len(hits) >= limit:
                break
    return hits
