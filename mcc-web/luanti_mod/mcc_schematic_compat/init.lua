-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- WorldEdit schematics from migrate use mcc_convert:* (avoid Mineclonia MTG aliases).

local convert_ids = dofile(core.get_modpath("mcc_schematic_compat") .. "/mcc_convert_ids.lua")

local registered = 0

-- Alias every concrete node name so WorldEdit can resolve mcc_convert:* from migrate schematics.
local names = {}
for node_name in pairs(core.registered_nodes) do
    if node_name ~= "" and not convert_ids.is_convert_name(node_name) then
        names[#names + 1] = node_name
    end
end
table.sort(names)

for i = 1, #names do
    local node_name = names[i]
    local alias = convert_ids.to_convert_id(node_name)
    if alias and core.registered_nodes[alias] == nil then
        core.register_alias(alias, node_name)
        registered = registered + 1
    end
end

core.log("action", "[mcc_schematic_compat] " .. registered .. " mcc_convert alias(es)")