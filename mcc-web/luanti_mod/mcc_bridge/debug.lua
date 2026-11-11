-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Channel-based debug logging for mcc_bridge (minetest.conf: mcc_bridge.debug).

local M = {}

local ALL_CHANNELS = {
    session = true,
    shop = true,
    http = true,
    command = true,
}

local function normalize_token(s)
    s = tostring(s or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
    if s == "1" or s == "true" or s == "yes" or s == "all" or s == "*" then
        return "all"
    end
    if s == "0" or s == "false" or s == "no" or s == "" then
        return ""
    end
    return s
end

--- Parse mcc_bridge.debug setting into a channel table.
function M.parse_channels(settings_string)
    local raw = normalize_token(settings_string)
    if raw == "" then
        return {}
    end
    if raw == "all" then
        local out = {}
        for k in pairs(ALL_CHANNELS) do
            out[k] = true
        end
        return out
    end
    local out = {}
    for part in raw:gmatch("[^,%s;]+") do
        part = normalize_token(part)
        if part ~= "" and part ~= "all" and ALL_CHANNELS[part] then
            out[part] = true
        end
    end
    return out
end

function M.setup(channels, opts)
    opts = opts or {}
    M._channels = channels or {}
    M._debug_heartbeat = opts.debug_heartbeat == true
    return M
end

function M.debug_enabled(channel)
    if not channel or not M._channels then
        return false
    end
    return M._channels[channel] == true
end

function M.channel_summary()
    local names = {}
    for k in pairs(M._channels or {}) do
        names[#names + 1] = k
    end
    table.sort(names)
    if #names == 0 then
        return "off"
    end
    return table.concat(names, ",")
end

function M.log(channel, msg)
    if not M.debug_enabled(channel) then
        return
    end
    msg = tostring(msg or "")
    if msg == "" then
        return
    end
    core.log("action", "[mcc_bridge:debug:" .. tostring(channel) .. "] " .. msg)
end

function M.logf(channel, fmt, ...)
    if not M.debug_enabled(channel) then
        return
    end
    M.log(channel, string.format(tostring(fmt or ""), ...))
end

function M.http_heartbeat_enabled()
    return M._debug_heartbeat == true
end

return M
