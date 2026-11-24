-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Mineclonia aliases MTG names (e.g. stairs:slab_stone -> mcl_stairs:slab_stone).
-- During migrate we write mcc_convert:* nodes; in prod, mcc_schematic_compat aliases them back.

local M = {}

M.PREFIX = "mcc_convert:"

function M.is_convert_name(name)
    return type(name) == "string" and name:sub(1, #M.PREFIX) == M.PREFIX
end

function M.to_convert_id(mtg_name)
    if M.is_convert_name(mtg_name) then
        return mtg_name
    end
    local mod, item = (mtg_name or ""):match("^([^:]+):(.+)$")
    if not mod then
        return nil
    end
    return "mcc_convert:" .. mod .. "_" .. item
end

function M.from_convert_id(convert_name)
    local rest = (convert_name or ""):match("^mcc_convert:(.+)$")
    if not rest then
        return nil
    end
    local mod, item = rest:match("^([^_]+)_(.+)$")
    if not mod then
        return nil
    end
    return mod .. ":" .. item
end

return M