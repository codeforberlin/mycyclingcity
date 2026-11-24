-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Keep in step with luanti/services/mcl_map.py. The Django command rejects a
-- mapping entry whose new name disagrees with that module.

local M = {}

local convert_ids = dofile(core.get_modpath("mcc_migrator") .. "/mcc_convert_ids.lua")

M.convert_stub_mode = false

local function finish_mtg_name(name)
    if not name then
        return nil
    end
    if M.convert_stub_mode then
        return convert_ids.to_convert_id(name)
    end
    return name
end

local CORE = {
    stone = "default:stone",
    cobble = "default:cobble",
    mossycobble = "default:mossycobble",
    dirt = "default:dirt",
    dirt_with_grass = "default:dirt_with_grass",
    coarse_dirt = "default:dirt",
    grass_path = "default:dirt_with_grass",
    sand = "default:sand",
    redsand = "default:desert_sand",
    gravel = "default:gravel",
    clay = "default:clay",
    glass = "default:glass",
    obsidian = "default:obsidian",
    bedrock = "default:obsidian",
    sandstone = "default:sandstone",
    brick = "default:brick",
    tree = "default:tree",
    wood = "default:wood",
    leaves = "default:leaves",
    darkleaves = "default:leaves",
    jungletree = "default:jungletree",
    junglewood = "default:junglewood",
    sprucetree = "default:pine_tree",
    sprucewood = "default:pine_wood",
    birchtree = "default:aspen_tree",
    birchwood = "default:aspen_wood",
    acaciatree = "default:acacia_tree",
    acaciawood = "default:acacia_wood",
    darktree = "default:tree",
    darkwood = "default:wood",
    stick = "default:stick",
    coal_lump = "default:coal_lump",
    charcoal = "default:coal_lump",
    iron_ingot = "default:steel_ingot",
    gold_ingot = "default:gold_ingot",
    diamond = "default:diamond",
    apple = "default:apple",
    paper = "default:paper",
    book = "default:book",
    clay_lump = "default:clay_lump",
    flint = "default:flint",
    torch = "default:torch",
    ladder = "default:ladder",
    andesite = "default:stone",
    andesite_smooth = "default:stone",
    diorite = "default:stone",
    diorite_smooth = "default:stone",
    granite = "default:stone",
    granite_smooth = "default:stone",
    stone_smooth = "default:stone",
    stonebrick = "default:stonebrick",
    stonebrickcarved = "default:stonebrick",
    stonebrickcracked = "default:stonebrick",
    cobweb = "default:cobweb",
    reeds = "default:papyrus",
    packed_ice = "default:ice",
    coalblock = "default:coalblock",
    ironblock = "default:steelblock",
    goldblock = "default:goldblock",
    diamondblock = "default:diamondblock",
    emeraldblock = "default:emeraldblock",
    water_source = "default:water_source",
    water_flowing = "default:water_flowing",
    glass_black = "default:obsidian_glass",
    glass_blue = "default:obsidian_glass",
    redsandstonesmooth = "default:desert_sandstone",
    sandstonesmooth2 = "default:sandstone",
}

local SIMPLE = {
    ["mcl_chests:chest"] = "default:chest",
    ["mcl_chests:chest_left"] = "default:chest",
    ["mcl_chests:chest_right"] = "default:chest",
    ["mcl_chests:chest_small"] = "default:chest",
    ["mcl_chests:trapped_chest_left"] = "default:chest",
    ["mcl_chests:trapped_chest_right"] = "default:chest",
    ["mcl_chests:trapped_chest_small"] = "default:chest",
    ["mcl_furnaces:furnace"] = "default:furnace",
    ["mcl_torches:torch"] = "default:torch",
    ["mcl_torches:torch_wall"] = "default:torch",
    ["mcl_crafting_table:crafting_table"] = "default:craftingtable",
    ["mcl_beds:bed_red_bottom"] = "beds:bed_bottom",
    ["mcl_beds:bed_red_top"] = "beds:bed_top",
    ["mcl_doors:trapdoor"] = "doors:trapdoor",
    ["mcl_doors:trapdoor_open"] = "doors:trapdoor_open",
    ["mcl_doors:iron_trapdoor"] = "doors:trapdoor_steel",
    ["mcl_flowerpots:flower_pot"] = "default:dry_shrub",
    ["mcl_signs:standing_sign"] = "default:sign_wall",
    ["mcl_signs:wall_sign"] = "default:sign_wall",
    ["mcl_nether:nether_brick"] = "default:stone",
    ["mcl_nether:red_nether_brick"] = "default:stonebrick",
    ["mcl_nether:soul_sand"] = "default:sand",
    ["mcl_nether:magma"] = "default:stone",
    ["mcl_anvils:anvil"] = "default:steelblock",
    ["mcl_buttons:button_stone_off"] = "default:stone",
    ["mcl_cauldrons:cauldron_3"] = "default:chest",
    ["mcl_end:end_rod"] = "default:torch",
    ["mcl_hoppers:hopper"] = "default:chest",
    ["mcl_jukebox:jukebox"] = "default:chest",
    ["mcl_lever:lever_on"] = "default:torch",
    ["mcl_minecarts:rail"] = "carts:rail",
    ["mcl_minecarts:golden_rail"] = "carts:powered_rail",
    ["mcl_minecarts:detector_rail"] = "carts:brake_rail",
    ["mcl_noteblock:noteblock"] = "default:chest",
    ["mcl_pistons:piston_sticky_off"] = "default:stone",
    ["mcl_pistons:piston_sticky_on"] = "default:stone",
    ["mcl_pressureplates:pressure_plate_oak_off"] = "default:wood",
    ["mcl_pressureplates:pressure_plate_stone_off"] = "default:stone",
    ["mcl_redstone_lamp:lamp_on"] = "default:glass",
    ["mcl_redstone_torch:redstone_torch_on_wall"] = "default:torch",
}

local STAIR_MATERIAL = {
    oak = "wood", oakwood = "wood", wood = "wood",
    spruce = "pine_wood", sprucewood = "pine_wood",
    birch = "aspen_wood", birchwood = "aspen_wood", birchtreebark = "aspen_wood",
    jungle = "junglewood", junglewood = "junglewood",
    acacia = "acacia_wood", acaciawood = "acacia_wood", acaciatreebark = "acacia_wood",
    dark = "wood", darkwood = "wood", darkoak = "wood",
    stone = "stone", cobble = "cobble", stonebrick = "stonebrick",
    brick = "brick", brickblock = "brick",
    sandstone = "sandstone", obsidian = "obsidian", glass = "glass",
    andesite = "stone", andesitesmooth = "stone", goldblock = "goldblock", quartzblock = "sandstone",
    concretebrown = "stone", concretegreen = "stone", concretelime = "stone",
    concretecyan = "stone", concretered = "stone", concreteyellow = "stone",
    concretesilver = "stone",
}

local FENCE_MATERIAL = {
    oak = "wood", wood = "wood", fence = "wood",
    spruce = "pine_wood", birch = "aspen_wood", jungle = "junglewood",
    acacia = "acacia_wood", dark = "wood", darkoak = "wood",
}

local WOOL_ALIAS = {
    gray = "grey", dark_gray = "dark_grey", purple = "violet",
    lime = "green", light_blue = "cyan", silver = "grey",
}

local WOOL_COLORS = {
    white = true, grey = true, gray = true, dark_grey = true, dark_gray = true,
    black = true, red = true, yellow = true, green = true, cyan = true, blue = true,
    magenta = true, orange = true, violet = true, purple = true, brown = true, pink = true,
    dark_green = true, lime = true, light_blue = true, silver = true,
}

local CONCRETE_WOOL = {
    black = "black", white = "white", red = "red", yellow = "yellow",
    orange = "orange", lime = "green", light_blue = "cyan", silver = "grey",
    red = "red",
}

local TREES = {
    tree_oak = "default:tree", wood_oak = "default:wood", leaves_oak = "default:leaves",
    sapling_oak = "default:sapling", tree_spruce = "default:pine_tree",
    wood_spruce = "default:pine_wood", tree_spruce = "default:pine_tree",
    wood_birch = "default:aspen_wood", leaves_jungle = "default:jungleleaves",
}

local FLOWERS = {
    dandelion = "flowers:dandelion", poppy = "flowers:rose",
    blue_orchid = "flowers:geranium", allium = "flowers:viola",
    azure_bluet = "flowers:tulip", oxeye_daisy = "flowers:chrysanthemum",
    tulip_red = "flowers:tulip", tulip_pink = "flowers:tulip",
    rose_bush = "flowers:rose", tallgrass = "default:grass_1",
    double_grass = "default:grass_2", waterlily = "flowers:waterlily",
}

local FARMING = {
    wheat = "default:grass_1", wheat_1 = "default:grass_1", wheat_2 = "default:grass_1",
    wheat_3 = "default:grass_1", wheat_4 = "default:grass_1", wheat_5 = "default:grass_1",
    wheat_6 = "default:grass_1", wheat_7 = "default:grass_1", carrot = "default:grass_1", carrot_1 = "default:grass_1",
    carrot_2 = "default:grass_1", carrot_4 = "default:grass_1", carrot_5 = "default:grass_1",
    carrot_6 = "default:grass_1", carrot_7 = "default:grass_1", potato = "default:grass_1",
    potato_1 = "default:grass_1", potato_2 = "default:grass_1", potato_3 = "default:grass_1",
    potato_4 = "default:grass_1", potato_5 = "default:grass_1", potato_6 = "default:grass_1",
    potato_7 = "default:grass_1", beetroot = "default:grass_1",
    beetroot_0 = "default:grass_1", beetroot_2 = "default:grass_1",
    pumpkin = "default:stone", hay_block = "default:stone", soil_wet = "default:dirt",
}

local DOOR_KIND = {
    wooden_door = "wood", wood_door = "wood", oak_door = "wood", door_oak = "wood",
    spruce_door = "wood", door_spruce = "wood", birch_door = "wood", door_birch = "wood",
    jungle_door = "wood", door_jungle = "wood", acacia_door = "wood", door_acacia = "wood",
    dark_oak_door = "wood", door_dark_oak = "wood", iron_door = "steel", steel_door = "steel",
}

local function compact(material)
    return (material or ""):gsub("_", "")
end

local function has_prefix(name, prefix)
    return (name or ""):sub(1, #prefix) == prefix
end

local function after_prefix(name, prefix)
    if not has_prefix(name, prefix) then
        return nil
    end
    return name:sub(#prefix + 1)
end

local function stair_material_key(rest)
    local material = rest
    if material:sub(-4) == "_top" then
        material = material:sub(1, -5)
    elseif material:sub(-7) == "_double" then
        material = material:sub(1, -8)
    end
    return STAIR_MATERIAL[compact(material)]
end

-- Lua patterns are not PCRE: "|" is literal, not alternation (unlike luanti/services/mcl_map.py).
local function parse_mcl_stair(name)
    local rest = name:match("^mcl_stairs:stair_(.+)$")
    if rest then
        return "stair", rest
    end
    rest = name:match("^mcl_stairs:slab_(.+)$")
    if rest then
        return "slab", rest
    end
    return nil, nil
end

local function door_kind_from_base(base)
    if DOOR_KIND[base] then
        return DOOR_KIND[base]
    end
    if base:sub(1, 5) == "door_" then
        return "wood"
    end
    if base:find("iron", 1, true) or base:find("steel", 1, true) then
        return "steel"
    end
    return nil
end

function M.resolve_name(old_name)
    local name = old_name or ""
    if name:sub(1, 4) ~= "mcl_" then
        return nil
    end
    if SIMPLE[name] then
        return finish_mtg_name(SIMPLE[name])
    end
    if name:sub(1, 9) == "mcl_core:" then
        return finish_mtg_name(CORE[name:sub(10)])
    end
    local kind, rest = parse_mcl_stair(name)
    if kind then
        local shape, material = "", rest
        if kind == "stair" and rest:sub(-6) == "_inner" then
            shape, material = "inner", rest:sub(1, -7)
        elseif kind == "stair" and rest:sub(-6) == "_outer" then
            shape, material = "outer", rest:sub(1, -7)
        end
        local target = stair_material_key(material)
        if not target then
            return nil
        end
        if kind == "slab" then
            return finish_mtg_name("stairs:slab_" .. target)
        end
        if shape == "inner" then
            return finish_mtg_name("stairs:stair_inner_" .. target)
        end
        if shape == "outer" then
            return finish_mtg_name("stairs:stair_outer_" .. target)
        end
        return finish_mtg_name("stairs:stair_" .. target)
    end
    local door_base, half = name:match("^mcl_doors:(.+)_([bt])_(%d+)$")
    if door_base then
        local dk = door_kind_from_base(door_base)
        if not dk then
            return nil
        end
        local side = half == "b" and "a" or "b"
        return finish_mtg_name("doors:door_" .. dk .. "_" .. side)
    end
    if name:sub(1, 10) == "mcl_doors:" then
        local local_name = name:sub(11)
        local dk = door_kind_from_base(local_name)
        if dk then
            return finish_mtg_name("doors:door_" .. dk)
        end
        return nil
    end
    if name:sub(1, 11) == "mcl_fences:" then
        local local_name = name:sub(12)
        if local_name:find("fence_gate", 1, true) then
            return finish_mtg_name("doors:trapdoor")
        end
        local_name = local_name:gsub("_fence$", "")
        local material = FENCE_MATERIAL[compact(local_name)]
        if material then
            return finish_mtg_name("default:fence_" .. material)
        end
        return nil
    end
    if name:sub(1, 9) == "mcl_wool:" then
        local color = name:sub(10):gsub("_wool$", "")
        if color:sub(-7) == "_carpet" then
            color = color:sub(1, -8)
        end
        if not WOOL_COLORS[color] then
            return nil
        end
        return finish_mtg_name("wool:" .. (WOOL_ALIAS[color] or color))
    end
    if name:sub(1, 10) == "mcl_walls:" then
        local local_name = name:sub(11)
        if local_name == "mossycobble" then
            return finish_mtg_name("walls:mossycobble")
        end
        if local_name == "cobble" or local_name:sub(1, 7) == "cobble_" then
            return finish_mtg_name("walls:cobble")
        end
        return nil
    end
    if name == "mcl_panes:glass_pane" or name == "mcl_xpanes:pane" or name == "mcl_core:glass_pane" then
        return finish_mtg_name("xpanes:pane")
    end
    if has_prefix(name, "mcl_panes:pane_") or name == "mcl_panes:pane_natural" then
        return finish_mtg_name("xpanes:pane")
    end
    if has_prefix(name, "mcl_colorblocks:") then
        local local_name = after_prefix(name, "mcl_colorblocks:")
        if has_prefix(local_name, "concrete_") then
            local wool = CONCRETE_WOOL[after_prefix(local_name, "concrete_")]
            if wool then
                return finish_mtg_name("wool:" .. wool)
            end
        end
        if has_prefix(local_name, "concrete_powder_") then
            local wool = CONCRETE_WOOL[after_prefix(local_name, "concrete_powder_")]
            if wool then
                return finish_mtg_name("wool:" .. wool)
            end
        end
        if local_name == "hardened_clay" or has_prefix(local_name, "hardened_clay_") then
            return finish_mtg_name("default:stonebrick")
        end
        return nil
    end
    if name:sub(1, 10) == "mcl_trees:" then
        return finish_mtg_name(TREES[name:sub(11)])
    end
    if name:sub(1, 12) == "mcl_flowers:" then
        return finish_mtg_name(FLOWERS[name:sub(13)])
    end
    if name:sub(1, 12) == "mcl_farming:" then
        return finish_mtg_name(FARMING[name:sub(13)])
    end
    return nil
end

function M.resolve_param2(old_name, param2)
    local p = (tonumber(param2) or 0) % 256
    local _base, _half, digit = (old_name or ""):match("^mcl_doors:.+_([bt])_(%d+)$")
    if digit then
        return (tonumber(digit) - 1) % 4
    end
    if (old_name or ""):sub(1, 11) == "mcl_stairs:" then
        return p % 24
    end
    return p
end

function M.param2_rule(old_name)
    if (old_name or ""):match("^mcl_doors:.+_[bt]_%d+$") then
        return "door_facing"
    end
    if (old_name or ""):sub(1, 11) == "mcl_stairs:" then
        return "stair_facedir"
    end
    return "keep"
end

--- All node names that convert_mcl may write (for stub registration in Mineclonia).
function M.collect_convert_targets()
    local seen = {}
    local function add(name)
        if name and name ~= "" then
            if M.convert_stub_mode then
                name = convert_ids.to_convert_id(name) or name
            end
            seen[name] = true
        end
    end

    for _, target in pairs(SIMPLE) do
        add(target)
    end
    for _, target in pairs(CORE) do
        add(target)
    end
    add("walls:cobble")
    add("walls:mossycobble")
    add("xpanes:pane")
    for _, material in pairs(STAIR_MATERIAL) do
        add("stairs:stair_" .. material)
        add("stairs:slab_" .. material)
        add("stairs:stair_inner_" .. material)
        add("stairs:stair_outer_" .. material)
    end
    for _, kind in pairs(DOOR_KIND) do
        add("doors:door_" .. kind .. "_a")
        add("doors:door_" .. kind .. "_b")
        add("doors:door_" .. kind)
    end
    add("doors:trapdoor")
    add("doors:trapdoor_open")
    add("doors:trapdoor_steel")
    for _, target in pairs(TREES) do
        add(target)
    end
    for _, target in pairs(FLOWERS) do
        add(target)
    end
    for _, target in pairs(FARMING) do
        add(target)
    end
    for _, material in pairs(FENCE_MATERIAL) do
        add("default:fence_" .. material)
    end
    for color, wool in pairs(WOOL_ALIAS) do
        add("wool:" .. (wool or color))
    end
    for color in pairs(WOOL_COLORS) do
        add("wool:" .. color)
    end

    return seen
end

return M