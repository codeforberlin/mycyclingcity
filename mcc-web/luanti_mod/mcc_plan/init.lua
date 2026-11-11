-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Hologram nodes for zero-Velo planning purchases (meta on normal item stacks).

local HOLO_NAME = "mcc_plan:hologram"
local HOLO_GROUP = "mcc_plan_holo"
-- Solid collision for scaffolding while planning (still visually transparent).
local HOLO_WALKABLE = true
local HOLO_FULL_COLLISION = {
	type = "fixed",
	fixed = { -0.5, -0.5, -0.5, 0.5, 0.5, 0.5 },
}
-- Plain paths: colorize + opacity; complex modifier chains: opacity only (safe append).
local HOLO_TINT = "^[colorize:#44CCFF:200"
local HOLO_ALPHA = 140
local HOLO_OPACITY = "^[opacity:" .. tostring(HOLO_ALPHA)
-- Stored id is mccplan_gh_<original with ':' -> '_'>; register as ":mccplan_gh_..." (no mod context at on_mods_loaded).
local GHOST_ID_PREFIX = "mccplan_gh_"
local itemdefs_registration_open = true
local META_ORIGINAL = "mccplan_original"
local META_SHOP_TARGET = "mcc_shop_target_name"
local PLAN_STAIR_PLACE_DELAY = 0.12
local GHOST_SOURCE_PREFIXES = {
    "mcl_core:",
    "mcl_stairs:",
    "mcl_fences:",
    "mcl_doors:",
}
-- target_itemstring -> registered hologram nodename (shape clone)
local holo_variant_cache = {}
-- Must be captured at mod load; get_mod_storage() is not reliable in globalstep/shutdown.
local storage = core.get_mod_storage()

local api_post -- set by mcc_bridge
local server_shutting_down = false

local function floor_block(v)
    return math.floor(v + 0.5)
end

local function bridge_mod()
    return rawget(_G, "mcc_bridge")
end

local function plan_world_name()
    local bridge = bridge_mod()
    if bridge and bridge.mcc_world_name then
        return bridge.mcc_world_name()
    end
    return "mycyclingcity"
end

local PLAN_ERROR_CHAT = {
    no_region = "Keine geschützte Bauzone an dieser Position (Koordinaten prüfen).",
    not_member = "Du bist kein Mitglied dieser Bauzone.",
    no_funding_pool = "Kein Velo-Pool für die Planungsumwandlung.",
    insufficient_velos = "Nicht genug Velos im Pool.",
    missing_client_tx_id = "Interner Fehler (Transaktion).",
    http_unreachable = "Web-App nicht erreichbar.",
}

local function plan_error_message(data)
    if not data or type(data) ~= "table" then
        return "Planung: unbekannter Fehler."
    end
    local code = data.error or (data.ok == false and "http_error") or nil
    if code and PLAN_ERROR_CHAT[code] then
        return PLAN_ERROR_CHAT[code]
    end
    if code then
        return "Planung: " .. tostring(code)
    end
    return "Planung: fehlgeschlagen."
end

-- Session mode (build/play/watch) lives in mcc_bridge mod storage, not here.
local function get_stored_mode(name)
    local bridge = bridge_mod()
    if bridge and bridge.get_stored_mode then
        return bridge.get_stored_mode(name)
    end
    return "play"
end

mcc_plan = rawget(_G, "mcc_plan") or {}
rawset(_G, "mcc_plan", mcc_plan)

function mcc_plan.set_api_post(fn)
    api_post = fn
end

function mcc_plan.is_active(name)
    if not storage then
        return false
    end
    return storage:get_string("plan_active_" .. name) == "1"
end

function mcc_plan.set_active(name, on)
    if not storage then
        return
    end
    if on then
        storage:set_string("plan_active_" .. name, "1")
    else
        storage:set_string("plan_active_" .. name, "")
    end
    if mcc_plan.refresh_hud then
        mcc_plan.refresh_hud(name)
    end
end

function mcc_plan.is_autoconvert_on(name)
    if not storage then
        return false
    end
    return storage:get_string("plan_autoconvert_" .. name) == "1"
end

function mcc_plan.set_autoconvert_on(name, on)
    if not storage then
        return
    end
    if on then
        storage:set_string("plan_autoconvert_" .. name, "1")
    else
        storage:set_string("plan_autoconvert_" .. name, "")
    end
    if mcc_plan.refresh_hud then
        mcc_plan.refresh_hud(name)
    end
end

function mcc_plan.stack_has_plan_meta(stack)
    if not stack then
        return false
    end
    local meta = stack:get_meta()
    if meta and meta:get_string("mcc_plan") == "1" then
        return true
    end
    return false
end

local function read_plan_fields(stack)
    local meta = stack:get_meta()
    return {
        shop_item_id = meta:get_string("mcc_shop_item_id"),
        buy_price_velos = meta:get_string("mcc_buy_price_velos"),
        target_name = meta:get_string("mcc_target_name"),
    }
end

local function plan_stack_short_label(item_name)
    item_name = tostring(item_name or "?")
    local tail = item_name:match(":([^:]*)$") or item_name
    return tail:gsub("_", " ")
end

function mcc_plan.plan_item_description(meta_table, stack_name)
    meta_table = meta_table or {}
    local target = meta_table.mcc_target_name or stack_name or "?"
    local convert_velos = meta_table.mcc_buy_price_velos or "?"
    local label = plan_stack_short_label(target)
    return string.format(
        "Planung · %s · Kauf 0 Velo · Umwandlung %s Velo",
        label,
        tostring(convert_velos)
    )
end

function mcc_plan.apply_meta_to_stack(stack, meta_table)
    if not stack or stack:is_empty() or type(meta_table) ~= "table" then
        return stack
    end
    local im = stack:get_meta()
    local enriched = {}
    for k, v in pairs(meta_table) do
        enriched[k] = v
    end
    if enriched.mcc_plan == "1" and enriched.mcc_purchase_velos == nil then
        enriched.mcc_purchase_velos = "0"
    end
    for k, v in pairs(enriched) do
        im:set_string(tostring(k), tostring(v))
    end
    if enriched.mcc_plan == "1" then
        im:set_string("description", mcc_plan.plan_item_description(enriched, stack:get_name()))
    end
    return stack
end

function mcc_plan.stack_is_zero_velo_plan(stack)
    if not mcc_plan.stack_has_plan_meta(stack) then
        return false
    end
    local meta = stack:get_meta()
    if not meta then
        return false
    end
    local purchase = meta:get_string("mcc_purchase_velos")
    if purchase == "" then
        return true
    end
    return tonumber(purchase) == 0
end

local function mcl_stair_base_item_name(item_name)
    item_name = tostring(item_name or "")
    if item_name:sub(1, 12) ~= "mcl_stairs:" then
        return item_name
    end
    if item_name:match("_inner$") then
        return item_name:sub(1, -7)
    end
    if item_name:match("_outer$") then
        return item_name:sub(1, -7)
    end
    return item_name
end

--- Mineclonia door craft items place as paired bottom/top world nodes (_b_# / _t_#).
local function mcl_door_base_item_name(item_name)
    item_name = tostring(item_name or "")
    if item_name:sub(1, 10) ~= "mcl_doors:" then
        return item_name
    end
    local base = item_name:match("^(.+)_[bt]_%d+$")
    if base then
        return base
    end
    return item_name
end

local function mcl_shop_credit_item_name(item_name)
    return mcl_door_base_item_name(mcl_stair_base_item_name(item_name))
end

local function mcl_door_top_from_bottom(bottom_name)
    bottom_name = tostring(bottom_name or "")
    if bottom_name:match("_b_%d+$") then
        return bottom_name:gsub("_b_", "_t_", 1)
    end
    return nil
end

local function holo_meta_table(fields, target_name, param2)
    local shop_target = (fields and fields.target_name or "") ~= "" and fields.target_name
        or mcl_shop_credit_item_name(target_name)
    return {
        target_name = target_name,
        [META_ORIGINAL] = target_name,
        [META_SHOP_TARGET] = shop_target,
        target_param2 = tostring(param2 or 0),
        shop_item_id = fields.shop_item_id or "",
        buy_price_velos = fields.buy_price_velos or "1",
    }
end

local function is_plan_hologram(nodename)
    if not nodename or nodename == "" then
        return false
    end
    if nodename == HOLO_NAME then
        return true
    end
    if nodename:sub(1, #GHOST_ID_PREFIX) == GHOST_ID_PREFIX then
        return true
    end
    return core.get_item_group(nodename, HOLO_GROUP) > 0
end

local function safe_register_node(reg_spec, def)
    local stored = reg_spec
    if stored:sub(1, 1) == ":" then
        stored = stored:sub(2)
    end
    if core.registered_nodes[stored] then
        return true
    end
    local ok, err = pcall(core.register_node, reg_spec, def)
    if not ok then
        core.log("error", "[mcc_plan] register_node " .. tostring(reg_spec) .. ": " .. tostring(err))
        return false
    end
    return core.registered_nodes[stored] ~= nil
end

local function texture_is_tintable(name)
    if type(name) ~= "string" or name == "" then
        return false
    end
    if name:find("%^", 1, true) or name:find("(", 1, true) then
        return false
    end
    return true
end

local function holo_texture_name(name)
    if type(name) ~= "string" or name == "" then
        return name
    end
    if texture_is_tintable(name) then
        return name .. HOLO_TINT .. HOLO_OPACITY
    end
    return name .. HOLO_OPACITY
end

local function tint_tile_entry(entry)
    if type(entry) == "string" then
        return holo_texture_name(entry)
    end
    if type(entry) == "table" then
        local out = {}
        for k, v in pairs(entry) do
            if (k == "name" or k == "image") and type(v) == "string" then
                out[k] = holo_texture_name(v)
            else
                out[k] = v
            end
        end
        return out
    end
    return entry
end

local function tint_tiles(tiles)
    if type(tiles) == "string" then
        return holo_texture_name(tiles)
    end
    if type(tiles) == "table" then
        local out = {}
        for i = 1, #tiles do
            out[i] = tint_tile_entry(tiles[i])
        end
        return out
    end
    return tiles
end

local function tint_special(special)
    if type(special) ~= "table" then
        return special
    end
    local out = {}
    for i, st in ipairs(special) do
        if type(st) == "table" then
            local ct = {}
            for k, v in pairs(st) do
                if (k == "name" or k == "image") and type(v) == "string" then
                    ct[k] = holo_texture_name(v)
                else
                    ct[k] = v
                end
            end
            out[i] = ct
        else
            out[i] = st
        end
    end
    return out
end

-- Do not copy runtime callbacks; drops disabled for preview nodes.
local FORBID_HOLO_CLONE = {
    name = true,
    type = true,
    description = true,
    drop = true,
    after_place_node = true,
    after_dig_node = true,
    on_construct = true,
    on_destruct = true,
    on_timer = true,
    on_receive_fields = true,
    on_metadata_inventory_move = true,
    on_metadata_inventory_put = true,
    on_metadata_inventory_take = true,
    allow_metadata_inventory_move = true,
    allow_metadata_inventory_put = true,
    allow_metadata_inventory_take = true,
    on_blast = true,
    on_rightclick = true,
    on_punch = true,
    can_dig = true,
    on_dig = true,
    groups = true,
}

local BAD_HOLO_DRAW = {
    liquid = true,
    flowingliquid = true,
    airlike = true,
}

local function clone_def_table(v, depth)
    depth = depth or 0
    if type(v) ~= "table" or depth > 12 then
        return v
    end
    local out = {}
    for k, c in pairs(v) do
        if type(c) == "table" then
            out[k] = clone_def_table(c, depth + 1)
        elseif type(c) ~= "function" then
            out[k] = c
        end
    end
    return out
end

local function node_has_cloneable_visual(base)
    if not base then
        return false
    end
    local draw = base.drawtype or "normal"
    if BAD_HOLO_DRAW[draw] then
        return false
    end
    if base.tiles then
        return true
    end
    if type(base.mesh) == "string" and base.mesh ~= "" then
        return true
    end
    if base.node_box then
        return true
    end
    return false
end

local STRIP_CLONE_KEYS = {
    mesecons = true,
    tube = true,
    node_placement_prediction = true,
    digging = true,
    on_variant = true,
    variant = true,
    variants = true,
    node_dig_prediction = true,
    climbable = true,
    damage_per_second = true,
    liquidtype = true,
    liquid_alternative_flowing = true,
    liquid_alternative_source = true,
    liquid_viscosity = true,
    liquid_renewable = true,
    move_resistance = true,
    floodable = true,
}

local function is_forbidden_clone_key(k)
    if FORBID_HOLO_CLONE[k] or STRIP_CLONE_KEYS[k] then
        return true
    end
    if type(k) ~= "string" then
        return false
    end
    if k:sub(1, 3) == "on_" or k:sub(1, 6) == "after_" or k:sub(1, 6) == "allow_" then
        return true
    end
    return false
end

local STRUCTURE_CLONE_KEYS = {
    node_box = true,
    collision_box = true,
    selection_box = true,
    connects = true,
    connect_sides = true,
    wallmounted_rotate_vertical = true,
}

local VISUAL_CLONE_KEYS = {
    drawtype = true,
    visual_scale = true,
    tiles = true,
    special_tiles = true,
    overlay_tiles = true,
    mesh = true,
    textures = true,
    colors = true,
    palette = true,
    node_box = true,
    collision_box = true,
    selection_box = true,
    paramtype = true,
    paramtype2 = true,
    connects = true,
    connect_sides = true,
    wallmounted_rotate_vertical = true,
    wield_image = true,
    inventory_image = true,
}

local function apply_holo_dig_policy(def)
    def.groups = def.groups or {}
    def.groups.dig_immediate = 3
    def._mcl_hardness = 0
    return def
end

local function collision_box_is_usable(box)
    if type(box) ~= "table" then
        return false
    end
    if box.type == "fixed" and type(box.fixed) == "table" and #box.fixed >= 6 then
        return true
    end
    if box.type == "leveled" or box.type == "wallmounted" or box.type == "connected" then
        return true
    end
    return false
end

local function apply_holo_walk_policy(def)
    def.walkable = HOLO_WALKABLE
    if HOLO_WALKABLE and not collision_box_is_usable(def.collision_box) then
        local nb = def.node_box
        if type(nb) == "table" and nb.type == "fixed" and type(nb.fixed) == "table" then
            def.collision_box = clone_def_table(nb)
        else
            def.collision_box = clone_def_table(HOLO_FULL_COLLISION)
        end
    end
    return def
end

local function clone_minimal_holo_def(base, holo_can_dig_fn, holo_on_dig_fn)
    local def = { description = "Planung (Vorschau)" }
    for k, _ in pairs(VISUAL_CLONE_KEYS) do
        local v = base[k]
        if v == nil then
            -- skip
        elseif k == "tiles" or k == "overlay_tiles" then
            def[k] = tint_tiles(v)
        elseif k == "special_tiles" then
            def[k] = tint_special(v)
        elseif type(v) == "table" then
            def[k] = clone_def_table(v)
        else
            def[k] = v
        end
    end
    if def.drawtype == nil then
        def.drawtype = "normal"
    end
    def.drop = ""
    def.use_texture_alpha = "blend"
    def.sunlight_propagates = true
    def.pointable = true
    def.is_ground_content = false
    def.groups = { [HOLO_GROUP] = 1, handy = 1, building_block = 1 }
    def._mcl_blast_resistance = base._mcl_blast_resistance or 0.3
    def.can_dig = holo_can_dig_fn
    def.on_dig = holo_on_dig_fn
    return apply_holo_walk_policy(apply_holo_dig_policy(def))
end

local function clone_nodedef_for_holo_preview(base, holo_can_dig_fn, holo_on_dig_fn)
    local def = {}
    for k, v in pairs(base) do
        if not is_forbidden_clone_key(k) and type(v) ~= "function" then
            if k == "tiles" then
                def[k] = tint_tiles(v)
            elseif k == "special_tiles" then
                def[k] = tint_special(v)
            elseif k == "overlay_tiles" then
                def[k] = tint_tiles(v)
            elseif STRUCTURE_CLONE_KEYS[k] or type(v) == "table" then
                def[k] = clone_def_table(v)
            else
                def[k] = v
            end
        end
    end
    -- Preview must stay mineable with empty hand: strip Mineclonia dig tiers (pickaxey, …).
    local strip_dig = {
        pickaxey = true,
        axey = true,
        shovely = true,
        shearsy = true,
        shearsy_wool = true,
        shearsy_cobweb = true,
        swordy = true,
        swordy_wool = true,
        swordy_cobweb = true,
    }
    local g = {}
    for k, v in pairs(base.groups or {}) do
        if not strip_dig[k] then
            g[k] = v
        end
    end
    g[HOLO_GROUP] = 1
    g.handy = 1
    g.building_block = g.building_block or 1
    def.groups = g
    def.description = "Planung (Vorschau)"
    def.drop = ""
    def._mcl_blast_resistance = base._mcl_blast_resistance or 0.3
    if def.sunlight_propagates == nil then
        def.sunlight_propagates = true
    end
    if def.paramtype == nil then
        def.paramtype = "light"
    end
    def.use_texture_alpha = "blend"
    def.sunlight_propagates = true
    def.pointable = true
    def.is_ground_content = false
    def.can_dig = holo_can_dig_fn
    def.on_dig = holo_on_dig_fn
    return apply_holo_walk_policy(apply_holo_dig_policy(def))
end

local function ghost_item_id(original)
    original = tostring(original or "")
    if original == "" then
        return ""
    end
    return GHOST_ID_PREFIX .. original:gsub(":", "_")
end

local function ghost_register_spec(original)
    local id = ghost_item_id(original)
    if id == "" then
        return nil
    end
    return ":" .. id
end

local function ghost_node_is_registered(stored_name)
    if core.registered_nodes[stored_name] then
        return true
    end
    if stored_name:sub(1, 1) ~= ":" then
        return core.registered_nodes[":" .. stored_name] ~= nil
    end
    return false
end

local function should_mirror_as_ghost(nodename)
    if not nodename or nodename:sub(1, 9) == "mcc_plan:" then
        return false
    end
    for _, prefix in ipairs(GHOST_SOURCE_PREFIXES) do
        if nodename:sub(1, #prefix) == prefix then
            return true
        end
    end
    return false
end

local function node_def_exists(nodename)
    return nodename and nodename ~= "" and core.registered_nodes[nodename] ~= nil
end

--- Mineclonia picks inner/outer stair node names on place; shop meta may name the other variant.
local function resolve_plan_shape_name(fields, newnode)
    local placed = (newnode and newnode.name) or ""
    local meta_target = (fields and fields.target_name) or ""
    if placed == "" or placed == "air" then
        return (meta_target ~= "" and meta_target) or placed
    end
    if meta_target == "" then
        return placed
    end
    if placed:match("^mcl_stairs:stair_.+_(inner|outer)$") then
        return placed
    end
    if placed:sub(1, 10) == "mcl_doors:" and node_def_exists(placed) then
        return placed
    end
    if placed ~= meta_target and should_mirror_as_ghost(placed) then
        return placed
    end
    return meta_target
end

-- Last wielded plan stack (on_placenode often receives an empty stack after the final item).
local plan_wield_snapshot = {}

local function plan_fields_from_place(player_name, itemstack)
    local fields = read_plan_fields(itemstack)
    if (fields.target_name or "") ~= "" then
        return fields
    end
    local snap = plan_wield_snapshot[player_name]
    if snap and snap ~= "" then
        local cached = ItemStack(snap)
        if mcc_plan.stack_has_plan_meta(cached) then
            return read_plan_fields(cached)
        end
    end
    return fields
end

local function plan_refund_stack(fields, fallback_node_name)
    local shop_target = fields and fields.target_name or ""
    if shop_target == "" then
        shop_target = mcl_shop_credit_item_name(fallback_node_name or "")
    end
    if shop_target == "" or shop_target == "air" then
        return nil
    end
    local stack = ItemStack(shop_target .. " 1")
    return mcc_plan.apply_meta_to_stack(stack, {
        mcc_plan = "1",
        mcc_shop_item_id = fields and fields.shop_item_id or "",
        mcc_buy_price_velos = fields and fields.buy_price_velos or "1",
        mcc_target_name = shop_target,
        mcc_purchase_velos = "0",
    })
end

local function give_item_to_player(placer, stack)
    if not placer or not placer:is_player() or not stack or stack:is_empty() then
        return
    end
    local inv = placer:get_inventory()
    if not inv then
        return
    end
    local left = inv:add_item("main", stack)
    if not left:is_empty() then
        local pos = placer:get_pos()
        if pos then
            core.add_item(pos, left)
        end
    end
end

-- Mineclonia/Luanti HUD wraps long infotext — keep one line (~40 chars typical usable width).
local INFO_HOVER_MAX = 42
local INFO_CHAT_MAX = 78

local function short_item_label(full)
    full = tostring(full or "?")
    local tail = full:match(":([^:]*)$") or full
    tail = tail:gsub("_", " ")
    if #tail > 18 then
        return tail:sub(1, 15) .. "…"
    end
    return tail
end

--- mode: short_label true = tail of id only for infotext; false = full target string for chat.
local function hologram_info_line(meta, max_len, short_label)
    max_len = max_len or INFO_HOVER_MAX
    short_label = short_label ~= false
    if not meta then
        return "Plan ?"
    end
    local target = meta:get_string(META_ORIGINAL)
    if target == "" then
        target = meta:get_string("target_name")
    end
    if target == "" then
        target = "?"
    end
    local label = short_label and short_item_label(target) or target
    local sid = meta:get_string("shop_item_id")
    local price = meta:get_string("buy_price_velos")
    if price == "" then
        price = "?"
    end
    local line
    if sid ~= "" then
        line = string.format("Plan %s #%s %sV", label, sid, price)
    else
        line = string.format("Plan %s %sV", label, price)
    end
    if #line > max_len then
        line = line:sub(1, max_len - 1) .. "…"
    end
    return line
end

--- Single line for HUD hover (must be after hologram_info_line; LBM calls this at load).
local function hologram_infotext_line(meta)
    return hologram_info_line(meta, INFO_HOVER_MAX, true)
end

local function raycast_hologram_under_crosshair(player, max_dist)
    max_dist = max_dist or 8
    local pos = player:get_pos()
    if not pos then
        return nil
    end
    local eye = { x = pos.x, y = pos.y + 1.62, z = pos.z }
    local dir = player:get_look_dir()
    local far = vector.add(eye, vector.multiply(dir, max_dist))
    local ray = core.raycast(eye, far, false, false)
    for pointed in ray do
        if pointed.type == "node" then
            return pointed.under
        end
    end
    return nil
end

local function register_placed_api(player_name, pos, target_name, param2, fields)
    if not api_post then
        return
    end
    api_post("/api/luanti/plan/placed/", {
        player = player_name,
        world = plan_world_name(),
        x = pos.x,
        y = pos.y,
        z = pos.z,
        target_name = target_name,
        param2 = param2 or 0,
        shop_item_id = tonumber(fields.shop_item_id),
        buy_price_velos = tonumber(fields.buy_price_velos) or 1,
    }, function(ok, data)
        if ok and data and data.ok then
            if mcc_plan.poll_summary then
                mcc_plan.poll_summary(player_name)
            end
        else
            core.chat_send_player(
                player_name,
                core.colorize("#FFAA66", "Plan-Ledger: " .. plan_error_message(data))
            )
        end
    end)
end

local function register_removed_api(pos, player_name)
    if not api_post then
        return
    end
    api_post("/api/luanti/plan/removed/", {
        world = plan_world_name(),
        x = pos.x,
        y = pos.y,
        z = pos.z,
    }, function(ok, data)
        if ok and data and data.ok and player_name and mcc_plan.poll_summary then
            mcc_plan.poll_summary(player_name)
        end
    end)
end

local function hologram_can_dig(pos, player)
    if not player or not player:is_player() then
        return true
    end
    return not player:get_player_control().sneak
end

function mcc_plan.clear_hologram_at(pos)
    if not pos then
        return false
    end
    local node = core.get_node(pos)
    if not is_plan_hologram(node.name) then
        return false
    end
    core.set_node(pos, { name = "air" })
    return true
end

function mcc_plan.remove_hologram_at(pos, digger, opts)
    opts = opts or {}
    local give_item = opts.give_item ~= false
    local register_api = opts.register_api ~= false
    if not pos then
        return false
    end
    local node = core.get_node(pos)
    if not is_plan_hologram(node.name) then
        return false
    end
    local meta = core.get_meta(pos)
    local shape = meta:get_string(META_ORIGINAL)
    if shape == "" then
        shape = meta:get_string("target_name")
    end
    if give_item and digger and digger:is_player() then
        local shop_target = meta:get_string(META_SHOP_TARGET)
        if shop_target == "" then
            shop_target = mcl_shop_credit_item_name(shape)
        end
        if shop_target == "" then
            shop_target = "mcl_core:stone"
        end
        local fields = {
            shop_item_id = meta:get_string("shop_item_id"),
            buy_price_velos = meta:get_string("buy_price_velos"),
            target_name = shop_target,
        }
        local stack = plan_refund_stack(
            {
                shop_item_id = fields.shop_item_id,
                buy_price_velos = fields.buy_price_velos,
                target_name = shop_target,
            },
            shop_target
        )
        if not stack then
            stack = ItemStack(shop_target .. " 1")
        end
        local inv = digger:get_inventory()
        if inv then
            local left = inv:add_item("main", stack)
            if not left:is_empty() then
                core.add_item(pos, left)
            end
        end
    end
    if register_api then
        local pname = digger and digger:is_player() and digger:get_player_name() or nil
        register_removed_api(pos, pname)
    end
    core.set_node(pos, { name = "air" })
    if shape and shape:match("^mcl_doors:.+_b_%d+$") then
        local top_pos = { x = pos.x, y = pos.y + 1, z = pos.z }
        local top_node = core.get_node(top_pos)
        if is_plan_hologram(top_node.name) then
            mcc_plan.remove_hologram_at(top_pos, digger, {
                give_item = false,
                register_api = false,
            })
        end
    elseif shape and shape:match("^mcl_doors:.+_t_%d+$") then
        local bot_pos = { x = pos.x, y = pos.y - 1, z = pos.z }
        local bot_node = core.get_node(bot_pos)
        if is_plan_hologram(bot_node.name) then
            mcc_plan.remove_hologram_at(bot_pos, digger, {
                give_item = false,
                register_api = false,
            })
        end
    end
    return true
end

local function hologram_on_dig(pos, node, digger)
    if not digger or not digger:is_player() then
        return
    end
    return mcc_plan.remove_hologram_at(pos, digger, { give_item = true, register_api = true })
end

--- Fast static check (no registration). May disagree with in-game if register_node fails.
function mcc_plan.preview_clone_tier(target)
    target = tostring(target or "")
    if target == "" or not core.registered_nodes[target] then
        return "na"
    end
    local base = core.registered_nodes[target]
    local draw = base.drawtype or "normal"
    if BAD_HOLO_DRAW[draw] then
        return "fallback"
    end
    if not node_has_cloneable_visual(base) then
        return "fallback"
    end
    return "shape"
end

--- Registers ghost variant when needed; reports real in-game clone tier for shop audit.
function mcc_plan.verify_clone_tier(target)
    target = tostring(target or "")
    if target == "" or not core.registered_nodes[target] then
        return "na", "not_a_node"
    end
    local base = core.registered_nodes[target]
    local draw = tostring(base.drawtype or "normal")
    local holo = mcc_plan.ensure_hologram_variant(target)
    if holo == HOLO_NAME then
        return "fallback", "drawtype=" .. draw
    end
    return "shape", holo
end

function mcc_plan.ensure_hologram_variant(target)
    target = tostring(target or "")
    if target == "" then
        return HOLO_NAME
    end
    local cached = holo_variant_cache[target]
    if cached then
        return cached
    end
    local base = core.registered_nodes[target]
    if not base or not node_has_cloneable_visual(base) then
        core.log("warning", "[mcc_plan] no visual clone for " .. target .. " — fallback cube")
        return HOLO_NAME
    end
    local stored_name = ghost_item_id(target)
    if stored_name == "" then
        return HOLO_NAME
    end
    if ghost_node_is_registered(stored_name) then
        holo_variant_cache[target] = stored_name
        return stored_name
    end
    if not itemdefs_registration_open then
        core.log(
            "warning",
            "[mcc_plan] ghost missing for "
                .. target
                .. " (register after load forbidden) — fallback cube"
        )
        return HOLO_NAME
    end
    local reg_spec = ghost_register_spec(target)
    if not reg_spec then
        return HOLO_NAME
    end
    local def = clone_nodedef_for_holo_preview(base, hologram_can_dig, hologram_on_dig)
    local registered = safe_register_node(reg_spec, def) and ghost_node_is_registered(stored_name)
    if not registered then
        def = clone_minimal_holo_def(base, hologram_can_dig, hologram_on_dig)
        registered = safe_register_node(reg_spec, def) and ghost_node_is_registered(stored_name)
    end
    if registered then
        holo_variant_cache[target] = stored_name
        return stored_name
    end
    core.log("error", "[mcc_plan] ghost register failed for " .. target .. " — fallback cube")
    return HOLO_NAME
end

function mcc_plan.finalize_node(pos, opts)
    if type(pos) ~= "table" or not pos.x then
        return false, "bad_pos"
    end
    local node = core.get_node(pos)
    if not is_plan_hologram(node.name) and node.name ~= "ignore" then
        return false, "not_ghost"
    end
    opts = opts or {}
    local meta = core.get_meta(pos)
    local meta_shape = meta:get_string(META_ORIGINAL)
    if meta_shape == "" then
        meta_shape = meta:get_string("target_name")
    end
    local target = tostring(opts.target_name or "")
    if meta_shape ~= "" and meta_shape:sub(1, 12) == "mcl_stairs:" then
        target = meta_shape
    elseif target == "" then
        target = meta_shape
    end
    if target == "" then
        return false, "no_target"
    end
    local param2 = opts.param2
    if param2 == nil then
        param2 = tonumber(meta:get_string("target_param2")) or node.param2 or 0
    end
    core.set_node(pos, { name = target, param2 = param2 })
    meta = core.get_meta(pos)
    meta:set_string("infotext", "")
    return true
end

function mcc_plan.set_hologram_node(pos, shape_name, param2, fields)
    shape_name = tostring(shape_name or "")
    if shape_name == "" then
        return
    end
    local holo_nodename = mcc_plan.ensure_hologram_variant(shape_name)
    core.set_node(pos, { name = holo_nodename, param2 = param2 or 0 })
    local meta = core.get_meta(pos)
    local tbl = holo_meta_table(fields or {}, shape_name, param2)
    for k, v in pairs(tbl) do
        meta:set_string(k, tostring(v))
    end
    meta:set_string("infotext", hologram_infotext_line(meta))
end

local function send_hologram_info(player, pos)
    if not player or not pos then
        return
    end
    local node = core.get_node(pos)
    if not is_plan_hologram(node.name) then
        core.chat_send_player(player:get_player_name(), "Kein Plan-Hologramm im Blick.")
        return
    end
    core.chat_send_player(
        player:get_player_name(),
        hologram_info_line(core.get_meta(pos), INFO_CHAT_MAX, false)
    )
end

core.register_node(HOLO_NAME, {
    description = "Planung: Shift+Linksklick = Infos · sonst abbauen · /mccplan look",
    drawtype = "glasslike",
    tiles = { "default_glass.png^[colorize:#44CCFF:80" },
    use_texture_alpha = "blend",
    paramtype = "light",
    sunlight_propagates = true,
    is_ground_content = false,
    walkable = HOLO_WALKABLE,
    collision_box = HOLO_FULL_COLLISION,
    pointable = true,
    groups = { [HOLO_GROUP] = 1, handy = 1, glass = 1, building_block = 1, dig_immediate = 3 },
    _mcl_hardness = 0,
    _mcl_blast_resistance = 0.3,
    can_dig = hologram_can_dig,
    on_dig = hologram_on_dig,
})

-- Info on Shift+punch: must use global callback (reliable with empty hand + all tools).
core.register_on_punchnode(function(pos, node, puncher, pointed_thing)
    if not is_plan_hologram(node.name) then
        return
    end
    if not puncher or not puncher:is_player() then
        return
    end
    if not puncher:get_player_control().sneak then
        return
    end
    send_hologram_info(puncher, pos)
end)

-- Refresh compact infotext on existing map (one-time per node when chunk is loaded).
core.register_lbm({
    name = HOLO_NAME .. "_infotext_compact_v10",
    nodenames = { HOLO_NAME },
    run_at_every_load = false,
    action = function(pos)
        local meta = core.get_meta(pos)
        meta:set_string("infotext", hologram_infotext_line(meta))
    end,
})

core.register_globalstep(function()
    for _, player in ipairs(core.get_connected_players()) do
        local name = player:get_player_name()
        if mcc_plan.is_active(name) then
            local wield = player:get_wielded_item()
            if mcc_plan.stack_has_plan_meta(wield) then
                plan_wield_snapshot[name] = wield:to_string()
            end
        else
            plan_wield_snapshot[name] = nil
        end
    end
end)

core.register_on_placenode(function(pos, newnode, placer, oldnode, itemstack, pointed_thing)
    if not placer or not placer:is_player() then
        return
    end
    local name = placer:get_player_name()
    local active = mcc_plan.is_active(name)
    local had_plan = mcc_plan.stack_has_plan_meta(itemstack)
    if not had_plan and active then
        local fields = plan_fields_from_place(name, itemstack)
        had_plan = (fields.target_name or "") ~= ""
    end
    if not active then
        had_plan = mcc_plan.stack_has_plan_meta(itemstack)
    end
    if active and had_plan then
        local fields = plan_fields_from_place(name, itemstack)
        local saved_old = oldnode
        plan_wield_snapshot[name] = nil
        core.after(PLAN_STAIR_PLACE_DELAY, function()
            local cur = core.get_node(pos)
            if cur.name == "air" then
                return
            end
            if is_plan_hologram(cur.name) then
                return
            end
            -- Door top half: paired hologram is created from the bottom callback only.
            if cur.name:match("^mcl_doors:.+_t_%d+$") then
                return
            end
            -- Corner stairs swap to _inner/_outer in after_place_node; read node after that runs.
            local shape_name = resolve_plan_shape_name(fields, cur)
            if not node_def_exists(shape_name) then
                core.log(
                    "warning",
                    "[mcc_plan] hologram shape missing: " .. tostring(shape_name)
                )
                core.set_node(pos, saved_old)
                give_item_to_player(placer, plan_refund_stack(fields, cur.name))
                core.chat_send_player(
                    name,
                    core.colorize("#FF6655", "Plan-Hologramm fehlgeschlagen — Block zurückgegeben.")
                )
                return
            end
            local p2 = cur.param2 or 0
            if shape_name:match("^mcl_doors:.+_b_%d+$") then
                local top_name = mcl_door_top_from_bottom(shape_name)
                local top_pos = { x = pos.x, y = pos.y + 1, z = pos.z }
                mcc_plan.set_hologram_node(pos, shape_name, p2, fields)
                if top_name and node_def_exists(top_name) then
                    local top_cur = core.get_node(top_pos)
                    local tp2 = top_cur.param2 or p2
                    mcc_plan.set_hologram_node(top_pos, top_name, tp2, fields)
                end
                register_placed_api(name, pos, shape_name, p2, fields)
                return
            end
            mcc_plan.set_hologram_node(pos, shape_name, p2, fields)
            register_placed_api(name, pos, shape_name, p2, fields)
        end)
    elseif not active and had_plan then
        local fields = plan_fields_from_place(name, itemstack)
        core.after(0, function()
            core.set_node(pos, oldnode)
            give_item_to_player(
                placer,
                plan_refund_stack(fields, newnode and newnode.name) or itemstack
            )
            core.chat_send_player(
                name,
                core.colorize("#FFEE55", "Planung einschalten (/mccplan on), um Hologramme zu setzen.")
            )
        end)
    end
    -- Plan AN + echte Blöcke: durchlassen (kein Zurücksetzen mehr).
end)

function mcc_plan.register_all_ghost_mirrors()
    local ok_n, fail_n = 0, 0
    for nodename in pairs(core.registered_nodes) do
        if should_mirror_as_ghost(nodename) then
            if mcc_plan.ensure_hologram_variant(nodename) == HOLO_NAME then
                fail_n = fail_n + 1
            else
                ok_n = ok_n + 1
            end
        end
    end
    core.log(
        "action",
        "[mcc_plan] ghost mirrors pre-registered ok="
            .. tostring(ok_n)
            .. " fallback="
            .. tostring(fail_n)
    )
end

core.register_on_mods_loaded(function()
    mcc_plan.register_all_ghost_mirrors()
    core.after(0, function()
        itemdefs_registration_open = false
    end)
end)

-- Second pass after init.lua of all mods (mcl_stairs etc.) while register_node is still allowed.
mcc_plan.register_all_ghost_mirrors()

local materialize_job_id = 0
local DEFAULT_CONVERT_LAYER_DELAY = tonumber(core.settings:get("mcc_plan.convert_layer_delay")) or 0.35
local DEFAULT_CONVERT_BLOCK_DELAY = tonumber(core.settings:get("mcc_plan.convert_block_delay")) or 0.0

local function sort_materialize_blocks(blocks)
    table.sort(blocks, function(a, b)
        local ay = tonumber(a.y) or 0
        local by = tonumber(b.y) or 0
        if ay ~= by then
            return ay < by
        end
        local ax = tonumber(a.x) or 0
        local bx = tonumber(b.x) or 0
        if ax ~= bx then
            return ax < bx
        end
        return (tonumber(a.z) or 0) < (tonumber(b.z) or 0)
    end)
    return blocks
end

local function group_blocks_by_y(blocks)
    local layers = {}
    for _, block in ipairs(blocks) do
        local ly = math.floor(tonumber(block.y) or 0)
        local last = layers[#layers]
        if not last or last.y ~= ly then
            layers[#layers + 1] = { y = ly, blocks = { block } }
        else
            last.blocks[#last.blocks + 1] = block
        end
    end
    return layers
end

function mcc_plan.materialize_blocks_staggered(blocks, opts)
    if type(blocks) ~= "table" or #blocks == 0 then
        return
    end
    opts = opts or {}
    local fx_stagger = opts.fx_stagger
    if fx_stagger == nil then
        fx_stagger = true
    end
    if not fx_stagger or #blocks <= 1 then
        for _, block in ipairs(blocks) do
            mcc_plan.materialize_block(block)
        end
        return
    end
    local layer_delay = tonumber(opts.layer_delay) or DEFAULT_CONVERT_LAYER_DELAY
    local block_delay = tonumber(opts.block_delay) or DEFAULT_CONVERT_BLOCK_DELAY
    if layer_delay < 0 then
        layer_delay = 0
    end
    if block_delay < 0 then
        block_delay = 0
    end

    local sorted = {}
    for i = 1, #blocks do
        sorted[i] = blocks[i]
    end
    sort_materialize_blocks(sorted)
    local layers = group_blocks_by_y(sorted)

    materialize_job_id = materialize_job_id + 1
    local job = materialize_job_id
    local t = 0
    for layer_idx, layer in ipairs(layers) do
        if layer_idx > 1 then
            t = t + layer_delay
        end
        if block_delay > 0 then
            for bi, block in ipairs(layer.blocks) do
                local delay = t + (bi - 1) * block_delay
                core.after(delay, function()
                    if materialize_job_id ~= job then
                        return
                    end
                    mcc_plan.materialize_block(block)
                end)
            end
            if #layer.blocks > 0 then
                t = t + (#layer.blocks - 1) * block_delay
            end
        else
            local layer_t = t
            local layer_blocks = layer.blocks
            core.after(layer_t, function()
                if materialize_job_id ~= job then
                    return
                end
                for _, block in ipairs(layer_blocks) do
                    mcc_plan.materialize_block(block)
                end
            end)
        end
    end
end

function mcc_plan.materialize_block(entry)
    if type(entry) ~= "table" then
        return
    end
    local pos = {
        x = tonumber(entry.x),
        y = tonumber(entry.y),
        z = tonumber(entry.z),
    }
    local target = tostring(entry.target_name or "")
    if not pos.x or target == "" then
        return
    end
    local p2 = tonumber(entry.param2)
    local ok = mcc_plan.finalize_node(pos, {
        target_name = target,
        param2 = p2,
    })
    if not ok then
        return
    end
    if target:match("^mcl_doors:.+_b_%d+$") then
        local top_name = mcl_door_top_from_bottom(target)
        if top_name and node_def_exists(top_name) then
            local top_pos = { x = pos.x, y = pos.y + 1, z = pos.z }
            local top_node = core.get_node(top_pos)
            if is_plan_hologram(top_node.name) then
                mcc_plan.finalize_node(top_pos, {
                    target_name = top_name,
                    param2 = top_node.param2 or p2,
                })
            elseif top_node.name == "air" then
                core.set_node(top_pos, { name = top_name, param2 = p2 or 0 })
            end
        end
    end
    if core.add_particlespawner then
        core.add_particlespawner({
            amount = 12,
            time = 0.6,
            minpos = vector.new(pos.x - 0.4, pos.y - 0.2, pos.z - 0.4),
            maxpos = vector.new(pos.x + 0.4, pos.y + 1.2, pos.z + 0.4),
            minvel = vector.new(-0.5, 0.5, -0.5),
            maxvel = vector.new(0.5, 2, 0.5),
            minexptime = 0.3,
            maxexptime = 0.8,
            minsize = 0.5,
            maxsize = 1.2,
            collisiondetection = false,
            -- mcl_particles_spark.png does not ship with Mineclonia; crit is in CORE/mcl_particles.
            texture = "mcl_particles_crit.png^[colorize:#55EEAA:200",
        })
    end
end

local hud_ids = {}
local hud_cache = {}
local hud_tick = 0
local autoconvert_tick = 0
local autoconvert_pending = {}
local autoconvert_chat_throttle = {}
local DEFAULT_AUTOCONVERT_INTERVAL = tonumber(core.settings:get("mcc_plan.autoconvert_interval")) or 5
local AUTOCONVERT_MAX_BLOCKS = tonumber(core.settings:get("mcc_plan.autoconvert_max_blocks")) or 4
local AUTOCONVERT_CHAT_COOLDOWN = 30
-- Screen position 0..1 (0 = top); was 0.88 — too close to hotbar.
local PLAN_HUD_Y = 0.82

local function player_feet_pos(player)
    local pos = player:get_pos()
    if not pos then
        return nil
    end
    return {
        x = floor_block(pos.x),
        y = floor_block(pos.y),
        z = floor_block(pos.z),
    }
end

local function should_show_zone_hud(name)
    return get_stored_mode(name) == "build"
end

local BUILD_MODE_MSG = "Nur im Bau-Modus (Session)."

local function require_build_session(name)
    if get_stored_mode(name) ~= "build" then
        return false, BUILD_MODE_MSG
    end
    return true
end

function mcc_plan.refresh_hud(name)
    local player = core.get_player_by_name(name)
    if not player or not should_show_zone_hud(name) then
        if hud_ids[name] then
            player = core.get_player_by_name(name)
            if player then
                player:hud_remove(hud_ids[name])
            end
            hud_ids[name] = nil
        end
        return
    end
    local text = hud_cache[name]
    if not text or text == "" then
        text = mcc_plan.is_active(name) and "Planung · …" or "Bauzone · …"
    end
    if not hud_ids[name] then
        hud_ids[name] = player:hud_add({
            type = "text",
            position = { x = 0.5, y = PLAN_HUD_Y },
            offset = { x = 0, y = 0 },
            alignment = { x = 0, y = 0 },
            scale = { x = 100, y = 100 },
            text = text,
            number = 0xFFFFFF,
        })
    else
        player:hud_change(hud_ids[name], "position", { x = 0.5, y = PLAN_HUD_Y })
        player:hud_change(hud_ids[name], "text", text)
    end
end

local function format_zone_summary_line(data)
    if not data or not data.ok then
        return nil
    end
    return string.format(
        "%s · %d Hologr. · Umwandlung %d Vel · Pool %d Vel",
        tostring(data.display_name or "?"),
        tonumber(data.planned_count) or 0,
        tonumber(data.total_velos_planned) or 0,
        tonumber(data.available_velos) or 0
    )
end

local function format_summary_chat(st_on_off, data, ok)
    if not ok or not data or not data.ok then
        return "Planung: "
            .. st_on_off
            .. " — "
            .. plan_error_message(data)
    end
    local zone = format_zone_summary_line(data)
    return "Planung: " .. st_on_off .. " · " .. (zone or "?")
end

function mcc_plan.poll_summary(name)
    if not api_post or not should_show_zone_hud(name) then
        return
    end
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local feet = player_feet_pos(player)
    if not feet then
        return
    end
    api_post("/api/luanti/plan/summary/", {
        player = name,
        world = plan_world_name(),
        x = feet.x,
        y = feet.y,
        z = feet.z,
    }, function(ok, data)
        if ok and data and data.ok then
            local zone = format_zone_summary_line(data)
            local prefix
            if mcc_plan.is_autoconvert_on(name) then
                prefix = "Auto-Umw. · "
            elseif mcc_plan.is_active(name) then
                prefix = "Planung AN · "
            else
                prefix = "Bauzone · "
            end
            hud_cache[name] = prefix .. (zone or "…")
        else
            hud_cache[name] = "Bauzone · " .. plan_error_message(data)
        end
        mcc_plan.refresh_hud(name)
    end)
end

local poll_summary = mcc_plan.poll_summary

local function autoconvert_throttled_chat(name, kind, message)
    local now = core.get_us_time and (core.get_us_time() / 1000000) or os.time()
    local row = autoconvert_chat_throttle[name]
    if not row then
        row = {}
        autoconvert_chat_throttle[name] = row
    end
    local last = row[kind] or 0
    if now - last < AUTOCONVERT_CHAT_COOLDOWN then
        return
    end
    row[kind] = now
    core.chat_send_player(name, message)
end

local function run_autoconvert_tick(name)
    if not api_post or not mcc_plan.is_autoconvert_on(name) then
        return
    end
    if not should_show_zone_hud(name) then
        mcc_plan.set_autoconvert_on(name, false)
        return
    end
    if autoconvert_pending[name] then
        return
    end
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local feet = player_feet_pos(player)
    if not feet then
        return
    end
    autoconvert_pending[name] = true
    api_post("/api/luanti/plan/summary/", {
        player = name,
        world = plan_world_name(),
        x = feet.x,
        y = feet.y,
        z = feet.z,
    }, function(ok, data)
        if not ok or not data or not data.ok then
            autoconvert_pending[name] = nil
            autoconvert_throttled_chat(name, "error", plan_error_message(data))
            return
        end
        local planned = tonumber(data.planned_count) or 0
        local pool = tonumber(data.available_velos) or 0
        if planned <= 0 then
            autoconvert_pending[name] = nil
            mcc_plan.set_autoconvert_on(name, false)
            core.chat_send_player(name, "Auto-Umwandlung AUS — keine Hologramme in der Zone.")
            poll_summary(name)
            return
        end
        if pool <= 0 then
            autoconvert_pending[name] = nil
            return
        end
        local region_id = data.region_id
        if not region_id or region_id == "" then
            autoconvert_pending[name] = nil
            autoconvert_throttled_chat(name, "error", plan_error_message(data))
            return
        end
        local max_n = AUTOCONVERT_MAX_BLOCKS
        if max_n > 32 then
            max_n = 32
        end
        if max_n < 1 then
            max_n = 1
        end
        local tx = name .. "-autoconv-" .. tostring(core.get_us_time and core.get_us_time() or os.time())
        api_post("/api/luanti/plan/convert/", {
            player = name,
            region_id = region_id,
            client_tx_id = tx,
            max_count = max_n,
            mode = "manual",
        }, function(ok2, data2)
            autoconvert_pending[name] = nil
            if ok2 and data2 and data2.ok then
                local conv = tonumber(data2.converted) or 0
                if conv > 0 then
                    autoconvert_throttled_chat(
                        name,
                        "success",
                        "Auto-Umwandlung: " .. tostring(conv) .. " Block/Blöcke real."
                    )
                end
                poll_summary(name)
            else
                autoconvert_throttled_chat(name, "error", plan_error_message(data2))
            end
        end)
    end)
end

local function send_status_to_chat(name)
    local st = mcc_plan.is_active(name) and "AN" or "AUS"
    local auto_st = mcc_plan.is_autoconvert_on(name) and "AN" or "AUS"
    if not api_post then
        return true,
            "Planung: "
                .. st
                .. " · Auto-Umw.: "
                .. auto_st
                .. " (Bridge offline)"
    end
    local player = core.get_player_by_name(name)
    local feet = player and player_feet_pos(player)
    if not feet then
        return true, "Planung: " .. st
    end
    api_post("/api/luanti/plan/summary/", {
        player = name,
        world = plan_world_name(),
        x = feet.x,
        y = feet.y,
        z = feet.z,
    }, function(ok, data)
        local line = format_summary_chat(st, data, ok)
        core.chat_send_player(name, line .. " · Auto-Umw.: " .. auto_st)
    end)
    return true, "Planung: " .. st .. " · Auto-Umw.: " .. auto_st .. " — Zoneninfo …"
end

local function bridge_sync_inventory(player)
    local bridge = bridge_mod()
    if bridge and bridge.sync_player_inventory_now then
        bridge.sync_player_inventory_now(player)
    end
end

--- Remove plan-meta stacks from main inventory. mode: "wield", "all", or stack count limit for "all".
function mcc_plan.discard_plan_items(player, mode)
    if not player or not player:is_player() then
        return 0, "no_player"
    end
    local inv = player:get_inventory()
    if not inv then
        return 0, "no_inv"
    end
    mode = tostring(mode or "wield")
    local removed = 0
    if mode == "wield" then
        local idx = player:get_wield_index() or 1
        local stack = inv:get_stack("main", idx)
        if mcc_plan.stack_has_plan_meta(stack) then
            removed = stack:get_count()
            inv:set_stack("main", idx, ItemStack(""))
        end
    else
        for i = 1, inv:get_size("main") do
            local stack = inv:get_stack("main", i)
            if mcc_plan.stack_has_plan_meta(stack) then
                removed = removed + stack:get_count()
                inv:set_stack("main", i, ItemStack(""))
            end
        end
    end
    if removed > 0 then
        bridge_sync_inventory(player)
    end
    return removed, removed > 0 and "ok" or "none"
end

core.register_on_shutdown(function()
    server_shutting_down = true
end)

core.register_on_leaveplayer(function(player)
    if not player or not player:is_player() then
        return
    end
    local name = player:get_player_name()
    mcc_plan.set_autoconvert_on(name, false)
    autoconvert_pending[name] = nil
    autoconvert_chat_throttle[name] = nil
end)

core.register_globalstep(function(dtime)
    if server_shutting_down or not storage then
        return
    end
    hud_tick = hud_tick + dtime
    autoconvert_tick = autoconvert_tick + dtime
    local hud_due = hud_tick >= 8
    local autoconvert_due = autoconvert_tick >= DEFAULT_AUTOCONVERT_INTERVAL
    if not hud_due and not autoconvert_due then
        return
    end
    if hud_due then
        hud_tick = 0
    end
    if autoconvert_due then
        autoconvert_tick = 0
    end
    for _, player in ipairs(core.get_connected_players()) do
        local name = player:get_player_name()
        if should_show_zone_hud(name) then
            if hud_due then
                poll_summary(name)
            end
            if autoconvert_due and mcc_plan.is_autoconvert_on(name) then
                run_autoconvert_tick(name)
            end
        else
            if mcc_plan.is_autoconvert_on(name) then
                mcc_plan.set_autoconvert_on(name, false)
            end
            hud_cache[name] = nil
            if hud_due then
                mcc_plan.refresh_hud(name)
            end
        end
    end
end)

local function run_plan_clear_from_feet(name, max_count)
    if not api_post then
        return false, "Bridge offline."
    end
    local player = core.get_player_by_name(name)
    local feet = player and player_feet_pos(player)
    if not feet then
        return false, "Keine Position."
    end
    api_post("/api/luanti/plan/summary/", {
        player = name,
        world = plan_world_name(),
        x = feet.x,
        y = feet.y,
        z = feet.z,
    }, function(ok, data)
        if not ok or not data or not data.region_id then
            core.chat_send_player(name, plan_error_message(data))
            return
        end
        api_post("/api/luanti/plan/clear/", {
            player = name,
            region_id = data.region_id,
            max_count = max_count,
            mode = "manual",
            world = plan_world_name(),
            x = feet.x,
            y = feet.y,
            z = feet.z,
        }, function(ok2, data2)
            if ok2 and data2 and data2.ok then
                local n = tonumber(data2.removed) or 0
                local velos = tonumber(data2.velos_total) or 0
                if n <= 0 then
                    core.chat_send_player(name, "Keine geplanten Hologramme in dieser Zone.")
                else
                    core.chat_send_player(
                        name,
                        string.format(
                            "Entfernt: %d Hologramme · geplante Umwandlung −%d Vel.",
                            n,
                            velos
                        )
                    )
                end
                poll_summary(name)
            else
                core.chat_send_player(name, plan_error_message(data2))
            end
        end)
    end)
    return true, "Entfernen …"
end

core.register_chatcommand("mccplan", {
    params = "[on|off|autoconvert [on|off]|status|summary|look|remove|clear [n|all]|convert [n]|discard [all|hand]]",
    description = "Planung: autoconvert=beim Strampeln · convert=manuell",
    func = function(name, param)
        local p = (param or ""):match("^(%S+)") or "status"
        if p == "autoconvert" then
            local sub = (param or ""):match("^autoconvert%s+(%S+)") or "status"
            if sub == "off" then
                mcc_plan.set_autoconvert_on(name, false)
                return true, "Auto-Umwandlung AUS."
            end
            local ok_build, err_build = require_build_session(name)
            if not ok_build then
                return false, err_build
            end
            if sub == "on" then
                if not api_post then
                    return false, "Bridge offline."
                end
                mcc_plan.set_autoconvert_on(name, true)
                poll_summary(name)
                return true,
                    "Auto-Umwandlung AN — Velos im Plan-Pool (Radfahren), Hologramme werden nach und nach real."
            end
            local st = mcc_plan.is_autoconvert_on(name) and "AN" or "AUS"
            return true, "Auto-Umwandlung: " .. st .. " (/mccplan autoconvert on|off)"
        end
        local ok_build, err_build = require_build_session(name)
        if not ok_build then
            return false, err_build
        end
        if p == "discard" then
            local player = core.get_player_by_name(name)
            if not player then
                return false, "Spieler nicht online."
            end
            local sub = (param or ""):match("^discard%s+(%S+)") or "hand"
            if sub == "hand" or sub == "slot" then
                sub = "wield"
            end
            local n = mcc_plan.discard_plan_items(player, sub == "all" and "all" or "wield")
            if n <= 0 then
                return false, "Kein Plan-Item (Hand: gewählter Slot · all: gesamtes Inventar)."
            end
            return true, "Plan-Items entfernt: " .. tostring(n) .. " Stück."
        end
        if p == "on" then
            mcc_plan.set_active(name, true)
            poll_summary(name)
            return true, "Planung AN — Shop: Planung aktivieren, 0 Velo."
        elseif p == "off" then
            mcc_plan.set_active(name, false)
            return true, "Planung AUS."
        elseif p == "status" or p == "summary" then
            poll_summary(name)
            return send_status_to_chat(name)
        elseif p == "look" then
            local player = core.get_player_by_name(name)
            if not player then
                return false, "Spieler nicht online."
            end
            local pos = raycast_hologram_under_crosshair(player)
            if not pos then
                return false, "Kein Block im Blick (max. 8 m)."
            end
            send_hologram_info(player, pos)
            return true, ""
        elseif p == "remove" then
            local player = core.get_player_by_name(name)
            if not player then
                return false, "Spieler nicht online."
            end
            local pos = raycast_hologram_under_crosshair(player)
            if not pos then
                return false, "Kein Plan-Hologramm im Blick (max. 8 m)."
            end
            if mcc_plan.remove_hologram_at(pos, player, { give_item = true, register_api = true }) then
                return true, "Plan-Hologramm entfernt."
            end
            return false, "Kein Plan-Hologramm an dieser Stelle."
        elseif p == "clear" then
            local sub = (param or ""):match("^clear%s+(%S+)") or "32"
            local max_n = 32
            if sub == "all" then
                max_n = 0
            else
                max_n = tonumber(sub) or 32
            end
            return run_plan_clear_from_feet(name, max_n)
        elseif p == "convert" then
            local n = tonumber((param or ""):match("convert%s+(%d+)")) or 1
            if not api_post then
                return false, "Bridge offline."
            end
            local feet = player_feet_pos(core.get_player_by_name(name))
            if not feet then
                return false, "Keine Position."
            end
            api_post("/api/luanti/plan/summary/", {
                player = name,
                world = plan_world_name(),
                x = feet.x,
                y = feet.y,
                z = feet.z,
            }, function(ok, data)
                if not ok or not data or not data.region_id then
                    core.chat_send_player(name, plan_error_message(data))
                    return
                end
                local tx = name .. "-plan-conv-" .. tostring(os.time())
                api_post("/api/luanti/plan/convert/", {
                    player = name,
                    region_id = data.region_id,
                    client_tx_id = tx,
                    max_count = n,
                    mode = "manual",
                }, function(ok2, data2)
                    if ok2 and data2 and data2.ok then
                        local n = tonumber(data2.converted) or 0
                        if n <= 0 then
                            core.chat_send_player(
                                name,
                                "Keine geplanten Blöcke zum Umwandeln (erst Hologramme setzen)."
                            )
                        else
                            local fx = data2.fx_stagger
                            if fx == nil then
                                fx = true
                            end
                            if n > 1 and fx then
                                core.chat_send_player(
                                    name,
                                    "Umwandlung gestartet: "
                                        .. tostring(n)
                                        .. " Blöcke (schichtweise von unten)."
                                )
                            else
                                core.chat_send_player(
                                    name,
                                    "Umgewandelt: " .. tostring(n) .. " Blöcke."
                                )
                            end
                        end
                        poll_summary(name)
                    else
                        core.chat_send_player(name, plan_error_message(data2))
                    end
                end)
            end)
            return true, "Umwandlung …"
        else
            return send_status_to_chat(name)
        end
    end,
})
