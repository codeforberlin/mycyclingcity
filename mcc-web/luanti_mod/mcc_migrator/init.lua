-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Temporary. gameid = mineclonia, only this mod in worldmods (no MTG pack).

local map = dofile(core.get_modpath("mcc_migrator") .. "/map.lua")
local convert_ids = dofile(core.get_modpath("mcc_migrator") .. "/mcc_convert_ids.lua")

local migrate_world = core.get_worldpath():match("mycyclingcity_migrate") ~= nil

map.convert_stub_mode = true

local MIGRATOR_BUILD = "2026-11-17g"
local convert_skip_sample_logged = false

local function stub_is_ready(name)
    if not name or name == "" then
        return false
    end
    if map.stub_targets and map.stub_targets[name] then
        return true
    end
    return rawget(core.registered_nodes, name) ~= nil
end

if migrate_world then
    core.log("action", "[mcc_migrator] build " .. MIGRATOR_BUILD)
    for _, sample in ipairs({
        "mcl_stairs:slab_oak",
        "mcl_colorblocks:concrete_black",
        "mcl_panes:pane_white_flat",
    }) do
        core.log(
            "action",
            "[mcc_migrator] map resolve " .. sample .. " -> " .. tostring(map.resolve_name(sample))
        )
    end
    core.log(
        "action",
        "[mcc_migrator] convert_stub_mode=true; mcl_stairs:slab_stone -> "
            .. tostring(map.resolve_name("mcl_stairs:slab_stone"))
    )
end

local CHUNK = tonumber(core.settings:get("mcc_migrator.chunk_size")) or 64
CHUNK = math.max(16, math.min(CHUNK, 128))

local active_job = nil

core.register_privilege("mcc_migrate", {
    description = "Mineclonia-Blöcke auf Standard-Nodes umschreiben",
    give_to_singleplayer = false,
})

local function allowed(name)
    local privs = core.get_player_privs(name)
    return privs.mcc_migrate == true or privs.server == true
end

local function notify(player, msg)
    if player and player ~= "" then
        core.chat_send_player(player, "[mcc_migrator] " .. msg)
    end
    core.log("action", "[mcc_migrator] " .. msg)
end

local function parse_box(param)
    local n = {}
    for num in tostring(param or ""):gmatch("-?%d+") do
        n[#n + 1] = tonumber(num)
    end
    if #n < 6 then
        return nil
    end
    local minp = {
        x = math.min(n[1], n[4]),
        y = math.min(n[2], n[5]),
        z = math.min(n[3], n[6]),
    }
    local maxp = {
        x = math.max(n[1], n[4]),
        y = math.max(n[2], n[5]),
        z = math.max(n[3], n[6]),
    }
    return minp, maxp
end

local function iter_chunks(minp, maxp)
    local tiles = {}
    for x0 = minp.x, maxp.x, CHUNK do
        for z0 = minp.z, maxp.z, CHUNK do
            for y0 = minp.y, maxp.y, CHUNK do
                tiles[#tiles + 1] = {
                    {
                        x = x0,
                        y = y0,
                        z = z0,
                    },
                    {
                        x = math.min(x0 + CHUNK - 1, maxp.x),
                        y = math.min(y0 + CHUNK - 1, maxp.y),
                        z = math.min(z0 + CHUNK - 1, maxp.z),
                    },
                }
            end
        end
    end
    return tiles
end

local function scan_box(minp, maxp)
    local vm = core.get_voxel_manip()
    local emin, emax = vm:read_from_map(minp, maxp)
    local data = vm:get_data()
    local area = VoxelArea:new({ MinEdge = emin, MaxEdge = emax })
    local seen = {}
    local unknown = {}
    local remaining = 0
    for x = minp.x, maxp.x do
        for y = minp.y, maxp.y do
            for z = minp.z, maxp.z do
                local id = data[area:index(x, y, z)]
                local node_name = core.get_name_from_content_id(id)
                if node_name and node_name:sub(1, 4) == "mcl_" then
                    remaining = remaining + 1
                    local new_name = map.resolve_name(node_name)
                    if new_name then
                        seen[node_name] = new_name
                    else
                        unknown[node_name] = true
                    end
                end
            end
        end
    end
    return seen, unknown, remaining
end

local function scan_region(minp, maxp, progress_player)
    local tiles = iter_chunks(minp, maxp)
    local seen = {}
    local unknown = {}
    local remaining = 0
    for i, tile in ipairs(tiles) do
        local s, u, r = scan_box(tile[1], tile[2])
        for old, new in pairs(s) do
            seen[old] = new
        end
        for name in pairs(u) do
            unknown[name] = true
        end
        remaining = remaining + r
        if progress_player and (i == 1 or i == #tiles or i % 8 == 0) then
            notify(progress_player, string.format("Scan Kachel %d/%d …", i, #tiles))
        end
    end
    return seen, unknown, remaining, #tiles
end

local function write_map(seen, unknown)
    local entries = {}
    for old_name, new_name in pairs(seen) do
        entries[#entries + 1] = {
            old = old_name,
            new = new_name,
            param2_rule = map.param2_rule(old_name),
        }
    end
    table.sort(entries, function(a, b)
        return a.old < b.old
    end)
    local unknown_list = {}
    for name in pairs(unknown) do
        unknown_list[#unknown_list + 1] = name
    end
    table.sort(unknown_list)
    local path = core.get_worldpath() .. "/mcc_migrator_map.json"
    local payload = { entries = entries, unknown = unknown_list }
    core.safe_file_write(path, core.write_json(payload))
    return path, unknown_list
end

local function target_node_name(node_name)
    local new_name = map.resolve_name(node_name)
    if not new_name then
        return nil
    end
    if not convert_ids.is_convert_name(new_name) then
        local stub = convert_ids.to_convert_id(new_name)
        if stub then
            new_name = stub
        end
    end
    return new_name
end

local function convert_box(minp, maxp)
    local vm = core.get_voxel_manip()
    local e1, e2 = vm:read_from_map(minp, maxp)
    local data = vm:get_data()
    local param2 = vm:get_param2_data()
    local area = VoxelArea:new({ MinEdge = e1, MaxEdge = e2 })
    local converted = 0
    local skipped = 0
    local noop = 0
    for x = minp.x, maxp.x do
        for y = minp.y, maxp.y do
            for z = minp.z, maxp.z do
                local i = area:index(x, y, z)
                local node_name = core.get_name_from_content_id(data[i])
                if node_name and node_name:sub(1, 4) == "mcl_" then
                    local new_name = target_node_name(node_name)
                    if not new_name or not stub_is_ready(new_name) then
                        skipped = skipped + 1
                    else
                        local new_id = core.get_content_id(new_name)
                        if new_id == data[i] then
                            noop = noop + 1
                            skipped = skipped + 1
                        else
                            data[i] = new_id
                            param2[i] = map.resolve_param2(node_name, param2[i] or 0)
                            converted = converted + 1
                        end
                    end
                end
            end
        end
    end
    if converted == 0 and skipped > 0 and not convert_skip_sample_logged then
        convert_skip_sample_logged = true
        local done = false
        for x = minp.x, maxp.x do
            for y = minp.y, maxp.y do
                for z = minp.z, maxp.z do
                    local node_name = core.get_name_from_content_id(data[area:index(x, y, z)])
                    if node_name and node_name:sub(1, 4) == "mcl_" then
                        local new_name = target_node_name(node_name)
                        core.log(
                            "warning",
                            "[mcc_migrator] convert sample: "
                                .. node_name
                                .. " -> "
                                .. tostring(new_name)
                                .. " stub="
                                .. tostring(stub_is_ready(new_name))
                                .. " build="
                                .. MIGRATOR_BUILD
                        )
                        done = true
                        break
                    end
                end
                if done then
                    break
                end
            end
            if done then
                break
            end
        end
    end
    if noop > 0 then
        core.log(
            "warning",
            "[mcc_migrator] convert_box: " .. noop .. " noop (Mineclonia alias?); stubs/mcc_convert prüfen."
        )
    end
    vm:set_data(data)
    vm:set_param2_data(param2)
    -- Luanti 5.10: VoxelManip has no update_light(); light refresh via write_to_map flag.
    vm:write_to_map(true)
    return converted, skipped
end

local function run_convert_job()
    local job = active_job
    if not job or job.kind ~= "convert" then
        return
    end
    local idx = job.index
    if idx > #job.tiles then
        local _, _, left = scan_region(job.minp, job.maxp, nil)
        notify(
            job.player,
            string.format(
                "Fertig: %d Kacheln, umgeschrieben %d, übersprungen %d, mcl_-Rest %d. "
                    .. "übersprungen/noop = Stub fehlte oder Mineclonia-Alias (gleiche content_id). "
                    .. "Log: convert_stub_mode + mcc_convert:stairs_slab_stone prüfen. "
                    .. "Welt hier nur Platzhalter-Grafik — nicht beurteilen. "
                    .. "Als Nächstes //save (vor Server-Neustart!). "
                    .. "Nach Neustart ohne sortierte Stub-Registrierung: Welt aus Backup. "
                    .. "Import nach mycyclingcity_prod.",
                #job.tiles,
                job.converted,
                job.skipped,
                left
            )
        )
        active_job = nil
        return
    end
    local tile = job.tiles[idx]
    local c, s = convert_box(tile[1], tile[2])
    job.converted = job.converted + c
    job.skipped = job.skipped + s
    job.index = idx + 1
    if idx == 1 or idx == #job.tiles or idx % 4 == 0 then
        notify(job.player, string.format("Umbau Kachel %d/%d …", idx, #job.tiles))
    end
    core.after(0.05, run_convert_job)
end

local function ensure_convert_stubs()
    -- After all Mineclonia mods finished (on_mods_loaded); early init was missing many mcl_* targets.
    map.convert_stub_mode = true
    dofile(core.get_modpath("mcc_migrator") .. "/register_targets.lua")(map)
end

core.register_on_mods_loaded(ensure_convert_stubs)

if migrate_world then
    core.settings:set("time_speed", "0")
    core.register_on_shutdown(function()
        core.settings:set("time_speed", "72")
    end)
    core.after(1, function()
        core.clear_objects({ limit = 1000000 })
    end)
end

core.register_chatcommand("scan_mcl", {
    params = "<x1> <y1> <z1> <x2> <y2> <z2>",
    description = "mcl-Nodes zählen (Großbereiche werden in Kacheln zerlegt)",
    privs = { server = true },
    func = function(name, param)
        if not allowed(name) then
            return false, "Privileg server oder mcc_migrate fehlt."
        end
        local minp, maxp = parse_box(param)
        if not minp then
            return false, "Sechs Koordinaten: /scan_mcl x1 y1 z1 x2 y2 z2"
        end
        local seen, unknown, remaining, ntiles = scan_region(minp, maxp, name)
        local path, unknown_list = write_map(seen, unknown)
        local msg = string.format(
            "%d Kacheln à %d: mcl noch da %d, unbekannt %d, Datei %s. Danach /convert_mcl mit denselben Koordinaten.",
            ntiles,
            CHUNK,
            remaining,
            #unknown_list,
            path
        )
        return #unknown_list == 0, msg
    end,
})

core.register_chatcommand("convert_mcl", {
    params = "<x1> <y1> <z1> <x2> <y2> <z2>",
    description = "mcl-Blöcke umschreiben (asynchron, Kacheln)",
    privs = { server = true },
    func = function(name, param)
        if not allowed(name) then
            return false, "Privileg server oder mcc_migrate fehlt."
        end
        if active_job then
            return false, "Es läuft noch ein Umbau-Job."
        end
        local minp, maxp = parse_box(param)
        if not minp then
            return false, "Sechs Koordinaten: /convert_mcl x1 y1 z1 x2 y2 z2"
        end
        local seen, unknown, remaining = scan_region(minp, maxp, nil)
        if remaining <= 0 then
            return true, "In diesem Bereich keine mcl_-Blöcke."
        end
        if next(unknown) then
            local list = {}
            for n in pairs(unknown) do
                list[#list + 1] = n
            end
            table.sort(list)
            return false, "Zuerst Mapping in mcl_map.py: " .. table.concat(list, ", ")
        end
        map.extra_stub_targets = map.extra_stub_targets or {}
        for _old, new_name in pairs(seen) do
            if new_name and new_name ~= "" then
                map.extra_stub_targets[new_name] = true
            end
        end
        ensure_convert_stubs()
        local tiles = iter_chunks(minp, maxp)
        active_job = {
            kind = "convert",
            player = name,
            minp = minp,
            maxp = maxp,
            tiles = tiles,
            index = 1,
            converted = 0,
            skipped = 0,
        }
        core.after(0.05, run_convert_job)
        return true, string.format(
            "Umbau gestartet (%d Kacheln à %d). Fortschritt im Chat. "
                .. "Hinweis: In gameid=mineclonia sehen Zielblöcke wie Stein aus (Platzhalter). "
                .. "Erst nach WorldEdit-Import in mycyclingcity_prod wieder korrekte Texturen.",
            #tiles,
            CHUNK
        )
    end,
})

core.register_chatcommand("mcc_migrator_probe", {
    params = "",
    description = "Testet Mapping + Stub für slab_stone (nach Server-Neustart)",
    privs = { server = true },
    func = function(name)
        if not allowed(name) then
            return false, "Privileg server oder mcc_migrate fehlt."
        end
        ensure_convert_stubs()
        local old = "mcl_stairs:slab_stone"
        local new_name = target_node_name(old)
        local nstub = 0
        if map.stub_targets then
            for _ in pairs(map.stub_targets) do
                nstub = nstub + 1
            end
        end
        local cid_old = core.get_content_id(old)
        local cid_new = new_name and core.get_content_id(new_name) or -1
        local msg = string.format(
            "build=%s; %s -> %s; stub_ready=%s; stub_targets=%d; cid %d->%d",
            MIGRATOR_BUILD,
            old,
            tostring(new_name),
            tostring(stub_is_ready(new_name)),
            nstub,
            cid_old,
            cid_new
        )
        return true, msg
    end,
})

core.register_chatcommand("purge_migrate_entities", {
    params = "",
    description = "Alle Objekte (Tiere, Items) in der Migrationswelt entfernen",
    privs = { server = true },
    func = function(name)
        if not allowed(name) then
            return false, "Privileg server oder mcc_migrate fehlt."
        end
        local n = core.clear_objects({ limit = 1000000 })
        return true, "Entfernt: " .. tostring(n)
    end,
})