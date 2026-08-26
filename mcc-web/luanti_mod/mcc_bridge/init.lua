-- Copyright (c) 2026 SAI-Lab / MyCyclingCity
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- MCC Luanti bridge: HTTP auth/session/inventory/shop + optional WS commands.

local http = core.request_http_api and core.request_http_api()
local modname = core.get_current_modname()
local modpath = core.get_modpath(modname)

local storage = core.get_mod_storage()

local function settings_get(key, default)
    local v = core.settings:get("mcc_bridge." .. key)
    if v == nil or v == "" then
        return default
    end
    return v
end

local CFG = {
    base_url = settings_get("base_url", "http://127.0.0.1:8000"),
    server_id = settings_get("server_id", "luanti-1"),
    shared_secret = settings_get("shared_secret", "SECRET"),
    heartbeat_seconds = tonumber(settings_get("heartbeat_seconds", "5")) or 5,
}

local function json_encode(tbl)
    return core.write_json(tbl)
end

local function json_decode(str)
    if not str or str == "" then
        return nil
    end
    return core.parse_json(str)
end

-- Simple HMAC-SHA256 via core if available is not portable; send timestamp + secret header
-- Matching Django: body without signature is signed. For Lua we use a lightweight
-- token: sha256(secret .. canonical_json) approximated with core.sha1 fallback note.
-- Production: prefer installing a HMAC helper; here we use shared secret header
-- plus body hash for Smoke tests. Django verifies HMAC of JSON payload.

local function api_post(path, body, callback)
    if not http then
        core.log("error", "[mcc_bridge] HTTP API not available (secure.http_mods?)")
        if callback then callback(false, nil) end
        return
    end
    body = body or {}
    body.server_id = CFG.server_id
    body.timestamp = os.time()
    -- Django accepts auth_token == shared_secret (HMAC optional for Lua).
    body.auth_token = CFG.shared_secret
    body.signature = ""
    http.fetch({
        url = CFG.base_url .. path,
        method = "POST",
        timeout = 10,
        data = json_encode(body),
        extra_headers = {
            "Content-Type: application/json",
        },
    }, function(result)
        if not result or not result.succeeded then
            core.log("warning", "[mcc_bridge] HTTP failed " .. path)
            if callback then callback(false, nil) end
            return
        end
        local data = json_decode(result.data)
        if callback then callback(true, data) end
    end)
end

-- Shared bridge API table (used by heartbeat command dispatch + shop GUI).
local mcc_bridge = rawget(_G, "mcc_bridge") or {}
rawset(_G, "mcc_bridge", mcc_bridge)

dofile(modpath .. "/shop_gui.lua")
mcc_bridge.init_shop_gui(api_post)

local region_outline = dofile(modpath .. "/region_outline.lua")

mcc_bridge.apply_city_steps = function(steps)
    for _, step in ipairs(steps or {}) do
        local op = step.op
        if op == "set_time" and step.value ~= nil then
            core.set_timeofday((tonumber(step.value) or 0) / 24000)
        elseif op == "set_time_speed" and step.value ~= nil then
            -- 0 = freeze day/night (always bright after set_time noon); ~72 = default.
            local speed = tonumber(step.value) or 72
            if speed < 0 then
                speed = 0
            end
            core.settings:set("time_speed", tostring(speed))
            core.log("action", "[mcc_bridge] time_speed=" .. tostring(speed))
        elseif op == "set_weather" then
            local w = tostring(step.value or step.weather or "clear")
            if w == "clear" then
                w = "none"
            end
            if core.global_exists("mcl_weather") and mcl_weather.change_weather then
                local ok = mcl_weather.change_weather(w)
                core.log("action", "[mcc_bridge] weather=" .. w .. " ok=" .. tostring(ok))
            else
                core.log("warning", "[mcc_bridge] mcl_weather unavailable")
            end
        elseif op == "chat" and step.message then
            core.chat_send_all(tostring(step.message))
        end
    end
end

mcc_bridge.cart_command = function(cmd)
    core.log("action", "[mcc_bridge] cart op=" .. tostring(cmd and cmd.op))
end

-- Players waiting for Admin session freigabe (poll join until granted).
local waiting_poll = {} -- name -> true
local clear_player_inventories -- forward decl (defined below)

local function set_player_frozen(player, frozen)
    if not player then
        return
    end
    if frozen then
        -- Completely lock locomotion (walk/jump/fly). Privs alone cannot stop walking.
        player:set_physics_override({
            speed = 0,
            jump = 0,
            gravity = 1,
            sneak = false,
            sneak_glitch = false,
            new_move = true,
        })
    else
        player:set_physics_override({
            speed = 1,
            jump = 1,
            gravity = 1,
            sneak = true,
            sneak_glitch = false,
            new_move = true,
        })
    end
end

local function is_player_paused(name)
    return storage:get_string("paused_" .. name) == "1"
end

-- Region catalog (used by command dispatch + is_protected). Declared early so
-- apply_bridge_commands closures can see these locals.
local protected_regions = {}
local has_protect_build_region = false

local function floor_block(n)
    n = tonumber(n) or 0
    if n >= 0 then
        return math.floor(n)
    end
    return math.ceil(n) - 1
end

local function apply_regions_catalog(payload_or_rows)
    local payload = payload_or_rows
    local rows = payload_or_rows
    if type(payload_or_rows) == "table" and payload_or_rows.regions then
        payload = payload_or_rows
        rows = payload_or_rows.regions
    end
    protected_regions = {}
    has_protect_build_region = false
    for _, r in ipairs(rows or {}) do
        if type(r) == "table" and r.min and r.max then
            local min = r.min
            local max = r.max
            local members = {}
            for _, m in ipairs(r.members or {}) do
                members[string.lower(tostring(m))] = true
            end
            local protect = r.protect_build ~= false
            if protect then
                has_protect_build_region = true
            end
            protected_regions[#protected_regions + 1] = {
                region_id = tostring(r.region_id or ""),
                protect_build = protect,
                members = members,
                min_x = math.min(tonumber(min[1]) or 0, tonumber(max[1]) or 0),
                min_y = math.min(tonumber(min[2]) or 0, tonumber(max[2]) or 0),
                min_z = math.min(tonumber(min[3]) or 0, tonumber(max[3]) or 0),
                max_x = math.max(tonumber(min[1]) or 0, tonumber(max[1]) or 0),
                max_y = math.max(tonumber(min[2]) or 0, tonumber(max[2]) or 0),
                max_z = math.max(tonumber(min[3]) or 0, tonumber(max[3]) or 0),
            }
        end
    end
    if region_outline and region_outline.apply_catalog then
        region_outline.apply_catalog(payload, rows)
    end
    core.log(
        "action",
        "[mcc_bridge] regions loaded count="
            .. tostring(#protected_regions)
            .. " protect_build="
            .. tostring(has_protect_build_region)
    )
end

local regions_fetch_seq = 0

local function refresh_regions_from_api()
    -- Ignore out-of-order HTTP replies so an older in-flight fetch cannot
    -- restore a stale outline after REGIONS_UPDATE already applied newer bounds.
    regions_fetch_seq = regions_fetch_seq + 1
    local seq = regions_fetch_seq
    api_post("/api/luanti/regions/", {}, function(ok, data)
        if seq ~= regions_fetch_seq then
            return
        end
        if ok and data then
            apply_regions_catalog(data)
        end
    end)
end

local apply_join_result -- forward decl (defined below)

local function collect_main_inventory(player)
    local payload = {}
    if not player then
        return payload
    end
    local inv = player:get_inventory()
    if not inv then
        return payload
    end
    local list = inv:get_list("main") or {}
    for _, stack in ipairs(list) do
        if not stack:is_empty() then
            payload[#payload + 1] = {
                name = stack:get_name(),
                count = stack:get_count(),
                wear = stack:get_wear(),
            }
        end
    end
    return payload
end

-- core.write_json encodes empty Lua {} as JSON object {}; Django expects [].
-- Always send inventory_count so empty inventories still persist.
local function inventory_body_fields(player)
    local items = collect_main_inventory(player)
    return {
        inventory = items,
        inventory_count = #items,
    }
end

-- Loud session-end notice for kids: colored chat banner + HUD + sound + echo.
local function show_session_end_warning(name, minutes)
    local mins = tonumber(minutes) or 1
    if mins < 1 then
        mins = 1
    end
    local line = "!!! SESSION ENDET IN CA. " .. tostring(mins) .. " MINUTEN !!!"
    local line_en = "!!! SESSION ENDS IN ~" .. tostring(mins) .. " MIN !!!"
    local bar = "################################"
    local colorize = core.colorize or function(_, s)
        return s
    end
    core.chat_send_player(name, colorize("#FF2222", bar))
    core.chat_send_player(name, colorize("#FFEE00", line))
    core.chat_send_player(name, colorize("#FFEE00", line_en))
    core.chat_send_player(name, colorize("#FF2222", bar))

    local player = core.get_player_by_name(name)
    if player then
        -- Level-up sound is loud and familiar from Mineclonia.
        core.sound_play("level_up", { to_player = name, gain = 1.0 }, true)
        core.after(0.35, function()
            core.sound_play("level_up", { to_player = name, gain = 0.8 }, true)
        end)

        local hud_text = "⚠ SESSION ENDET BALD ⚠\nnoch ca. " .. tostring(mins) .. " Minuten"
        local hid = player:hud_add({
            type = "text",
            position = { x = 0.5, y = 0.22 },
            offset = { x = 0, y = 0 },
            alignment = { x = 0, y = 0 },
            text = hud_text,
            number = 0xFF2200,
            size = { x = 2.5, y = 2.5 },
            z_index = 200,
            style = 1,
        })
        if hid then
            core.after(15, function()
                local p = core.get_player_by_name(name)
                if p then
                    p:hud_remove(hid)
                end
            end)
        end
    end

    -- Second chat pulse so it stays visible if they look away briefly.
    core.after(4, function()
        if core.get_player_by_name(name) then
            core.chat_send_player(name, colorize("#FFEE00", line))
            core.sound_play("experience", { to_player = name, gain = 0.9 }, true)
        end
    end)
    core.log("action", "[mcc_bridge] SESSION_END_WARNING player=" .. name .. " min=" .. tostring(mins))
end

local function apply_bridge_commands(commands)
    if type(commands) ~= "table" then
        return
    end
    for _, cmd in ipairs(commands) do
        if type(cmd) == "table" then
            local t = tostring(cmd.type or "")
            if t == "RUN_CITY_PRESET" then
                mcc_bridge.apply_city_steps(cmd.steps)
                core.log("action", "[mcc_bridge] city preset " .. tostring(cmd.slug or "?"))
            elseif t == "SESSION_STARTED" and cmd.player then
                waiting_poll[tostring(cmd.player)] = true
            elseif t == "SET_MODE" and cmd.player then
                local pname = tostring(cmd.player)
                local player = core.get_player_by_name(pname)
                if cmd.paused then
                    -- Persist live inventory before freeze (mode unchanged).
                    if player then
                        local mode_now = storage:get_string("mode_" .. pname)
                        if mode_now == nil or mode_now == "" or mode_now == "paused" then
                            mode_now = "play"
                        end
                        local sync_body = inventory_body_fields(player)
                        sync_body.player = pname
                        sync_body.mode = mode_now
                        api_post("/api/luanti/inventory/sync/", sync_body)
                    end
                    storage:set_string("paused_" .. pname, "1")
                    storage:set_string("mode_" .. pname, "paused")
                    if player then
                        core.set_player_privs(pname, { shout = true })
                        set_player_frozen(player, true)
                        core.chat_send_player(
                            pname,
                            "Session pausiert — keine Bewegung. / Session paused — no movement."
                        )
                    end
                    waiting_poll[pname] = nil
                else
                    storage:set_string("paused_" .. pname, "")
                    if player then
                        set_player_frozen(player, false)
                    end
                    local new_mode = tostring(cmd.mode or "")
                    if new_mode ~= "" then
                        -- Save current-mode inventory, switch mode in Django, apply join.
                        local mode_body = inventory_body_fields(player)
                        mode_body.player = pname
                        mode_body.mode = new_mode
                        api_post(
                            "/api/luanti/session/set-mode/",
                            mode_body,
                            function(ok, join)
                                if ok and join and not join.wait then
                                    apply_join_result(pname, join)
                                elseif ok and join and join.wait then
                                    waiting_poll[pname] = true
                                else
                                    core.log(
                                        "warning",
                                        "[mcc_bridge] SET_MODE failed player=" .. pname
                                    )
                                    waiting_poll[pname] = true
                                end
                            end
                        )
                    else
                        waiting_poll[pname] = true
                    end
                end
            elseif t == "SESSION_END_WARNING" and cmd.player then
                local pname = tostring(cmd.player)
                local minutes = tonumber(cmd.minutes) or 1
                if minutes < 1 then
                    minutes = 1
                end
                show_session_end_warning(pname, minutes)
            elseif t == "CHAT_PLAYER" and cmd.player then
                local pname = tostring(cmd.player)
                local msg = tostring(cmd.message or "")
                if msg ~= "" then
                    core.chat_send_player(pname, msg)
                end
            elseif t == "DUMP_ITEM_REGISTRY" then
                -- Push registered itemstrings to Django for shop import / picker.
                local batch = {}
                local batch_size = 400
                local total = 0
                local first_chunk = true
                local function flush()
                    if #batch == 0 then
                        return
                    end
                    api_post("/api/luanti/shop/registry/", {
                        items = batch,
                        clear = first_chunk,
                    })
                    first_chunk = false
                    batch = {}
                end
                for name, def in pairs(core.registered_items or {}) do
                    if type(name) == "string" and name:find(":", 1, true) and name:sub(1, 1) ~= ":" then
                        local kind = "item"
                        if core.registered_nodes[name] then
                            kind = "node"
                        elseif core.registered_tools and core.registered_tools[name] then
                            kind = "tool"
                        end
                        local desc = ""
                        if type(def) == "table" and def.description then
                            desc = tostring(def.description):gsub("\n", " "):sub(1, 200)
                        end
                        batch[#batch + 1] = { name = name, description = desc, kind = kind }
                        total = total + 1
                        if #batch >= batch_size then
                            flush()
                        end
                    end
                end
                flush()
                core.log(
                    "action",
                    "[mcc_bridge] DUMP_ITEM_REGISTRY items=" .. tostring(total)
                )
            elseif t == "GET_PLAYER_POS" and cmd.player then
                local pname = tostring(cmd.player)
                local request_id = tostring(cmd.request_id or "")
                local player = core.get_player_by_name(pname)
                if not player then
                    -- Case-insensitive fallback among connected players.
                    local want = string.lower(pname)
                    for _, p in ipairs(core.get_connected_players()) do
                        if string.lower(p:get_player_name()) == want then
                            player = p
                            pname = p:get_player_name()
                            break
                        end
                    end
                end
                if player and request_id ~= "" then
                    local pos = player:get_pos()
                    if pos then
                        api_post("/api/luanti/player/pos/", {
                            request_id = request_id,
                            player = pname,
                            x = floor_block(pos.x),
                            y = floor_block(pos.y),
                            z = floor_block(pos.z),
                        })
                        core.log(
                            "action",
                            "[mcc_bridge] GET_PLAYER_POS player="
                                .. pname
                                .. " req="
                                .. request_id
                        )
                    end
                else
                    core.log(
                        "warning",
                        "[mcc_bridge] GET_PLAYER_POS miss player="
                            .. pname
                            .. " req="
                            .. request_id
                    )
                end
            elseif t == "REGIONS_UPDATE" then
                -- Apply push immediately (outline spawners are deleted+rebuilt inside
                -- apply_catalog). Bump fetch seq so any older in-flight HTTP refresh
                -- cannot overwrite with stale bounds; then re-pull for full members.
                regions_fetch_seq = regions_fetch_seq + 1
                apply_regions_catalog(cmd)
                refresh_regions_from_api()
            elseif t == "SAVE_LEAVE_ALL" then
                -- Safe server stop: kick everyone so on_leaveplayer saves inventory.
                local reason = tostring(cmd.reason or "server_shutdown")
                for _, player in ipairs(core.get_connected_players()) do
                    local pname = player:get_player_name()
                    waiting_poll[pname] = nil
                    core.kick_player(pname, reason)
                end
                core.log("action", "[mcc_bridge] SAVE_LEAVE_ALL reason=" .. reason)
            elseif t == "CLEAR_INVENTORY" and cmd.player then
                local pname = tostring(cmd.player)
                local mode = tostring(cmd.mode or "")
                local player = core.get_player_by_name(pname)
                if player then
                    clear_player_inventories(player)
                    if mode == "" then
                        mode = storage:get_string("mode_" .. pname) or "play"
                        if mode == "paused" then
                            mode = "play"
                        end
                    end
                    api_post("/api/luanti/inventory/sync/", {
                        player = pname,
                        mode = mode,
                        inventory = {},
                        inventory_count = 0,
                    })
                    core.chat_send_player(pname, "Inventar geleert. / Inventory cleared.")
                    core.log("action", "[mcc_bridge] CLEAR_INVENTORY player=" .. pname)
                end
            elseif t == "KICK_PLAYER" and cmd.player then
                -- Keep Django session active until leave (with inventory) or
                -- offline leave below. Admin must not end_session before kick.
                local pname = tostring(cmd.player)
                local reason = tostring(cmd.reason or "session_ended")
                local player = core.get_player_by_name(pname)
                storage:set_string("paused_" .. pname, "")
                if player then
                    set_player_frozen(player, false)
                    core.kick_player(pname, reason)
                else
                    api_post("/api/luanti/session/leave/", { player = pname })
                    core.log("action", "[mcc_bridge] KICK offline leave player=" .. pname)
                end
            elseif t == "SET_PASSWORD" and cmd.player and cmd.password then
                local pname = tostring(cmd.player)
                local raw = tostring(cmd.password)
                if core.set_player_password and core.get_password_hash then
                    core.set_player_password(pname, core.get_password_hash(pname, raw))
                    core.log("action", "[mcc_bridge] SET_PASSWORD player=" .. pname)
                else
                    core.log("error", "[mcc_bridge] SET_PASSWORD unavailable")
                end
            elseif t == "CART_COMMAND" then
                mcc_bridge.cart_command(cmd)
            else
                core.log("action", "[mcc_bridge] ignored command type=" .. t)
            end
        end
    end
end

local function connected_player_names()
    local names = {}
    for _, player in ipairs(core.get_connected_players()) do
        names[#names + 1] = player:get_player_name()
    end
    return names
end

local function post_session_leave(player, name)
    local leave_body = inventory_body_fields(player)
    leave_body.player = name
    storage:set_string("paused_" .. name, "")
    if player then
        set_player_frozen(player, false)
    end
    api_post("/api/luanti/session/leave/", leave_body)
end

local function heartbeat()
    local names = connected_player_names()
    -- core.write_json encodes empty {} as object {}, not []; send player_count
    -- so Django can reconcile offline sessions after a hard server restart.
    api_post(
        "/api/luanti/heartbeat/",
        { players = names, player_count = #names },
        function(ok, data)
            if ok then
                storage:set_string("last_heartbeat", tostring(os.time()))
                if data then
                    apply_bridge_commands(data.commands)
                end
            end
        end
    )
end

-- Play/watch: city must stay intact (no dig/place), even with shop tools.
-- Build mode: dig/place only inside protect_build regions where the player is a member
-- (once at least one such region exists). Otherwise unrestricted (legacy).
local function pos_in_region(pos, region)
    local x = floor_block(pos.x)
    local y = floor_block(pos.y)
    local z = floor_block(pos.z)
    return x >= region.min_x
        and x <= region.max_x
        and y >= region.min_y
        and y <= region.max_y
        and z >= region.min_z
        and z <= region.max_z
end

local function build_mode_is_protected(pos, name)
    if not has_protect_build_region then
        return false
    end
    if core.check_player_privs(name, { protection_bypass = true }) then
        return false
    end
    local key = string.lower(tostring(name))
    local member_here = false
    for _, region in ipairs(protected_regions) do
        if region.protect_build and pos_in_region(pos, region) then
            if region.members[key] then
                member_here = true
                break
            end
        end
    end
    if member_here then
        return false
    end
    -- Outside all protect_build regions, or inside without membership.
    return true
end

local function get_stored_mode(name)
    local mode = storage:get_string("mode_" .. name)
    if mode == nil or mode == "" then
        return "play"
    end
    return mode
end

local function mode_protects_world(name)
    if is_player_paused(name) then
        return true
    end
    local mode = get_stored_mode(name)
    return mode == "play" or mode == "watch" or mode == "paused"
end

local function install_play_mode_world_protection()
    local old_is_protected = core.is_protected
    function core.is_protected(pos, name)
        if name and mode_protects_world(name) then
            return true
        end
        if name and pos and get_stored_mode(name) == "build" then
            if build_mode_is_protected(pos, name) then
                return true
            end
        end
        return old_is_protected(pos, name)
    end

    core.register_on_protection_violation(function(pos, name)
        if not name then
            return
        end
        if mode_protects_world(name) then
            core.chat_send_player(
                name,
                "Im Spielmodus kannst du die Stadt nicht verändern. / Play mode: city is protected."
            )
            return
        end
        if get_stored_mode(name) == "build" and build_mode_is_protected(pos, name) then
            core.chat_send_player(
                name,
                "Hier darfst du nicht bauen (keine Bauzone / kein Member). / Build zone required."
            )
        end
    end)
end

clear_player_inventories = function(player)
    if not player then
        return
    end
    local inv = player:get_inventory()
    if not inv then
        return
    end
    -- Mineclonia survival inventories need a usable main list; older clears via
    -- set_list({}, {}) could shrink size to 0 and block dig/shop inserts.
    if inv:get_size("main") < 36 then
        inv:set_size("main", 36)
    end
    if inv:get_size("craft") < 4 then
        inv:set_size("craft", 4)
    end
    for _, listname in ipairs({ "main", "craft", "offhand", "armor" }) do
        local size = inv:get_size(listname)
        if size > 0 then
            for i = 1, size do
                inv:set_stack(listname, i, ItemStack(""))
            end
        end
    end
end

-- Singlenode/void: MCL dig drops spawn as entities and fall off the world before
-- the item-magnet can collect them. Put drops into the digger inventory first.
local function install_direct_dig_to_inventory()
    local orig = core.handle_node_drops
    if type(orig) ~= "function" then
        return
    end
    function core.handle_node_drops(pos, drops, digger)
        orig(pos, drops, digger)
        if not digger or not digger:is_player() or not pos then
            return
        end
        local inv = digger:get_inventory()
        if not inv then
            return
        end
        if inv:get_size("main") < 36 then
            inv:set_size("main", 36)
        end
        for _, obj in ipairs(core.get_objects_inside_radius(pos, 2.5) or {}) do
            local ent = obj:get_luaentity()
            if ent and ent.name == "__builtin:item" and ent.itemstring and ent.itemstring ~= "" and not ent._removed then
                local leftover = inv:add_item("main", ItemStack(ent.itemstring))
                if leftover:is_empty() then
                    ent._removed = true
                    obj:remove()
                else
                    ent.itemstring = leftover:to_string()
                end
            end
        end
    end
    core.log("action", "[mcc_bridge] dig drops → inventory (void-safe)")
end

apply_join_result = function(name, join)
    local player = core.get_player_by_name(name)
    if not player or not join then
        return
    end
    if join.wait then
        waiting_poll[name] = true
        storage:set_string("paused_" .. name, "")
        clear_player_inventories(player)
        set_player_frozen(player, false)
        core.chat_send_player(name, "Warte auf Session-Freigabe… / Waiting for session…")
        core.set_player_privs(name, { shout = true })
        storage:set_string("mode_" .. name, "play")
        return
    end
    waiting_poll[name] = nil
    local paused = join.paused == true or join.mode == "paused"
    if paused then
        storage:set_string("paused_" .. name, "1")
        storage:set_string("mode_" .. name, "paused")
        core.set_player_privs(name, { shout = true })
        set_player_frozen(player, true)
        core.chat_send_player(
            name,
            "Session pausiert — keine Bewegung. / Session paused — no movement."
        )
        return
    end
    storage:set_string("paused_" .. name, "")
    set_player_frozen(player, false)
    local privs = {}
    for _, p in ipairs(join.privs or {}) do
        privs[p] = true
    end
    core.set_player_privs(name, privs)
    local inv = player:get_inventory()
    if inv then
        clear_player_inventories(player)
        -- Apply Django inventory only (empty for new players — shop buys fill it).
        if type(join.inventory) == "table" then
            for i, stack in ipairs(join.inventory) do
                if type(stack) == "table" and stack.name then
                    local item = ItemStack(stack.name .. " " .. tostring(stack.count or 1))
                    if stack.wear then
                        item:set_wear(stack.wear)
                    end
                    inv:set_stack("main", i, item)
                end
            end
        end
    end
    if join.mode then
        core.chat_send_player(name, "Modus / Mode: " .. tostring(join.mode))
    end
    storage:set_string("mode_" .. name, join.mode or "play")
end

local function poll_waiting_sessions()
    for name, _ in pairs(waiting_poll) do
        if not core.get_player_by_name(name) then
            waiting_poll[name] = nil
        else
            api_post("/api/luanti/session/join/", { player = name }, function(ok, join)
                if ok and join and not join.wait then
                    apply_join_result(name, join)
                    core.chat_send_player(name, "Session freigegeben! / Session granted!")
                elseif ok and join and join.wait then
                    waiting_poll[name] = true
                end
            end)
        end
    end
    core.after(5, poll_waiting_sessions)
end

-- Solid spawn pad for singlenode/void worlds — created once, never rebuilt.
-- Re-placing every restart wiped player builds around spawn (stone pad + air column).
local function ensure_spawn_platform()
    local marker = storage:get_string("spawn_platform_v1")
    if marker and marker ~= "" then
        core.log(
            "action",
            "[mcc_bridge] spawn platform already initialized (" .. marker .. "), keeping world"
        )
        return
    end

    local y_floor = 0
    local y_spawn = 4
    local radius = 8
    local minp = { x = -radius, y = y_floor, z = -radius }
    local maxp = { x = radius, y = y_floor + 1, z = radius }
    local node_name = "mcl_core:stone"
    if not core.registered_nodes[node_name] then
        node_name = "mapgen_stone"
    end
    -- Keep a thin bedrock rim under the pad so the void stays sealed if stone is removed.
    local rim_name = "mcl_core:bedrock"
    if not core.registered_nodes[rim_name] then
        rim_name = node_name
    end
    core.emerge_area(minp, maxp, function(_, _, calls_remaining)
        if calls_remaining and calls_remaining > 0 then
            return
        end
        -- Another emerge callback may have finished first; do not overwrite builds.
        local again = storage:get_string("spawn_platform_v1")
        if again and again ~= "" then
            return
        end
        local placed = 0
        for x = -radius, radius do
            for z = -radius, radius do
                core.set_node({ x = x, y = y_floor, z = z }, { name = rim_name })
                core.set_node({ x = x, y = y_floor + 1, z = z }, { name = node_name })
                placed = placed + 2
            end
        end
        -- Clear a few air blocks above so spawn is not inside solid (first init only).
        for x = -1, 1 do
            for z = -1, 1 do
                for y = y_floor + 2, y_spawn + 2 do
                    core.set_node({ x = x, y = y, z = z }, { name = "air" })
                end
            end
        end
        storage:set_string("spawn_platform_v1", "stone_v2")
        core.log(
            "action",
            "[mcc_bridge] spawn platform created once node="
                .. node_name
                .. " placed="
                .. tostring(placed)
                .. " spawn_y="
                .. tostring(y_spawn)
        )
    end)
end

core.register_on_mods_loaded(function()
    install_play_mode_world_protection()
    install_direct_dig_to_inventory()
    -- Always ensure void worlds have a landing pad (independent of HTTP).
    core.after(1, ensure_spawn_platform)

    -- Re-apply freeze: other mods may reset physics_override.
    -- Also tick region outline particles / enter hints.
    core.register_globalstep(function(dtime)
        for _, player in ipairs(core.get_connected_players()) do
            local name = player:get_player_name()
            if is_player_paused(name) then
                set_player_frozen(player, true)
            end
        end
        if region_outline and region_outline.tick then
            region_outline.tick(dtime)
        end
    end)

    if not http then
        core.log("error", "[mcc_bridge] enable secure.http_mods = mcc_bridge")
        return
    end
    -- Defer first heartbeat: get_connected_players is deprecated during mod load.
    local interval = math.max(5, CFG.heartbeat_seconds)
    core.after(1, function()
        heartbeat()
        refresh_regions_from_api()
        local function loop()
            heartbeat()
            core.after(interval, loop)
        end
        core.after(interval, loop)
        -- Periodic catalog refresh so Admin edits never leave ghost outlines.
        local function regions_loop()
            refresh_regions_from_api()
            core.after(20, regions_loop)
        end
        core.after(20, regions_loop)
    end)
    core.after(5, poll_waiting_sessions)
    core.log("action", "[mcc_bridge] loaded server_id=" .. CFG.server_id)
end)

-- Closed registration: only names that Django already knows get auth entries.
core.register_on_prejoinplayer(function(name, ip)
    if not name or name == "" then
        return "Invalid name"
    end
end)

core.register_on_joinplayer(function(player)
    local name = player:get_player_name()
    -- Strip world-file leftovers immediately; Django inventory is applied only
    -- after session freigabe (wait=false).
    clear_player_inventories(player)
    core.set_player_privs(name, { shout = true })
    storage:set_string("mode_" .. name, "play")
    -- Rescue players stuck in singlenode void from a previous fall.
    local pos = player:get_pos()
    if pos and pos.y < -32 then
        player:set_pos({ x = 0, y = 4, z = 0 })
        core.chat_send_player(name, "Zum Spawn zurückgesetzt / Reset to spawn")
    end
    api_post("/api/luanti/auth/check/", { player = name }, function(ok, data)
        if not ok or not data or not data.allowed then
            core.kick_player(name, "Nicht freigegeben / Not authorized")
            return
        end
        api_post("/api/luanti/session/join/", { player = name }, function(ok2, join)
            if not ok2 or not join then
                return
            end
            apply_join_result(name, join)
        end)
    end)
end)

core.register_on_leaveplayer(function(player)
    local name = player:get_player_name()
    waiting_poll[name] = nil
    if region_outline and region_outline.clear_player then
        region_outline.clear_player(name)
    end
    if mcc_bridge.shop_gui_on_leave then
        mcc_bridge.shop_gui_on_leave(name)
    end
    post_session_leave(player, name)
end)

-- Hard stop/restart: attempt leave before process exit (best-effort HTTP).
core.register_on_shutdown(function()
    for _, player in ipairs(core.get_connected_players()) do
        local name = player:get_player_name()
        waiting_poll[name] = nil
        if mcc_bridge.shop_gui_on_leave then
            mcc_bridge.shop_gui_on_leave(name)
        end
        post_session_leave(player, name)
    end
end)

-- Open graphical shop (Buy / Sell formspec).
core.register_chatcommand("mccshop", {
    description = "MCC Shop GUI",
    func = function(name)
        if mcc_bridge.open_shop_gui then
            mcc_bridge.open_shop_gui(name)
        else
            core.chat_send_player(name, "Shop GUI unavailable")
        end
        return true
    end,
})

-- Text catalog fallback for operators / debugging.
core.register_chatcommand("mccshop_list", {
    description = "MCC Shop text catalog",
    func = function(name)
        api_post("/api/luanti/shop/catalog/", { player = name }, function(ok, data)
            if not ok or not data then
                core.chat_send_player(name, "Shop offline")
                return
            end
            for _, cat in ipairs(data.categories or {}) do
                core.chat_send_player(name, "[" .. (cat.name or "?") .. "]")
                for _, item in ipairs(cat.items or {}) do
                    core.chat_send_player(
                        name,
                        string.format(
                            "  #%s %s = %s Velos",
                            tostring(item.id),
                            item.display_name or item.item_name,
                            tostring(item.buy_price_velos)
                        )
                    )
                end
            end
            core.chat_send_player(name, "Buy: /mccbuy <id> [qty]  |  Sell: /mccsell <id> [qty]")
        end)
        return true
    end,
})

core.register_chatcommand("mccbuy", {
    params = "<item_id> [qty]",
    description = "Buy shop item for Velos",
    func = function(name, param)
        local id, qty = param:match("^(%d+)%s*(%d*)$")
        id = tonumber(id)
        qty = tonumber(qty) or 1
        if not id then
            return false, "Usage: /mccbuy <id> [qty]"
        end
        local tx = name .. "-" .. tostring(os.time()) .. "-" .. tostring(id)
        api_post("/api/luanti/shop/buy/", {
            player = name,
            item_id = id,
            quantity = qty,
            client_tx_id = tx,
        }, function(ok, data)
            if not ok or not data or not data.ok then
                core.chat_send_player(name, "Kauf fehlgeschlagen / buy failed")
                return
            end
            local player = core.get_player_by_name(name)
            if player and data.grant then
                local inv = player:get_inventory()
                for _, g in ipairs(data.grant) do
                    inv:add_item("main", ItemStack((g.item_name or "") .. " " .. tostring(g.count or 1)))
                end
            end
            core.chat_send_player(name, "Velos: " .. tostring(data.velos_spendable or "?"))
        end)
        return true
    end,
})

local function count_item_in_main(inv, item_name)
    local total = 0
    if not inv or not item_name or item_name == "" then
        return 0
    end
    for i = 1, inv:get_size("main") do
        local stack = inv:get_stack("main", i)
        if stack:get_name() == item_name then
            total = total + stack:get_count()
        end
    end
    return total
end

local function take_item_from_main(inv, item_name, count)
    local left = tonumber(count) or 0
    if left <= 0 then
        return true
    end
    for i = 1, inv:get_size("main") do
        if left <= 0 then
            break
        end
        local stack = inv:get_stack("main", i)
        if stack:get_name() == item_name then
            local n = stack:get_count()
            local remove = math.min(n, left)
            stack:take_item(remove)
            inv:set_stack("main", i, stack)
            left = left - remove
        end
    end
    return left <= 0
end

core.register_chatcommand("mccsell", {
    params = "<item_id> [qty]",
    description = "Sell shop item back for Velos (only previously bought)",
    func = function(name, param)
        local id, qty = param:match("^(%d+)%s*(%d*)$")
        id = tonumber(id)
        qty = tonumber(qty) or 1
        if not id then
            return false, "Usage: /mccsell <id> [qty]"
        end
        local player = core.get_player_by_name(name)
        if not player then
            return false, "Player offline"
        end
        local inv = player:get_inventory()
        if not inv then
            return false, "No inventory"
        end
        -- Resolve item_name from catalog, then take from inv before API credit.
        api_post("/api/luanti/shop/catalog/", {}, function(ok, cat)
            if not ok or not cat then
                core.chat_send_player(name, "Shop offline")
                return
            end
            local item_name = nil
            local stack_size = 1
            for _, c in ipairs(cat.categories or {}) do
                for _, item in ipairs(c.items or {}) do
                    if tonumber(item.id) == id then
                        item_name = item.item_name
                        stack_size = tonumber(item.stack_size) or 1
                        break
                    end
                end
                if item_name then
                    break
                end
            end
            if not item_name then
                core.chat_send_player(name, "Unbekannte ID / unknown id")
                return
            end
            local need = qty * math.max(1, stack_size)
            if count_item_in_main(inv, item_name) < need then
                core.chat_send_player(name, "Nicht genug Items im Inventar / not enough items")
                return
            end
            if not take_item_from_main(inv, item_name, need) then
                core.chat_send_player(name, "Entfernen fehlgeschlagen / remove failed")
                return
            end
            local tx = name .. "-sell-" .. tostring(os.time()) .. "-" .. tostring(id)
            api_post("/api/luanti/shop/sell/", {
                player = name,
                item_id = id,
                quantity = qty,
                client_tx_id = tx,
            }, function(ok2, data)
                if not ok2 or not data or not data.ok then
                    -- Restore items if sell rejected (e.g. no purchase credit).
                    inv:add_item("main", ItemStack(item_name .. " " .. tostring(need)))
                    local err = (data and data.error) or "sell_failed"
                    core.chat_send_player(name, "Verkauf fehlgeschlagen / sell failed: " .. tostring(err))
                    return
                end
                core.chat_send_player(
                    name,
                    "Verkauf +"
                        .. tostring(data.refunded or "?")
                        .. " Velos, Stand: "
                        .. tostring(data.velos_spendable or "?")
                )
            end)
        end)
        return true
    end,
})

dofile(modpath .. "/api/http_note.lua")
