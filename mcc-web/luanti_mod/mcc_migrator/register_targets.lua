-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later

return function(map)
    map.stub_targets = map.stub_targets or {}

    local STUB = {
        drawtype = "normal",
        tiles = { "default_stone.png" },
        groups = { cracky = 3 },
        is_ground_content = true,
    }

    local function register_stub(target_name)
        if (target_name or "") == "" then
            return false
        end
        if map.stub_targets[target_name] or rawget(core.registered_nodes, target_name) then
            map.stub_targets[target_name] = true
            return false
        end
        local def = {}
        for k, v in pairs(STUB) do
            def[k] = v
        end
        def.description = "Umbau-Ziel: " .. target_name
        if target_name:find("^stairs:", 1, true) or target_name:find("^doors:", 1, true) then
            def.paramtype2 = "facedir"
        end
        if target_name:find("^carts:", 1, true) then
            def.drawtype = "raillike"
            def.walkable = false
            def.groups = { oddly_breakable_by_hand = 1, dig_immediate = 2 }
        end
        if target_name:find("_inner_", 1, true) or target_name:find("_outer_", 1, true) then
            def.drawtype = "nodebox"
            def.paramtype2 = "facedir"
            def.node_box = { type = "fixed", fixed = { -0.5, -0.5, -0.5, 0.5, 0, 0.5 } }
        end
        core.register_node(":" .. target_name, def)
        map.stub_targets[target_name] = true
        return true
    end

    local registered = 0
    local seen = {}

    if map.collect_convert_targets then
        seen = map.collect_convert_targets()
    end
    if map.extra_stub_targets then
        for name in pairs(map.extra_stub_targets) do
            seen[name] = true
        end
    end
    for node_name in pairs(core.registered_nodes) do
        if node_name:sub(1, 4) == "mcl_" then
            local new_name = map.resolve_name(node_name)
            if new_name then
                seen[new_name] = true
            end
        end
    end

    -- Stable registration order: map.sqlite stores numeric content_ids; if stub order
    -- changes between restarts, every converted block becomes <unknown>.
    local ordered = {}
    for target_name in pairs(seen) do
        ordered[#ordered + 1] = target_name
    end
    table.sort(ordered)

    for i = 1, #ordered do
        if register_stub(ordered[i]) then
            registered = registered + 1
        end
    end
    local nstub = 0
    for _ in pairs(map.stub_targets) do
        nstub = nstub + 1
    end
    core.log(
        "action",
        "[mcc_migrator] registered "
            .. registered
            .. " new stub node(s), "
            .. #ordered
            .. " mapping target(s), "
            .. nstub
            .. " stub_targets ready (sorted ids)"
    )
end