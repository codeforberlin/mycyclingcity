-- Copyright (c) 2026 SAI-Lab / MyCyclingCity
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Cuboid outline particles at player foot height + enter hint.
-- Catalog updates bump generation so obsolete edges stop redrawing immediately.

local M = {}

local outline_enabled = true
local enter_hint_enabled = true
local view_distance = 48
local regions = {}
local last_region_by_player = {}
local EDGE_STEP = 2
local CORNER_POST_HEIGHT = 3
local TICK_INTERVAL = 0.3
local PARTICLE_LIFE = 0.45
local accum = 0
local catalog_generation = 0
-- After a catalog change, skip drawing briefly so leftover particles expire.
local suppress_draw_until = 0

local function clamp(n, lo, hi)
    if n < lo then
        return lo
    end
    if n > hi then
        return hi
    end
    return n
end

local function rgb_hex(r, g, b)
    return string.format("#%02X%02X%02X", clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))
end

local function particle_texture(r, g, b)
    return "mcl_particles_crit.png^[colorize:" .. rgb_hex(r, g, b) .. ":220"
end

local function dist2_horizontal(ax, az, bx, bz)
    local dx = ax - bx
    local dz = az - bz
    return dx * dx + dz * dz
end

local function contains_block(region, x, y, z)
    return x >= region.min_x
        and x <= region.max_x
        and y >= region.min_y
        and y <= region.max_y
        and z >= region.min_z
        and z <= region.max_z
end

local function now()
    return core.get_us_time() / 1e6
end

local function spawn_particle(player_name, pos, texture)
    core.add_particle({
        pos = pos,
        velocity = { x = 0, y = 0.01, z = 0 },
        acceleration = { x = 0, y = 0, z = 0 },
        expirationtime = PARTICLE_LIFE,
        size = 2.2,
        collisiondetection = false,
        vertical = false,
        texture = texture,
        playername = player_name,
        glow = 8,
    })
end

local function draw_edge(player_name, texture, y, x1, z1, x2, z2)
    local dx = x2 - x1
    local dz = z2 - z1
    local len = math.max(math.abs(dx), math.abs(dz))
    if len <= 0 then
        spawn_particle(player_name, { x = x1 + 0.5, y = y + 0.2, z = z1 + 0.5 }, texture)
        return
    end
    local steps = math.max(1, math.floor(len / EDGE_STEP))
    for i = 0, steps do
        local t = i / steps
        local x = x1 + dx * t
        local z = z1 + dz * t
        spawn_particle(player_name, { x = x + 0.5, y = y + 0.2, z = z + 0.5 }, texture)
    end
end

local function draw_corner_post(player_name, texture, x, y, z)
    for h = 0, CORNER_POST_HEIGHT - 1 do
        spawn_particle(
            player_name,
            { x = x + 0.5, y = y + 0.2 + h, z = z + 0.5 },
            texture
        )
    end
end

local function draw_outline(player_name, region, foot_y)
    -- Follow the player vertically so outlines sit on the ground under their feet,
    -- not at a fixed mid-column height (void-tall regions were floating in the air).
    local y = clamp(foot_y, region.min_y, region.max_y)
    local tex = particle_texture(region.r, region.g, region.b)
    local min_x, max_x = region.min_x, region.max_x
    local min_z, max_z = region.min_z, region.max_z
    draw_edge(player_name, tex, y, min_x, min_z, max_x, min_z)
    draw_edge(player_name, tex, y, max_x, min_z, max_x, max_z)
    draw_edge(player_name, tex, y, max_x, max_z, min_x, max_z)
    draw_edge(player_name, tex, y, min_x, max_z, min_x, min_z)
    draw_corner_post(player_name, tex, min_x, y, min_z)
    draw_corner_post(player_name, tex, max_x, y, min_z)
    draw_corner_post(player_name, tex, max_x, y, max_z)
    draw_corner_post(player_name, tex, min_x, y, max_z)
end

local function show_enter_hint(player, region)
    if not enter_hint_enabled or not player then
        return
    end
    local name = player:get_player_name()
    local label = region.display_name or region.region_id
    local hex = rgb_hex(region.r, region.g, region.b)
    local msg = core.colorize("#AAAAAA", "Region: ") .. core.colorize(hex, label)
    core.chat_send_player(name, msg)
    local hid = player:hud_add({
        type = "text",
        position = { x = 0.5, y = 0.88 },
        offset = { x = 0, y = 0 },
        alignment = { x = 0, y = 0 },
        text = "Region: " .. label,
        number = tonumber(hex:sub(2), 16) or 0x55FFFF,
        size = { x = 1.6, y = 1.6 },
        z_index = 150,
        style = 1,
    })
    if hid then
        core.after(3.5, function()
            local p = core.get_player_by_name(name)
            if p then
                p:hud_remove(hid)
            end
        end)
    end
end

local function maybe_enter_hint(player_name, inside)
    local prev = last_region_by_player[player_name]
    if not inside then
        last_region_by_player[player_name] = nil
        return
    end
    if prev == inside.region_id then
        return
    end
    last_region_by_player[player_name] = inside.region_id
    local player = core.get_player_by_name(player_name)
    show_enter_hint(player, inside)
end

function M.apply_catalog(payload, region_rows)
    regions = {}
    last_region_by_player = {}
    accum = TICK_INTERVAL
    catalog_generation = catalog_generation + 1
    -- Let any particles from the previous bounds expire without being refreshed.
    suppress_draw_until = now() + PARTICLE_LIFE + 0.05

    if type(payload) == "table" then
        if payload.outline_enabled ~= nil then
            outline_enabled = payload.outline_enabled and true or false
        end
        if payload.enter_hint_enabled ~= nil then
            enter_hint_enabled = payload.enter_hint_enabled and true or false
        end
        if payload.view_distance ~= nil then
            view_distance = math.max(8, tonumber(payload.view_distance) or 48)
        end
    end

    local rows = region_rows
    if type(payload) == "table" and type(payload.regions) == "table" then
        rows = payload.regions
    elseif type(rows) ~= "table" then
        rows = {}
    end

    local next_regions = {}
    for _, r in ipairs(rows or {}) do
        if type(r) == "table" then
            local min_x, min_y, min_z, max_x, max_y, max_z
            if r.min and r.max then
                min_x = tonumber(r.min[1]) or 0
                min_y = tonumber(r.min[2]) or 0
                min_z = tonumber(r.min[3]) or 0
                max_x = tonumber(r.max[1]) or 0
                max_y = tonumber(r.max[2]) or 0
                max_z = tonumber(r.max[3]) or 0
            elseif r.min_x ~= nil and r.max_x ~= nil then
                min_x = tonumber(r.min_x) or 0
                min_y = tonumber(r.min_y) or 0
                min_z = tonumber(r.min_z) or 0
                max_x = tonumber(r.max_x) or 0
                max_y = tonumber(r.max_y) or 0
                max_z = tonumber(r.max_z) or 0
            end
            if min_x ~= nil then
                local rgb = r.color_rgb or {}
                next_regions[#next_regions + 1] = {
                    region_id = tostring(r.region_id or ""),
                    display_name = tostring(r.display_name or r.region_id or ""),
                    min_x = math.min(min_x, max_x),
                    min_y = math.min(min_y, max_y),
                    min_z = math.min(min_z, max_z),
                    max_x = math.max(min_x, max_x),
                    max_y = math.max(min_y, max_y),
                    max_z = math.max(min_z, max_z),
                    r = tonumber(rgb[1]) or 64,
                    g = tonumber(rgb[2]) or 160,
                    b = tonumber(rgb[3]) or 255,
                }
            end
        end
    end
    regions = next_regions

    local bounds_log = {}
    for _, region in ipairs(regions) do
        bounds_log[#bounds_log + 1] = string.format(
            "%s[%d,%d→%d,%d]",
            region.region_id,
            region.min_x,
            region.min_z,
            region.max_x,
            region.max_z
        )
    end
    core.log(
        "action",
        "[mcc_bridge] outline catalog gen="
            .. tostring(catalog_generation)
            .. " count="
            .. tostring(#regions)
            .. " enabled="
            .. tostring(outline_enabled)
            .. " "
            .. table.concat(bounds_log, " ")
    )
end

function M.clear_player(name)
    last_region_by_player[name] = nil
end

function M.clear_all()
    regions = {}
    last_region_by_player = {}
    accum = 0
    suppress_draw_until = now() + PARTICLE_LIFE + 0.05
end

function M.tick(dtime)
    if not outline_enabled or #regions == 0 then
        return
    end
    accum = accum + (dtime or 0)
    if accum < TICK_INTERVAL then
        return
    end
    accum = 0

    local drawing = now() >= suppress_draw_until
    local view_sq = view_distance * view_distance
    local snapshot = regions
    for _, player in ipairs(core.get_connected_players()) do
        local name = player:get_player_name()
        local pos = player:get_pos()
        if pos then
            local px, py, pz = pos.x, pos.y, pos.z
            local bx = math.floor(px)
            local by = math.floor(py)
            local bz = math.floor(pz)
            local foot_y = by
            local inside = nil
            for _, region in ipairs(snapshot) do
                if drawing then
                    local nearest_x = clamp(px, region.min_x, region.max_x)
                    local nearest_z = clamp(pz, region.min_z, region.max_z)
                    if dist2_horizontal(px, pz, nearest_x, nearest_z) <= view_sq then
                        draw_outline(name, region, foot_y)
                    end
                end
                if contains_block(region, bx, by, bz) then
                    inside = region
                end
            end
            maybe_enter_hint(name, inside)
        end
    end
end

return M
