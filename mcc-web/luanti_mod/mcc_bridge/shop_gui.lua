-- Copyright (c) 2026 SAI-Lab / MyCyclingCity
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- MCC shop formspec: Buy (icon grid) + Sell (detached slots like SellGUI).

local S = core.get_translator("mcc_bridge")
local F = core.formspec_escape
local FORMNAME = "mcc_bridge:shop"

local PAGE_W = 9
local PAGE_H = 3
local PAGE_SIZE = PAGE_W * PAGE_H
local SELL_LIST = "mcc_sell"
local SELL_SIZE = 27

local api_post -- injected
local player_state = {} -- name -> state table

local function esc(s)
    return F(tostring(s or ""))
end

local function ensure_sell_inv(name)
    local player = core.get_player_by_name(name)
    if not player then
        return nil
    end
    local inv = player:get_inventory()
    if not inv then
        return nil
    end
    -- Player-bound list is more reliable for drag&drop than detached inventories.
    if inv:get_size(SELL_LIST) ~= SELL_SIZE then
        inv:set_size(SELL_LIST, SELL_SIZE)
    end
    return inv
end

local function return_sell_slots_to_player(name)
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local inv = player:get_inventory()
    if not inv or inv:get_size(SELL_LIST) <= 0 then
        return
    end
    for i = 1, inv:get_size(SELL_LIST) do
        local stack = inv:get_stack(SELL_LIST, i)
        if not stack:is_empty() then
            local leftover = inv:add_item("main", stack)
            if not leftover:is_empty() then
                local pos = player:get_pos()
                if pos then
                    core.add_item(pos, leftover)
                end
            end
            inv:set_stack(SELL_LIST, i, ItemStack(""))
        end
    end
end

local function destroy_sell_inv(name)
    return_sell_slots_to_player(name)
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local inv = player:get_inventory()
    if inv and inv:get_size(SELL_LIST) > 0 then
        inv:set_size(SELL_LIST, 0)
    end
end

local function flatten_catalog(catalog)
    local cats = {}
    local by_id = {}
    for _, cat in ipairs((catalog and catalog.categories) or {}) do
        local items = {}
        for _, it in ipairs(cat.items or {}) do
            items[#items + 1] = it
            by_id[tonumber(it.id)] = it
        end
        cats[#cats + 1] = {
            slug = cat.slug or "",
            name = cat.name or cat.slug or "?",
            items = items,
        }
    end
    return cats, by_id
end

local function filtered_items(st)
    local cat = st.cats[st.cat_idx]
    if not cat then
        return {}
    end
    local q = (st.filter or ""):lower()
    if q == "" then
        return cat.items
    end
    local out = {}
    for _, it in ipairs(cat.items) do
        local dn = tostring(it.display_name or it.item_name or ""):lower()
        local iname = tostring(it.item_name or ""):lower()
        if dn:find(q, 1, true) or iname:find(q, 1, true) then
            out[#out + 1] = it
        end
    end
    return out
end

local function category_list_string(st)
    local parts = {}
    for _, cat in ipairs(st.cats or {}) do
        local n = #(cat.items or {})
        parts[#parts + 1] = esc(tostring(cat.name or "?") .. " (" .. tostring(n) .. ")")
    end
    return table.concat(parts, ",")
end

local function get_state(name)
    return player_state[name]
end

local function build_formspec(name)
    local st = get_state(name)
    if not st then
        return ""
    end
    local velos = tonumber(st.velos) or 0
    local tab = st.tab or "buy"
    local fs = {
        "formspec_version[6]",
        "size[12.8,11.2]",
        "position[0.5,0.5]",
        "anchor[0.5,0.5]",
        "label[0.3,0.35;" .. esc(S("MCC Shop")) .. "]",
        "label[8.5,0.35;" .. esc(S("Velos") .. ": " .. tostring(velos)) .. "]",
        "button[0.3,0.6;2.2,0.7;tab_buy;" .. esc(S("Buy")) .. "]",
        "button[2.6,0.6;2.2,0.7;tab_sell;" .. esc(S("Sell")) .. "]",
        "button_exit[10.8,0.6;1.7,0.7;close;" .. esc(S("Close")) .. "]",
    }

    if tab == "buy" then
        -- Full category list (all categories, including empty).
        local cat_count = #(st.cats or {})
        if st.cat_idx < 1 then
            st.cat_idx = 1
        end
        if cat_count > 0 and st.cat_idx > cat_count then
            st.cat_idx = cat_count
        end
        fs[#fs + 1] = "label[0.3,1.4;" .. esc(S("Categories")) .. "]"
        fs[#fs + 1] = string.format(
            "textlist[0.3,1.7;3.2,6.5;catlist;%s;%d;false]",
            category_list_string(st),
            st.cat_idx
        )

        fs[#fs + 1] = "field[3.7,1.7;5.5,0.55;filter;" .. esc(S("Search")) .. ";" .. esc(st.filter or "") .. "]"
        fs[#fs + 1] = "button[9.3,1.7;1.5,0.55;do_filter;" .. esc(S("Filter")) .. "]"

        local items = filtered_items(st)
        local pages = math.max(1, math.ceil(#items / PAGE_SIZE))
        if st.page > pages then
            st.page = pages
        end
        if st.page < 1 then
            st.page = 1
        end
        local start = (st.page - 1) * PAGE_SIZE
        for row = 0, PAGE_H - 1 do
            for col = 0, PAGE_W - 1 do
                local idx = start + row * PAGE_W + col + 1
                local it = items[idx]
                local px = 3.7 + col * 1.0
                local py = 2.5 + row * 1.05
                if it then
                    local iname = it.item_name or ""
                    local tip = (it.display_name or iname)
                        .. "\n"
                        .. tostring(it.buy_price_velos or 0)
                        .. " "
                        .. S("Velos")
                    fs[#fs + 1] = string.format(
                        "item_image_button[%f,%f;0.95,0.95;%s;item_%s;]",
                        px,
                        py,
                        esc(iname),
                        tostring(it.id)
                    )
                    fs[#fs + 1] = "tooltip[item_" .. tostring(it.id) .. ";" .. esc(tip) .. "]"
                end
            end
        end

        fs[#fs + 1] = "button[3.7,5.8;1.2,0.55;page_prev;<]"
        fs[#fs + 1] = "label[5.0,5.95;"
            .. esc(S("Page") .. " " .. st.page .. "/" .. pages .. "  (" .. tostring(#items) .. ")")
            .. "]"
        fs[#fs + 1] = "button[8.5,5.8;1.2,0.55;page_next;>]"

        local sel = st.by_id[st.selected_id]
        local sel_label = sel and (sel.display_name or sel.item_name) or S("None selected")
        local price = sel and tonumber(sel.buy_price_velos) or 0
        local qty = math.max(1, math.min(64, tonumber(st.qty) or 1))
        st.qty = qty
        local total = price * qty
        fs[#fs + 1] = "label[3.7,6.55;" .. esc(S("Selected") .. ": " .. sel_label) .. "]"
        fs[#fs + 1] = "label[3.7,7.05;"
            .. esc(S("Price") .. ": " .. tostring(price) .. "  |  " .. S("Total") .. ": " .. tostring(total))
            .. "]"
        fs[#fs + 1] = "button[3.7,7.5;0.8,0.55;qty_dec;-]"
        fs[#fs + 1] = "field[4.6,7.5;1.4,0.55;qty;" .. esc(S("Qty")) .. ";" .. tostring(qty) .. "]"
        fs[#fs + 1] = "button[6.1,7.5;0.8,0.55;qty_inc;+]"
        fs[#fs + 1] = "button[7.1,7.5;2.2,0.55;do_buy;" .. esc(S("Buy")) .. "]"

        fs[#fs + 1] = "list[current_player;main;3.7,8.3;9,1;0]"
        fs[#fs + 1] = "listring[current_player;main]"
    else
        -- Sell tab: player inventory list mcc_sell (drag from main).
        ensure_sell_inv(name)
        fs[#fs + 1] = "label[0.3,1.5;" .. esc(S("Drag items here to sell (shop purchases only)")) .. "]"
        fs[#fs + 1] = "list[current_player;" .. SELL_LIST .. ";0.3,2.1;9,3;0]"
        fs[#fs + 1] = "list[current_player;main;0.3,5.8;9,3;9]"
        fs[#fs + 1] = "list[current_player;main;0.3,9.3;9,1;0]"
        fs[#fs + 1] = "listring[current_player;" .. SELL_LIST .. "]"
        fs[#fs + 1] = "listring[current_player;main]"
        fs[#fs + 1] = "button[0.3,10.5;3.5,0.55;do_sell;" .. esc(S("Sell all")) .. "]"
        fs[#fs + 1] = "button[4.0,10.5;3.5,0.55;return_sell;" .. esc(S("Return items")) .. "]"
    end

    return table.concat(fs, "")
end

local function show_shop(name)
    local fs = build_formspec(name)
    if fs ~= "" then
        core.show_formspec(name, FORMNAME, fs)
    end
end

local function refresh_after_catalog(name, data)
    local cats, by_id = flatten_catalog(data)
    local st = player_state[name] or {}
    st.cats = cats
    st.by_id = by_id
    st.velos = tonumber(data.velos_spendable) or st.velos or 0
    st.tab = st.tab or "buy"
    st.cat_idx = st.cat_idx or 1
    if st.cat_idx > #cats then
        st.cat_idx = 1
    end
    st.page = st.page or 1
    st.qty = st.qty or 1
    st.filter = st.filter or ""
    st.busy = false
    player_state[name] = st
    show_shop(name)
end

local function open_shop_gui(name)
    if not api_post then
        core.chat_send_player(name, S("Shop offline"))
        return
    end
    api_post("/api/luanti/shop/catalog/", { player = name }, function(ok, data)
        if not ok or not data or not data.ok then
            core.chat_send_player(name, S("Shop offline"))
            return
        end
        if data.session_ok == false then
            core.chat_send_player(name, S("No active session"))
            return
        end
        if data.session_paused == true then
            core.chat_send_player(name, S("Session paused"))
            return
        end
        -- session_ok may be nil on older servers — still open if categories present
        ensure_sell_inv(name)
        player_state[name] = player_state[name] or {}
        refresh_after_catalog(name, data)
    end)
end

local function collect_sell_items(name)
    local player = core.get_player_by_name(name)
    local items = {}
    if not player then
        return items
    end
    local inv = player:get_inventory()
    if not inv or inv:get_size(SELL_LIST) <= 0 then
        return items
    end
    local merged = {}
    for i = 1, inv:get_size(SELL_LIST) do
        local stack = inv:get_stack(SELL_LIST, i)
        if not stack:is_empty() then
            local iname = stack:get_name()
            merged[iname] = (merged[iname] or 0) + stack:get_count()
        end
    end
    -- Build a dense array so write_json emits JSON [] not {}.
    local idx = 0
    for iname, qty in pairs(merged) do
        idx = idx + 1
        items[idx] = { item_name = iname, quantity = qty }
    end
    return items
end

local function apply_sell_result(name, data)
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local inv = player:get_inventory()
    if not inv or inv:get_size(SELL_LIST) <= 0 then
        return
    end
    local leftovers = {}
    for _, r in ipairs(data.rejected or {}) do
        local n = r.item_name
        local q = tonumber(r.quantity) or 0
        if n and q > 0 then
            leftovers[n] = (leftovers[n] or 0) + q
        end
    end
    for i = 1, inv:get_size(SELL_LIST) do
        inv:set_stack(SELL_LIST, i, ItemStack(""))
    end
    for iname, qty in pairs(leftovers) do
        local leftover = inv:add_item(SELL_LIST, ItemStack(iname .. " " .. tostring(qty)))
        if not leftover:is_empty() then
            inv:add_item("main", leftover)
        end
    end
end

local function room_for_grant(player, grant)
    local inv = player:get_inventory()
    if not inv then
        return false
    end
    if inv:get_size("main") < 36 then
        inv:set_size("main", 36)
    end
    for _, g in ipairs(grant or {}) do
        local stack = ItemStack((g.item_name or "") .. " " .. tostring(g.count or 1))
        if not inv:room_for_item("main", stack) then
            return false
        end
    end
    return true
end

core.register_on_player_receive_fields(function(player, formname, fields)
    if formname ~= FORMNAME then
        return false
    end
    local name = player:get_player_name()
    local st = get_state(name)
    if not st then
        return true
    end
    if fields.quit or fields.close then
        return_sell_slots_to_player(name)
        return true
    end
    if fields.tab_buy then
        st.tab = "buy"
        show_shop(name)
        return true
    end
    if fields.tab_sell then
        st.tab = "sell"
        ensure_sell_inv(name)
        show_shop(name)
        return true
    end
    if fields.return_sell then
        return_sell_slots_to_player(name)
        show_shop(name)
        return true
    end
    if fields.do_filter then
        st.filter = fields.filter or ""
        st.page = 1
        show_shop(name)
        return true
    end
    if fields.page_prev then
        st.page = math.max(1, (st.page or 1) - 1)
        show_shop(name)
        return true
    end
    if fields.page_next then
        st.page = (st.page or 1) + 1
        show_shop(name)
        return true
    end
    -- textlist: "CHG:<idx>" or "DCL:<idx>" (1-based)
    if fields.catlist then
        local idx = tonumber(tostring(fields.catlist):match(":(%d+)"))
        if idx and idx >= 1 and idx <= #(st.cats or {}) then
            st.cat_idx = idx
            st.page = 1
            show_shop(name)
        end
        return true
    end
    for id, _ in pairs(st.by_id or {}) do
        if fields["item_" .. tostring(id)] then
            st.selected_id = id
            show_shop(name)
            return true
        end
    end
    if fields.qty_dec then
        st.qty = math.max(1, (tonumber(fields.qty) or st.qty or 1) - 1)
        show_shop(name)
        return true
    end
    if fields.qty_inc then
        st.qty = math.min(64, (tonumber(fields.qty) or st.qty or 1) + 1)
        show_shop(name)
        return true
    end
    if fields.qty and not fields.do_buy then
        -- typing qty without buy — keep value on next rebuild via field default
        local q = tonumber(fields.qty)
        if q then
            st.qty = math.max(1, math.min(64, q))
        end
    end

    if fields.do_buy then
        if st.busy then
            return true
        end
        local q = tonumber(fields.qty) or st.qty or 1
        q = math.max(1, math.min(64, q))
        st.qty = q
        local sel = st.by_id[st.selected_id]
        if not sel then
            core.chat_send_player(name, S("None selected"))
            return true
        end
        st.busy = true
        local tx = name .. "-gui-buy-" .. tostring(os.time()) .. "-" .. tostring(sel.id)
        api_post("/api/luanti/shop/buy/", {
            player = name,
            item_id = sel.id,
            quantity = q,
            client_tx_id = tx,
        }, function(ok, data)
            st.busy = false
            if not ok or not data or not data.ok then
                local err = (data and data.error) or "buy_failed"
                core.chat_send_player(name, S("Buy failed") .. ": " .. tostring(err))
                show_shop(name)
                return
            end
            local p = core.get_player_by_name(name)
            if p and data.grant then
                if not room_for_grant(p, data.grant) then
                    core.chat_send_player(name, S("Inventory full"))
                    -- Still spent velos — grant what fits
                end
                local inv = p:get_inventory()
                for _, g in ipairs(data.grant) do
                    local stack = ItemStack((g.item_name or "") .. " " .. tostring(g.count or 1))
                    local leftover = inv:add_item("main", stack)
                    if not leftover:is_empty() then
                        local pos = p:get_pos()
                        if pos then
                            core.add_item(pos, leftover)
                        end
                    end
                end
            end
            st.velos = tonumber(data.velos_spendable) or st.velos
            core.chat_send_player(name, S("Velos") .. ": " .. tostring(st.velos))
            show_shop(name)
        end)
        return true
    end

    if fields.do_sell then
        if st.busy then
            return true
        end
        local items = collect_sell_items(name)
        if #items == 0 then
            core.chat_send_player(name, S("Nothing to sell"))
            return true
        end
        st.busy = true
        local tx = name .. "-gui-sell-" .. tostring(os.time())
        -- items_count: Lua write_json may encode empty {} ; non-empty arrays are fine.
        api_post("/api/luanti/shop/sell_batch/", {
            player = name,
            items = items,
            items_count = #items,
            client_tx_id = tx,
        }, function(ok, data)
            st.busy = false
            if not ok or not data then
                core.chat_send_player(name, S("Sell failed") .. ": http")
                core.log("warning", "[mcc_bridge] sell_batch HTTP failed player=" .. name)
                show_shop(name)
                return
            end
            if not data.ok then
                local err = data.error or "sell_failed"
                core.chat_send_player(name, S("Sell failed") .. ": " .. tostring(err))
                show_shop(name)
                return
            end
            apply_sell_result(name, data)
            st.velos = tonumber(data.velos_spendable) or st.velos
            local refunded = tonumber(data.refunded_total) or 0
            if refunded > 0 then
                core.chat_send_player(
                    name,
                    S("Sold") .. " +" .. tostring(refunded) .. " " .. S("Velos")
                )
            else
                core.chat_send_player(name, S("Not sellable (no purchase credit)"))
            end
            show_shop(name)
        end)
        return true
    end

    return true
end)

core.register_on_leaveplayer(function(player)
    local name = player:get_player_name()
    destroy_sell_inv(name)
    player_state[name] = nil
end)

-- Public API for init.lua
mcc_bridge = rawget(_G, "mcc_bridge") or {}
rawset(_G, "mcc_bridge", mcc_bridge)

function mcc_bridge.init_shop_gui(post_fn)
    api_post = post_fn
end

function mcc_bridge.open_shop_gui(name)
    open_shop_gui(name)
end

function mcc_bridge.shop_gui_on_leave(name)
    destroy_sell_inv(name)
    player_state[name] = nil
end
