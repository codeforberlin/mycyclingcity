# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Mineclonia itemstrings to the standard mods installed in games/mycyclingcity.
# Unknown names return None. Callers must not write a partial conversion.

from __future__ import annotations

import re

_CORE: dict[str, str] = {
    "stone": "default:stone",
    "cobble": "default:cobble",
    "mossycobble": "default:mossycobble",
    "dirt": "default:dirt",
    "dirt_with_grass": "default:dirt_with_grass",
    "coarse_dirt": "default:dirt",
    "grass_path": "default:dirt_with_grass",
    "sand": "default:sand",
    "redsand": "default:desert_sand",
    "gravel": "default:gravel",
    "clay": "default:clay",
    "glass": "default:glass",
    "obsidian": "default:obsidian",
    "bedrock": "default:obsidian",
    "sandstone": "default:sandstone",
    "brick": "default:brick",
    "tree": "default:tree",
    "wood": "default:wood",
    "leaves": "default:leaves",
    "darkleaves": "default:leaves",
    "jungletree": "default:jungletree",
    "junglewood": "default:junglewood",
    "sprucetree": "default:pine_tree",
    "sprucewood": "default:pine_wood",
    "birchtree": "default:aspen_tree",
    "birchwood": "default:aspen_wood",
    "acaciatree": "default:acacia_tree",
    "acaciawood": "default:acacia_wood",
    "darktree": "default:tree",
    "darkwood": "default:wood",
    "stick": "default:stick",
    "coal_lump": "default:coal_lump",
    "charcoal": "default:coal_lump",
    "iron_ingot": "default:steel_ingot",
    "gold_ingot": "default:gold_ingot",
    "diamond": "default:diamond",
    "apple": "default:apple",
    "paper": "default:paper",
    "book": "default:book",
    "clay_lump": "default:clay_lump",
    "flint": "default:flint",
    "torch": "default:torch",
    "ladder": "default:ladder",
    "andesite": "default:stone",
    "andesite_smooth": "default:stone",
    "diorite": "default:stone",
    "diorite_smooth": "default:stone",
    "granite": "default:stone",
    "granite_smooth": "default:stone",
    "stone_smooth": "default:stone",
    "stonebrick": "default:stonebrick",
    "stonebrickcarved": "default:stonebrick",
    "stonebrickcracked": "default:stonebrick",
    "cobweb": "default:cobweb",
    "reeds": "default:papyrus",
    "packed_ice": "default:ice",
    "coalblock": "default:coalblock",
    "ironblock": "default:steelblock",
    "goldblock": "default:goldblock",
    "diamondblock": "default:diamondblock",
    "emeraldblock": "default:emeraldblock",
    "water_source": "default:water_source",
    "water_flowing": "default:water_flowing",
    "glass_black": "default:obsidian_glass",
    "glass_blue": "default:obsidian_glass",
    "redsandstonesmooth": "default:desert_sandstone",
    "sandstonesmooth2": "default:sandstone",
}

_SIMPLE_MODS: dict[str, str] = {
    "mcl_chests:chest": "default:chest",
    "mcl_chests:chest_left": "default:chest",
    "mcl_chests:chest_right": "default:chest",
    "mcl_chests:chest_small": "default:chest",
    "mcl_chests:trapped_chest_left": "default:chest",
    "mcl_chests:trapped_chest_right": "default:chest",
    "mcl_chests:trapped_chest_small": "default:chest",
    "mcl_furnaces:furnace": "default:furnace",
    "mcl_torches:torch": "default:torch",
    "mcl_torches:torch_wall": "default:torch",
    "mcl_crafting_table:crafting_table": "default:craftingtable",
    "mcl_beds:bed_red_bottom": "beds:bed_bottom",
    "mcl_beds:bed_red_top": "beds:bed_top",
    "mcl_doors:trapdoor": "doors:trapdoor",
    "mcl_doors:trapdoor_open": "doors:trapdoor_open",
    "mcl_doors:iron_trapdoor": "doors:trapdoor_steel",
    "mcl_flowerpots:flower_pot": "default:dry_shrub",
    "mcl_signs:standing_sign": "default:sign_wall",
    "mcl_signs:wall_sign": "default:sign_wall",
    "mcl_nether:nether_brick": "default:stone",
    "mcl_nether:red_nether_brick": "default:stonebrick",
    "mcl_nether:soul_sand": "default:sand",
    "mcl_nether:magma": "default:stone",
    "mcl_anvils:anvil": "default:steelblock",
    "mcl_buttons:button_stone_off": "default:stone",
    "mcl_cauldrons:cauldron_3": "default:chest",
    "mcl_end:end_rod": "default:torch",
    "mcl_hoppers:hopper": "default:chest",
    "mcl_jukebox:jukebox": "default:chest",
    "mcl_lever:lever_on": "default:torch",
    "mcl_minecarts:rail": "carts:rail",
    "mcl_minecarts:golden_rail": "carts:powered_rail",
    "mcl_minecarts:detector_rail": "carts:brake_rail",
    "mcl_noteblock:noteblock": "default:chest",
    "mcl_pistons:piston_sticky_off": "default:stone",
    "mcl_pistons:piston_sticky_on": "default:stone",
    "mcl_pressureplates:pressure_plate_oak_off": "default:wood",
    "mcl_pressureplates:pressure_plate_stone_off": "default:stone",
    "mcl_redstone_lamp:lamp_on": "default:glass",
    "mcl_redstone_torch:redstone_torch_on_wall": "default:torch",
}

_STAIR_MATERIAL: dict[str, str] = {
    "oak": "wood",
    "oakwood": "wood",
    "wood": "wood",
    "spruce": "pine_wood",
    "sprucewood": "pine_wood",
    "birch": "aspen_wood",
    "birchwood": "aspen_wood",
    "birchtreebark": "aspen_wood",
    "jungle": "junglewood",
    "junglewood": "junglewood",
    "acacia": "acacia_wood",
    "acaciawood": "acacia_wood",
    "acaciatreebark": "acacia_wood",
    "dark": "wood",
    "darkwood": "wood",
    "darkoak": "wood",
    "stone": "stone",
    "cobble": "cobble",
    "stonebrick": "stonebrick",
    "brick": "brick",
    "brickblock": "brick",
    "sandstone": "sandstone",
    "obsidian": "obsidian",
    "glass": "glass",
    "andesite": "stone",
    "andesitesmooth": "stone",
    "goldblock": "goldblock",
    "quartzblock": "sandstone",
    "concretebrown": "stone",
    "concretegreen": "stone",
    "concretelime": "stone",
    "concretecyan": "stone",
    "concretered": "stone",
    "concreteyellow": "stone",
    "concretesilver": "stone",
}

_FENCE_MATERIAL: dict[str, str] = {
    "oak": "wood",
    "wood": "wood",
    "fence": "wood",
    "spruce": "pine_wood",
    "birch": "aspen_wood",
    "jungle": "junglewood",
    "acacia": "acacia_wood",
    "dark": "wood",
    "darkoak": "wood",
}

_WOOL_COLORS = {
    "white",
    "grey",
    "gray",
    "dark_grey",
    "dark_gray",
    "black",
    "red",
    "yellow",
    "green",
    "cyan",
    "blue",
    "magenta",
    "orange",
    "violet",
    "purple",
    "brown",
    "pink",
    "dark_green",
    "lime",
    "light_blue",
    "silver",
}

_WOOL_ALIAS = {
    "gray": "grey",
    "dark_gray": "dark_grey",
    "purple": "violet",
    "lime": "green",
    "light_blue": "cyan",
    "silver": "grey",
}

_CONCRETE_WOOL: dict[str, str] = {
    "black": "black",
    "white": "white",
    "red": "red",
    "yellow": "yellow",
    "orange": "orange",
    "lime": "green",
    "light_blue": "cyan",
    "silver": "grey",
}

_TREES: dict[str, str] = {
    "tree_oak": "default:tree",
    "wood_oak": "default:wood",
    "leaves_oak": "default:leaves",
    "sapling_oak": "default:sapling",
    "tree_spruce": "default:pine_tree",
    "wood_spruce": "default:pine_wood",
    "wood_birch": "default:aspen_wood",
    "leaves_jungle": "default:jungleleaves",
}

_FLOWERS: dict[str, str] = {
    "dandelion": "flowers:dandelion",
    "poppy": "flowers:rose",
    "blue_orchid": "flowers:geranium",
    "allium": "flowers:viola",
    "azure_bluet": "flowers:tulip",
    "oxeye_daisy": "flowers:chrysanthemum",
    "tulip_red": "flowers:tulip",
    "tulip_pink": "flowers:tulip",
    "rose_bush": "flowers:rose",
    "tallgrass": "default:grass_1",
    "double_grass": "default:grass_2",
    "waterlily": "flowers:waterlily",
}

_FARMING: dict[str, str] = {
    "wheat": "default:grass_1",
    "wheat_1": "default:grass_1",
    "wheat_2": "default:grass_1",
    "wheat_3": "default:grass_1",
    "wheat_4": "default:grass_1",
    "wheat_5": "default:grass_1",
    "wheat_6": "default:grass_1",
    "wheat_7": "default:grass_1",
    "carrot": "default:grass_1",
    "carrot_1": "default:grass_1",
    "carrot_2": "default:grass_1",
    "carrot_4": "default:grass_1",
    "carrot_5": "default:grass_1",
    "carrot_6": "default:grass_1",
    "carrot_7": "default:grass_1",
    "potato": "default:grass_1",
    "potato_1": "default:grass_1",
    "potato_2": "default:grass_1",
    "potato_3": "default:grass_1",
    "potato_4": "default:grass_1",
    "potato_5": "default:grass_1",
    "potato_6": "default:grass_1",
    "potato_7": "default:grass_1",
    "beetroot": "default:grass_1",
    "beetroot_0": "default:grass_1",
    "beetroot_2": "default:grass_1",
    "pumpkin": "default:stone",
    "hay_block": "default:stone",
    "soil_wet": "default:dirt",
}

_DOOR_KIND = {
    "wooden_door": "wood",
    "wood_door": "wood",
    "oak_door": "wood",
    "door_oak": "wood",
    "spruce_door": "wood",
    "door_spruce": "wood",
    "birch_door": "wood",
    "door_birch": "wood",
    "jungle_door": "wood",
    "door_jungle": "wood",
    "acacia_door": "wood",
    "door_acacia": "wood",
    "dark_oak_door": "wood",
    "door_dark_oak": "wood",
    "iron_door": "steel",
    "steel_door": "steel",
}

_STAIR_RE = re.compile(r"^mcl_stairs:(stair|slab)_(.+)$")
_DOOR_RE = re.compile(r"^mcl_doors:(.+)_([bt])_(\d+)$")


def resolve_name(old_name: str) -> str | None:
    """Map one Mineclonia itemstring to a standard mod name, or None."""
    name = (old_name or "").strip()
    if not name.startswith("mcl_"):
        return None
    if name in _SIMPLE_MODS:
        return _SIMPLE_MODS[name]
    if name.startswith("mcl_core:"):
        return _CORE.get(name.split(":", 1)[1])
    stair = _resolve_stair(name)
    if stair:
        return stair
    door = _resolve_door(name)
    if door:
        return door
    fence = _resolve_fence(name)
    if fence:
        return fence
    wool = _resolve_wool(name)
    if wool:
        return wool
    wall = _resolve_wall(name)
    if wall:
        return wall
    pane = _resolve_pane(name)
    if pane:
        return pane
    concrete = _resolve_colorblocks(name)
    if concrete:
        return concrete
    tree = _resolve_trees(name)
    if tree:
        return tree
    flower = _resolve_flowers(name)
    if flower:
        return flower
    farming = _resolve_farming(name)
    if farming:
        return farming
    fence_gate = _resolve_fence_gate(name)
    if fence_gate:
        return fence_gate
    return None


def resolve_param2(old_name: str, param2: int) -> int:
    """Orientation for the converted node."""
    p = int(param2) & 0xFF
    name = (old_name or "").strip()
    door = _DOOR_RE.match(name)
    if door:
        facing = (int(door.group(3)) - 1) % 4
        return facing
    if name.startswith("mcl_stairs:"):
        return p % 24
    return p


def param2_rule(old_name: str) -> str:
    name = (old_name or "").strip()
    if _DOOR_RE.match(name):
        return "door_facing"
    if name.startswith("mcl_stairs:"):
        return "stair_facedir"
    return "keep"


def _stair_material_key(rest: str) -> str | None:
    material = rest
    if material.endswith("_top"):
        material = material[: -len("_top")]
    elif material.endswith("_double"):
        material = material[: -len("_double")]
    return _STAIR_MATERIAL.get(material.replace("_", ""))


def _resolve_stair(name: str) -> str | None:
    match = _STAIR_RE.match(name)
    if not match:
        return None
    kind, rest = match.group(1), match.group(2)
    shape = ""
    material = rest
    if kind == "stair" and rest.endswith("_inner"):
        shape = "inner"
        material = rest[: -len("_inner")]
    elif kind == "stair" and rest.endswith("_outer"):
        shape = "outer"
        material = rest[: -len("_outer")]
    target = _stair_material_key(material)
    if not target:
        return None
    if kind == "slab":
        return f"stairs:slab_{target}"
    if shape == "inner":
        return f"stairs:stair_inner_{target}"
    if shape == "outer":
        return f"stairs:stair_outer_{target}"
    return f"stairs:stair_{target}"


def _door_kind(base: str) -> str | None:
    if base in _DOOR_KIND:
        return _DOOR_KIND[base]
    if base.startswith("door_"):
        return "wood"
    if "iron" in base or "steel" in base:
        return "steel"
    return None


def _resolve_door(name: str) -> str | None:
    match = _DOOR_RE.match(name)
    if match:
        kind = _door_kind(match.group(1))
        if not kind:
            return None
        half = "a" if match.group(2) == "b" else "b"
        return f"doors:door_{kind}_{half}"
    if name.startswith("mcl_doors:"):
        kind = _door_kind(name.split(":", 1)[1])
        if kind:
            return f"doors:door_{kind}"
    return None


def _resolve_fence(name: str) -> str | None:
    if not name.startswith("mcl_fences:"):
        return None
    local = name.split(":", 1)[1]
    local = local.removesuffix("_fence")
    material = _FENCE_MATERIAL.get(local.replace("_", ""))
    if not material:
        return None
    return f"default:fence_{material}"


def _resolve_fence_gate(name: str) -> str | None:
    if not name.startswith("mcl_fences:"):
        return None
    local = name.split(":", 1)[1]
    if "fence_gate" not in local:
        return None
    if "spruce" in local:
        return "doors:trapdoor"
    return "doors:trapdoor"


def _resolve_wool(name: str) -> str | None:
    if not name.startswith("mcl_wool:"):
        return None
    color = name.split(":", 1)[1]
    color = color.removesuffix("_wool")
    if color.endswith("_carpet"):
        color = color[: -len("_carpet")]
    if color not in _WOOL_COLORS:
        return None
    return "wool:" + _WOOL_ALIAS.get(color, color)


def _resolve_wall(name: str) -> str | None:
    if not name.startswith("mcl_walls:"):
        return None
    local = name.split(":", 1)[1]
    if local == "mossycobble":
        return "walls:mossycobble"
    if local == "cobble" or local.startswith("cobble_"):
        return "walls:cobble"
    return None


def _resolve_pane(name: str) -> str | None:
    if name in {"mcl_panes:glass_pane", "mcl_xpanes:pane", "mcl_core:glass_pane"}:
        return "xpanes:pane"
    if name.startswith("mcl_panes:pane_"):
        return "xpanes:pane"
    return None


def _resolve_colorblocks(name: str) -> str | None:
    if not name.startswith("mcl_colorblocks:"):
        return None
    local = name.split(":", 1)[1]
    if local.startswith("concrete_"):
        color = local.removeprefix("concrete_")
        wool = _CONCRETE_WOOL.get(color)
        if wool:
            return "wool:" + wool
    if local.startswith("concrete_powder_"):
        color = local.removeprefix("concrete_powder_")
        wool = _CONCRETE_WOOL.get(color)
        if wool:
            return "wool:" + wool
    if local.startswith("hardened_clay"):
        return "default:stonebrick"
    return None


def _resolve_trees(name: str) -> str | None:
    if not name.startswith("mcl_trees:"):
        return None
    return _TREES.get(name.split(":", 1)[1])


def _resolve_flowers(name: str) -> str | None:
    if not name.startswith("mcl_flowers:"):
        return None
    return _FLOWERS.get(name.split(":", 1)[1])


def _resolve_farming(name: str) -> str | None:
    if not name.startswith("mcl_farming:"):
        return None
    return _FARMING.get(name.split(":", 1)[1])