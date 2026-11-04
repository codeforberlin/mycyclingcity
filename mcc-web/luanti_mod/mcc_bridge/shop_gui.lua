-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- MCC shop formspec: Buy (icon grid) + Sell (detached slots like SellGUI).

local F = core.formspec_escape
local FORMNAME = "mcc_bridge:shop"

-- Hardcoded DE shop UI (no core.get_translator). The Luanti client re-applies gettext to
-- many formspec strings; combined with cached @1 entries that causes T@mcc_bridge errors.
local UI = {
    title = "MCC-Shop",
    velos = "Velos",
    buy = "Kaufen",
    sell = "Verkaufen",
    close = "Schließen",
    categories = "Kategorien",
    search = "Suchbegriff",
    filter = "Filter",
    clear = "Leeren",
    page = "Seite",
    selected = "Auswahl",
    none_selected = "Nichts ausgewählt",
    price = "Preis",
    total = "Gesamt",
    qty = "Menge",
    sell_hint = "Ziehe Items hierher zum Verkaufen (nur Shop-Käufe)",
    sell_all = "Alles verkaufen",
    return_items = "Items zurück",
    shop_offline = "Shop offline",
    no_session = "Keine aktive Session",
    session_paused = "Session pausiert",
    buy_failed = "Kauf fehlgeschlagen",
    sell_failed = "Verkauf fehlgeschlagen",
    inventory_full = "Inventar voll",
    nothing_to_sell = "Nichts zu verkaufen",
    sold = "Verkauft",
    not_sellable = "Nicht verkaufbar (kein Kauf-Guthaben)",
}

-- Chat debug on item click: intended "Auswahl:" line text (set false when done).
local SHOP_SELECTION_DEBUG_TO_PLAYER = false
local SHOP_LABEL_FALLBACK_LANGS = { "de", "en" }

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

local SHOP_SEARCH_HITS_SUFFIX_DE = "Treffer im gesamten Shop"
local FILTER_ROW_Y = 1.88
local CAT_LIST_Y = 1.88
local CAT_LIST_H = 6.32
local CAT_LIST_BOTTOM = CAT_LIST_Y + CAT_LIST_H
local BUY_ROW_H = 0.55
local BUY_QTY_ROW_Y = CAT_LIST_BOTTOM - BUY_ROW_H
local BUY_PRICE_Y = BUY_QTY_ROW_Y - 0.5
local BUY_SELECTED_Y = BUY_PRICE_Y - 0.32
local GRID_ITEM_H = 0.95
local GRID_ROW_DY = 1.05
local PAGE_CTRL_H = 0.55
local PAGE_CTRL_GAP = 0.18
local PAGE_BTN_W = 1.2
local BUY_PANEL_X = 3.7
local BUY_PANEL_W = 8.85
-- ‹ › adjacently, page text to the right of both buttons.
local PAGE_PREV_X = BUY_PANEL_X
local PAGE_NEXT_X = BUY_PANEL_X + PAGE_BTN_W
local PAGE_TEXT_X = PAGE_NEXT_X + PAGE_BTN_W + 0.12
local PAGE_TEXT_Y_OFFSET = 0.26
local PAGE_SEL_GAP = 0.34

local function shop_search_hits_label(count)
    return tostring(count) .. " " .. SHOP_SEARCH_HITS_SUFFIX_DE
end

-- Client gettext re-parses formspec strings; @ and \\n in item descriptions break labels.
local function humanize_item_name(item_name)
    local s = tostring(item_name or "")
    local tail = s:match(":([^:]*)$") or s
    tail = tail:gsub("_", " "):gsub("-", " ")
    return tail:gsub("%s+", " "):match("^%s*(.-)%s*$") or tail
end

local function item_shop_id(it)
    if not it then
        return ""
    end
    local n = tonumber(it.id)
    if n then
        return tostring(math.floor(n + 0.0001))
    end
    return tostring(it.id or "")
end

-- mod:item in item_image_button must not use full formspec_escape (breaks item ids).
local function formspec_item_id(item_name)
    local s = tostring(item_name or "")
    return s:gsub("\\", "\\\\"):gsub("]", "\\]"):gsub(";", "\\;")
end

local function plain_shop_label(s, max_len)
    s = tostring(s or "")
    s = s:gsub("[\r\n]+", " ")
    repeat
        local next_s = s:gsub("@%S+%)", "")
        if next_s == s then
            break
        end
        s = next_s
    until false
    s = s:gsub("@", "")
    s = s:gsub("\\", "")
    s = s:gsub("%s+", " "):match("^%s*(.-)%s*$") or ""
    max_len = max_len or 52
    if #s > max_len then
        s = s:sub(1, max_len - 3) .. "..."
    end
    return s
end

local function normalize_language_code(raw)
    local code = tostring(raw or ""):lower():gsub("_", "-")
    if code == "" then
        return "de"
    end
    local primary = code:match("^([^-]+)") or code
    if primary == "de" or primary == "en" then
        return primary
    end
    if #primary > 16 then
        primary = primary:sub(1, 16)
    end
    return primary
end

local function client_language_code()
    local lang = "de"
    if core.get_language then
        local client_lang = core.get_language()
        if client_lang and tostring(client_lang) ~= "" then
            lang = tostring(client_lang)
        end
    end
    return normalize_language_code(lang)
end

local function label_for_lang(labels, lang)
    if type(labels) ~= "table" then
        return nil
    end
    lang = normalize_language_code(lang)
    return labels[lang] or labels[tostring(lang)]
end

local function item_short_title(it, max_len, lang)
    if not it then
        return ""
    end
    max_len = max_len or 48
    lang = normalize_language_code(lang or "de")
    local preferred = label_for_lang(it.labels, lang)
    if preferred and tostring(preferred) ~= "" then
        local t = plain_shop_label(preferred, max_len)
        if t ~= "" then
            return t
        end
    end
    -- Server-resolved name for catalog lang (same order as shop_labels.resolve_item_display_name).
    local from_display = plain_shop_label(it.display_name, max_len)
    if from_display ~= "" then
        return from_display
    end
    if type(it.labels) == "table" then
        for _, code in ipairs(SHOP_LABEL_FALLBACK_LANGS) do
            if code ~= lang then
                local v = it.labels[code]
                if v and tostring(v) ~= "" then
                    local t = plain_shop_label(v, max_len)
                    if t ~= "" then
                        return t
                    end
                end
            end
        end
    end
    return plain_shop_label(humanize_item_name(it.item_name), max_len)
end

-- Plain catalog / item id only (same formspec path as the fixed-label test; no MCL tooltip markup).
local function selection_display_text(sel, lang)
    if not sel then
        return UI.none_selected
    end
    local title = item_short_title(sel, 48, lang)
    if title == "" then
        title = humanize_item_name(sel.item_name)
    end
    if title == "" then
        title = tostring(sel.item_name or "?")
    end
    return title
end

local function shop_debug_truncate(s, max_len)
    s = tostring(s or "")
    max_len = max_len or 64
    if #s > max_len then
        return s:sub(1, max_len - 3) .. "..."
    end
    return s
end

local function shop_debug_selection_to_player(name, st, it)
    if not SHOP_SELECTION_DEBUG_TO_PLAYER or not it then
        return
    end
    local lang = (st and st.catalog_lang) or client_language_code()
    local show = selection_display_text(it, lang)
    lang = normalize_language_code(lang)
    local labels_de = ""
    local labels_en = ""
    if type(it.labels) == "table" then
        labels_de = tostring(it.labels.de or it.labels["de"] or "")
        labels_en = tostring(it.labels.en or it.labels["en"] or "")
    end
    local msg = "[MCC-Shop] Auswahl-Text: ["
        .. show
        .. "] len="
        .. #show
        .. " | client_lang="
        .. shop_debug_truncate(normalize_language_code(st and st.client_lang), 16)
        .. " | catalog_request="
        .. shop_debug_truncate(st and st.catalog_request_lang, 16)
        .. " | catalog_response="
        .. shop_debug_truncate(normalize_language_code(st and st.catalog_lang), 16)
        .. " | labels.de="
        .. shop_debug_truncate(labels_de)
        .. " | labels.en="
        .. shop_debug_truncate(labels_en)
        .. " | display_name="
        .. shop_debug_truncate(it.display_name)
        .. " | item_name="
        .. tostring(it.item_name or "")
    core.chat_send_player(name, msg)
    core.log("action", "[mcc_bridge shop] " .. name .. " " .. msg)
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
            local iid = item_shop_id(it)
            if iid ~= "" then
                by_id[iid] = it
            end
        end
        cats[#cats + 1] = {
            slug = cat.slug or "",
            name = cat.name or cat.slug or "?",
            labels = cat.labels,
            items = items,
        }
    end
    return cats, by_id
end

local function normalize_search_query(s)
    s = string.lower(tostring(s or ""))
    s = s:gsub("^%s+", ""):gsub("%s+$", "")
    s = s:gsub("ä", "a"):gsub("ö", "o"):gsub("ü", "u"):gsub("ß", "ss")
    return s
end

local function item_search_haystack(it)
    local chunks = {}
    if it.display_name and tostring(it.display_name) ~= "" then
        chunks[#chunks + 1] = tostring(it.display_name)
    end
    if type(it.labels) == "table" then
        for _, label in pairs(it.labels) do
            if label and tostring(label) ~= "" then
                chunks[#chunks + 1] = tostring(label)
            end
        end
    end
    if it.search and tostring(it.search) ~= "" then
        chunks[#chunks + 1] = tostring(it.search)
    end
    if it.item_name and tostring(it.item_name) ~= "" then
        chunks[#chunks + 1] = tostring(it.item_name)
    end
    return normalize_search_query(table.concat(chunks, " "))
end

-- Case-insensitive substring match (plain find); longer query narrows results naturally.
local function item_matches_filter(it, q)
    if q == "" then
        return true
    end
    local hay = item_search_haystack(it)
    if hay == "" then
        return false
    end
    return hay:find(q, 1, true) ~= nil
end

local function search_query_active(st)
    return normalize_search_query(st.filter or "") ~= ""
end

-- Browse: items of selected category. Search: all shop items whose name/metadata matches.
-- Returns { { it = item, cat_name = string|nil }, ... }
local function filtered_item_entries(st)
    local q = normalize_search_query(st.filter or "")
    if q == "" then
        local cat = st.cats[st.cat_idx]
        if not cat then
            return {}
        end
        local out = {}
        for _, it in ipairs(cat.items or {}) do
            out[#out + 1] = { it = it, cat_name = nil }
        end
        return out
    end
    local out = {}
    for _, cat in ipairs(st.cats or {}) do
        for _, it in ipairs(cat.items or {}) do
            if item_matches_filter(it, q) then
                out[#out + 1] = { it = it, cat_name = cat.name }
            end
        end
    end
    table.sort(out, function(a, b)
        local na = normalize_search_query(a.it.display_name or a.it.item_name or "")
        local nb = normalize_search_query(b.it.display_name or b.it.item_name or "")
        if na == nb then
            return tostring(a.it.item_name or "") < tostring(b.it.item_name or "")
        end
        return na < nb
    end)
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

local function clear_shop_selection(st)
    if st then
        st.selected_id = nil
    end
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
        "label[0.3,0.35;" .. esc(UI.title) .. "]",
        "label[8.5,0.35;" .. esc(UI.velos .. ": " .. tostring(velos)) .. "]",
        "button[0.3,0.6;2.2,0.7;tab_buy;" .. esc(UI.buy) .. "]",
        "button[2.6,0.6;2.2,0.7;tab_sell;" .. esc(UI.sell) .. "]",
        "button_exit[10.8,0.6;1.7,0.7;close;" .. esc(UI.close) .. "]",
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
        fs[#fs + 1] = "label[0.3,1.62;" .. esc(UI.categories) .. "]"
        fs[#fs + 1] = string.format(
            "textlist[0.3,%f;3.2,%f;catlist;%s;%d;false]",
            CAT_LIST_Y,
            CAT_LIST_H,
            category_list_string(st),
            st.cat_idx
        )

        fs[#fs + 1] = string.format(
            "field[3.7,%f;4.8,0.55;filter;%s;%s]",
            FILTER_ROW_Y,
            esc(UI.search),
            esc(st.filter or "")
        )
        fs[#fs + 1] = "field_close_on_enter[filter;false]"
        fs[#fs + 1] = string.format(
            "button[8.5,%f;1.1,0.55;do_filter;%s]",
            FILTER_ROW_Y,
            esc(UI.filter)
        )
        if search_query_active(st) then
            fs[#fs + 1] = string.format(
                "button[9.65,%f;1.35,0.55;clear_filter;%s]",
                FILTER_ROW_Y,
                esc(UI.clear)
            )
        end

        local items = filtered_item_entries(st)
        if search_query_active(st) then
            fs[#fs + 1] = string.format(
                "label[%f,2.70;%s]",
                BUY_PANEL_X,
                esc(plain_shop_label(shop_search_hits_label(#items), 64))
            )
        end
        local pages = math.max(1, math.ceil(#items / PAGE_SIZE))
        if st.page > pages then
            st.page = pages
        end
        if st.page < 1 then
            st.page = 1
        end
        local grid_y = search_query_active(st) and 2.88 or 2.68
        local grid_bottom = grid_y + (PAGE_H - 1) * GRID_ROW_DY + GRID_ITEM_H
        local page_y = grid_bottom + PAGE_CTRL_GAP
        local page_y_max = BUY_SELECTED_Y - PAGE_CTRL_H - PAGE_SEL_GAP
        if page_y > page_y_max then
            page_y = page_y_max
        end
        local start = (st.page - 1) * PAGE_SIZE
        for row = 0, PAGE_H - 1 do
            for col = 0, PAGE_W - 1 do
                local idx = start + row * PAGE_W + col + 1
                local entry = items[idx]
                local px = 3.7 + col * 1.0
                local py = grid_y + row * GRID_ROW_DY
                if entry and entry.it then
                    local it = entry.it
                    local iname = formspec_item_id(it.item_name or "")
                    local iid = item_shop_id(it)
                    -- No custom tooltip[] (breaks some clients); engine shows item description on hover.
                    fs[#fs + 1] = string.format(
                        "item_image_button[%f,%f;0.95,0.95;%s;item_%s;]",
                        px,
                        py,
                        iname,
                        iid
                    )
                end
            end
        end

        local page_text = UI.page
            .. " "
            .. st.page
            .. "/"
            .. pages
            .. "  ("
            .. tostring(#items)
            .. ")"
        fs[#fs + 1] = string.format(
            "button[%f,%f;%f,%f;page_prev;<]",
            PAGE_PREV_X,
            page_y,
            PAGE_BTN_W,
            PAGE_CTRL_H
        )
        fs[#fs + 1] = string.format(
            "button[%f,%f;%f,%f;page_next;>]",
            PAGE_NEXT_X,
            page_y,
            PAGE_BTN_W,
            PAGE_CTRL_H
        )
        fs[#fs + 1] = string.format(
            "label[%f,%f;%s]",
            PAGE_TEXT_X,
            page_y + PAGE_TEXT_Y_OFFSET,
            esc(page_text)
        )

        local sel = st.selected_id and st.by_id[st.selected_id]
        local sel_label = selection_display_text(sel, st.catalog_lang)
        local price = sel and tonumber(sel.buy_price_velos) or 0
        local qty = math.max(1, math.min(64, tonumber(st.qty) or 1))
        st.qty = qty
        local total = price * qty
        if sel then
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                BUY_PANEL_X,
                BUY_SELECTED_Y,
                esc(UI.selected .. ":")
            )
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                BUY_PANEL_X + 1.35,
                BUY_SELECTED_Y,
                esc(sel_label)
            )
        else
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                BUY_PANEL_X,
                BUY_SELECTED_Y,
                esc(UI.selected .. ": " .. UI.none_selected)
            )
        end
        fs[#fs + 1] = string.format(
            "label[3.7,%f;%s]",
            BUY_PRICE_Y,
            esc(UI.price .. ": " .. tostring(price) .. "  |  " .. UI.total .. ": " .. tostring(total))
        )
        fs[#fs + 1] = string.format("button[3.7,%f;0.8,%f;qty_dec;-]", BUY_QTY_ROW_Y, BUY_ROW_H)
        fs[#fs + 1] = string.format(
            "field[4.6,%f;1.4,%f;qty;%s;%s]",
            BUY_QTY_ROW_Y,
            BUY_ROW_H,
            esc(UI.qty),
            tostring(qty)
        )
        fs[#fs + 1] = "field_close_on_enter[qty;false]"
        fs[#fs + 1] = string.format("button[6.1,%f;0.8,%f;qty_inc;+]", BUY_QTY_ROW_Y, BUY_ROW_H)
        fs[#fs + 1] = string.format(
            "button[7.1,%f;2.2,%f;do_buy;%s]",
            BUY_QTY_ROW_Y,
            BUY_ROW_H,
            esc(UI.buy)
        )
        -- Buy tab: no player inventory row (items are delivered via API after "Kaufen").
    else
        -- Sell tab: player inventory list mcc_sell (drag from main).
        ensure_sell_inv(name)
        fs[#fs + 1] = "label[0.3,1.5;" .. esc(UI.sell_hint) .. "]"
        fs[#fs + 1] = "list[current_player;" .. SELL_LIST .. ";0.3,2.1;9,3;0]"
        fs[#fs + 1] = "list[current_player;main;0.3,5.8;9,3;9]"
        fs[#fs + 1] = "list[current_player;main;0.3,9.3;9,1;0]"
        fs[#fs + 1] = "listring[current_player;" .. SELL_LIST .. "]"
        fs[#fs + 1] = "listring[current_player;main]"
        fs[#fs + 1] = "button[0.3,10.5;3.5,0.55;do_sell;" .. esc(UI.sell_all) .. "]"
        fs[#fs + 1] = "button[4.0,10.5;3.5,0.55;return_sell;" .. esc(UI.return_items) .. "]"
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
    st.catalog_lang = normalize_language_code(
        data.catalog_lang or st.catalog_request_lang or st.catalog_lang or "de"
    )
    if not st.selected_id or not st.by_id[st.selected_id] then
        clear_shop_selection(st)
    end
    player_state[name] = st
    if SHOP_SELECTION_DEBUG_TO_PLAYER then
        core.chat_send_player(
            name,
            "[MCC-Shop] Katalog geladen | client_lang="
                .. tostring(st.client_lang or "?")
                .. " | catalog_request="
                .. tostring(st.catalog_request_lang or "?")
                .. " | catalog_response="
                .. tostring(st.catalog_lang or "?")
        )
    end
    show_shop(name)
end

local function open_shop_gui(name)
    if not api_post then
        core.chat_send_player(name, UI.shop_offline)
        return
    end
    local client_lang = client_language_code()
    player_state[name] = player_state[name] or {}
    clear_shop_selection(player_state[name])
    player_state[name].client_lang = client_lang
    player_state[name].catalog_request_lang = client_lang
    api_post("/api/luanti/shop/catalog/", { player = name, lang = client_lang }, function(ok, data)
        if not ok or not data or not data.ok then
            core.chat_send_player(name, UI.shop_offline)
            return
        end
        if data.session_ok == false then
            core.chat_send_player(name, UI.no_session)
            return
        end
        if data.session_paused == true then
            core.chat_send_player(name, UI.session_paused)
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
    -- Enter in text fields: apply and keep shop open (before quit/close handling).
    if fields.clear_filter then
        st.filter = ""
        st.page = 1
        clear_shop_selection(st)
        show_shop(name)
        return true
    end
    if fields.do_filter or fields.key_enter_field == "filter" then
        st.filter = fields.filter or st.filter or ""
        st.page = 1
        if normalize_search_query(st.filter) == "" then
            clear_shop_selection(st)
        end
        show_shop(name)
        return true
    end
    if fields.key_enter_field == "qty" then
        local q = tonumber(fields.qty)
        if q then
            st.qty = math.max(1, math.min(64, q))
        end
        show_shop(name)
        return true
    end
    if fields.quit or fields.close then
        if fields.key_enter_field == "filter" then
            st.filter = fields.filter or st.filter or ""
            st.page = 1
            show_shop(name)
            return true
        end
        if fields.key_enter_field == "qty" then
            local q = tonumber(fields.qty)
            if q then
                st.qty = math.max(1, math.min(64, q))
            end
            show_shop(name)
            return true
        end
        clear_shop_selection(st)
        return_sell_slots_to_player(name)
        player_state[name] = nil
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
    -- Item grid clicks (before catlist: clients echo textlist on every submit).
    for iid, it in pairs(st.by_id or {}) do
        if fields["item_" .. iid] ~= nil then
            st.selected_id = iid
            shop_debug_selection_to_player(name, st, it)
            show_shop(name)
            return true
        end
    end
    -- textlist: only act on CHG/DCL (1-based index)
    if fields.catlist then
        local raw = tostring(fields.catlist)
        local idx = tonumber(raw:match("^CHG:(%d+)")) or tonumber(raw:match("^DCL:(%d+)"))
        if idx and idx >= 1 and idx <= #(st.cats or {}) then
            st.cat_idx = idx
            st.page = 1
            st.filter = ""
            clear_shop_selection(st)
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
            core.chat_send_player(name, UI.none_selected)
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
                core.chat_send_player(name, UI.buy_failed .. ": " .. tostring(err))
                show_shop(name)
                return
            end
            local p = core.get_player_by_name(name)
            if p and data.grant then
                if not room_for_grant(p, data.grant) then
                    core.chat_send_player(name, UI.inventory_full)
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
            core.chat_send_player(name, UI.velos .. ": " .. tostring(st.velos))
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
            core.chat_send_player(name, UI.nothing_to_sell)
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
                core.chat_send_player(name, UI.sell_failed .. ": http")
                core.log("warning", "[mcc_bridge] sell_batch HTTP failed player=" .. name)
                show_shop(name)
                return
            end
            if not data.ok then
                local err = data.error or "sell_failed"
                core.chat_send_player(name, UI.sell_failed .. ": " .. tostring(err))
                show_shop(name)
                return
            end
            apply_sell_result(name, data)
            st.velos = tonumber(data.velos_spendable) or st.velos
            local refunded = tonumber(data.refunded_total) or 0
            if refunded > 0 then
                core.chat_send_player(
                    name,
                    UI.sold .. " +" .. tostring(refunded) .. " " .. UI.velos
                )
            else
                core.chat_send_player(name, UI.not_sellable)
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
