-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Optional MCC partner mods (mcc_plan, mcc_texture_painter). Safe to query before/after mod load.

local M = {}

--- Global API table published by the mod (nil if mod not loaded).
local function partner_global(modname)
    local g = rawget(_G, modname)
    if type(g) == "table" then
        return g
    end
    return nil
end

function M.has_plan_mod()
    return partner_global("mcc_plan") ~= nil
end

function M.has_texture_painter_mod()
    return partner_global("mcc_texture_painter") ~= nil
end

function M.plan_api()
    return partner_global("mcc_plan")
end

function M.log_partner_mods()
    core.log(
        "action",
        "[mcc_bridge] partner_mods plan="
            .. (M.has_plan_mod() and "loaded" or "missing")
            .. " painter="
            .. (M.has_texture_painter_mod() and "loaded" or "missing")
    )
end

return M
