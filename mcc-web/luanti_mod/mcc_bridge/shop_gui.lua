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
    wallet_buy_prefix = "Abbuchung:",
    wallet_sell_prefix = "Gutschrift:",
    wallet_plan_buy_prefix = "Kauf später von:",
    wallet_play_buy_prefix = "Dein Shop-Konto:",
    wallet_play_sell_note = "Verkauf erst im Bau-Modus",
    wallet_unknown = "Kein Wallet",
    buy = "Kaufen",
    plan_buy_tab = "Planen",
    plan_buy_action = "Planen",
    sell = "Verkaufen",
    convert_tab = "Umwandeln",
    convert_headline = "Geister-Steine werden echte Blöcke",
    convert_velos_order = "Belastetes Konto: zuerst dein Shop-Konto, dann Plan-Pool",
    convert_shop_account_fmt = "Dein Shop-Konto: %s (%s Velos)",
    convert_sell_section_lines = {
        "Abbau und Verkauf nach Umwandlung — Wem gehören die Blöcke?",
    },
    convert_sell_own_fmt = "Du zahlst alles → Gruppe: %s",
    convert_sell_top_fmt = "Pool zahlt mit → TOP: %s",
    convert_zone = "Bauzone",
    convert_current_zone = "Aktuelle Zone",
    convert_planned = "Geister-Blöcke",
    convert_velos_need = "Für Umwandlung nötig",
    convert_pool_total = "Plan-Pool aktuelle Zone: %s Velos",
    convert_pool_line = "%d. %s · %d Velos",
    convert_pool_more = "… und %d weitere Gruppen",
    convert_pool_empty = "Plan-Pool leer — Umwandeln nach Rad-Velos auf Plan-Gruppen.",
    convert_pool_line_shop = "%d. %s · %d Velos (dein Shop-Konto)",
    convert_action = "Umwandeln",
    convert_busy = "Bitte warten …",
    convert_failed = "Umwandlung fehlgeschlagen",
    convert_qty_all = "Alle",
    convert_qty_label = "Blöcke",
    wallet_plan_pool_prefix = "Plan-Pool:",
    autoconvert_label = "Auto-Umwandlung beim Strampeln",
    shop_mode_convert_denied = "Umwandeln nur im Bau-Modus (Session)",
    err_no_region = "Keine geschützte Bauzone an dieser Position.",
    err_not_member = "Du bist kein Mitglied dieser Bauzone.",
    err_no_funding_pool = "Kein Velo-Pool für die Planungsumwandlung.",
    err_convert_requires_build = "Umwandlung nur im Bau-Modus (Session).",
    err_convert_requires_position = "Umwandeln nur in deiner Bauzone — bitte in die Planungszone gehen.",
    discard_tab = "Entfernen",
    discard_zone = "Auswahl zum Entfernen",
    discard_hint = "Plan-Blöcke hierher ziehen",
    discard_all = "Auswahl entfernen",
    discard_move_denied = "Nur Plan-Blöcke aus dem Shop hierher legen.",
    nothing_to_discard = "Nichts zum Entfernen.",
    discard_done = "Plan-Items entfernt: %d Stück.",
    wallet_plan_discard_note = "Plan-Items wegwerfen (0 Velos)",
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
    total_conversion = "Gesamtumwandlungspreis",
    qty = "Menge",
    sell_hint = "Shop-Käufe in die Auswahl ziehen",
    sell_zone = "Verkaufsauswahl",
    inv_zone = "Inventar",
    sell_all = "Auswahl verkaufen",
    return_items = "Items zurück",
    shop_offline = "Shop offline",
    no_session = "Keine aktive Session — Katalog trotzdem sichtbar; Kauf/Verkauf nach Freigabe.",
    session_paused = "Session pausiert",
    buy_failed = "Kauf fehlgeschlagen",
    err_server_error = "Server-Fehler (Web-App neu starten?)",
    err_http_unreachable = "Keine Verbindung zum MCC-Server",
    err_shop_plan_requires_plan = "Plan-Kauf nur im Planungs-Modus (Session)",
    err_shop_requires_build = "Kauf/Verkauf realer Items nur im Bau-Modus (Session)",
    play_browse_note = "Nur Stöbern. Zum Planen oder Kaufen muss ein Betreuer den Modus freigeben.",
    shop_mode_buy_denied = "Hier kannst du noch nichts kaufen. Bitte „Planen“ oder „Bauen“ freigeben lassen.",
    shop_mode_sell_denied = "Verkauf nur im Bau-Modus (Session)",
    plan_session_note = "Du planst: nur Geister-Blöcke (0 Velos). Ausheben und echte Steine: Bau-Modus.",
    err_session_paused = "Session ist pausiert",
    err_item_not_found = "Artikel nicht im Shop",
    err_insufficient_velos = "Nicht genug Velos",
    err_no_group = "Keine Gruppe / Wallet für diese Session",
    err_quantity_exceeds_stack = "Menge über der Stapelgrenze für diesen Artikel",
    sell_failed = "Verkauf fehlgeschlagen",
    sell_busy = "Shop beschäftigt — bitte kurz warten.",
    buy_busy = "Shop beschäftigt — bitte kurz warten.",
    sell_rejected = "Kein Rückkauf-Guthaben für diese Items (nur Shop-Käufe ohne Planung).",
    inventory_full = "Inventar voll",
    nothing_to_sell = "Nichts zu verkaufen",
    sold = "Verkauft",
    not_sellable = "Nicht verkaufbar (kein Kauf-Guthaben)",
    sell_tip_ok = "Verkaufbar · Shop-Guthaben (%d) bei %s",
    sell_tip_ok_wallet = "Verkaufbar · Guthaben deiner Wallet %s",
    sell_tip_other = "Nicht verkaufbar: Shop-Kauf bei Gruppe %s — aktuelle Wallet: %s",
    sell_tip_parent_pool_locked = "Nicht verkaufbar: TOP-Pool für eure Gruppe gesperrt — Guthaben bei %s",
    sell_tip_no_credit = "Nicht verkaufbar: kein Shop-Kaufguthaben für diese Wallet",
    sell_tip_not_shop = "Nicht verkaufbar: kein Shop-Artikel",
    sell_tip_refund_total = "Gesamtsumme: %d Velos",
    sell_tip_refund_detail = "(%d × %d Velos pro Stück)",
    sell_tip_refund_capped = "Hinweis: nur %d von %d Stück verkaufbar",
    sell_move_denied = "Nur verkaufbare Shop-Käufe in die Verkaufsauswahl legen.",
    plan_toggle = "Planung (0 Velo, Hologramme)",
    plan_hint = "Kauf 0 Velo · Umwandlung je Block laut Preis",
    plan_sell_disabled = "Im Planungsmodus kein Verkaufen — Planung im Shop ausschalten.",
    plan_note = "Nur in der Bauzone platzierbar",
    build_only = "Planung nur im Bau-Modus",
    plan_mod_missing = "Planungsmodus nicht verfügbar (Mod mcc_plan nicht geladen) — Kauf/Verkauf wie gewohnt. / Planning unavailable (mcc_plan not loaded) — buy/sell works normally.",
}

-- Chat debug on item click: intended "Auswahl:" line text (set false when done).
local SHOP_SELECTION_DEBUG_TO_PLAYER = false
local SHOP_LABEL_FALLBACK_LANGS = { "de", "en" }

local SHOP_QTY_HARD_MAX = 64

local function max_qty_for_item(it)
    if not it then
        return SHOP_QTY_HARD_MAX
    end
    local mb = tonumber(it.max_buy_quantity)
    if mb and mb > 0 then
        return math.max(1, math.min(SHOP_QTY_HARD_MAX, mb))
    end
    local ss = tonumber(it.stack_size) or 1
    return math.max(1, math.min(SHOP_QTY_HARD_MAX, ss))
end

local function clamp_shop_qty(qty, it)
    qty = tonumber(qty) or 1
    return math.max(1, math.min(max_qty_for_item(it), qty))
end

local PAGE_W = 8
local PAGE_H = 4
local PAGE_SIZE = PAGE_W * PAGE_H
local SELL_LIST = "mcc_sell"
local SELL_SIZE = 27
local SELL_HINT_META_SAVED = "mcc_shop_desc_saved"
local SELL_HINT_META_MARK = "mcc_shop_sell_ann"

local api_post -- injected
local player_state = {} -- name -> state table
-- Forward: shop_apply_tab_change / run_shop_convert call this before its definition below.
local show_shop

local function shop_debugf(fmt, ...)
    local bridge = rawget(_G, "mcc_bridge")
    if bridge and bridge.debug_logf then
        bridge.debug_logf("shop", fmt, ...)
    end
end

local function mcc_plan_mod()
    local bridge = rawget(_G, "mcc_bridge")
    if bridge and bridge.plan_api then
        return bridge.plan_api()
    end
    return rawget(_G, "mcc_plan")
end

local shop_mod_storage -- lazy

local function player_planning_shop(name)
    local mp = mcc_plan_mod()
    if mp and mp.is_active then
        return mp.is_active(name)
    end
    return false
end

local function shop_buy_error_message(code)
    local key = "err_" .. tostring(code or "")
    if UI[key] then
        return UI[key]
    end
    return tostring(code or "buy_failed")
end

local function shop_plan_error_message(data)
    local mp = mcc_plan_mod()
    if mp and mp.plan_error_message then
        return mp.plan_error_message(data)
    end
    local code = data and (data.error or (data.ok == false and "http_error"))
    return shop_buy_error_message(code)
end

local function shop_get_session_mode(name)
	local bridge = rawget(_G, "mcc_bridge")
	if bridge and bridge.get_stored_mode then
		return bridge.get_stored_mode(name) or "play"
	end
	return "play"
end

local function shop_session_build_mode(name)
	return shop_get_session_mode(name) == "build"
end

local function shop_session_plan_mode(name)
	return shop_get_session_mode(name) == "plan"
end

local function shop_session_allows_trade(name)
	local m = shop_get_session_mode(name)
	return m == "build" or m == "plan"
end

local function shop_show_sell_tab(name)
	return shop_session_build_mode(name)
end

local function shop_show_discard_tab(name)
	return shop_session_plan_mode(name)
end

local function shop_show_convert_tab(name)
	return shop_session_build_mode(name)
end

local function shop_show_secondary_tab(name)
	if shop_show_sell_tab(name) or shop_show_discard_tab(name) then
		return true
	end
	-- Play/watch: keep Verkaufen tab visible; click shows shop_mode_sell_denied.
	if not shop_session_allows_trade(name) then
		return true
	end
	return false
end

local function shop_tab_id_list(name)
	local ids = { "buy" }
	if shop_show_discard_tab(name) then
		ids[#ids + 1] = "sell"
		return ids
	end
	if shop_show_sell_tab(name) then
		ids[#ids + 1] = "sell"
	end
	if shop_show_convert_tab(name) then
		ids[#ids + 1] = "convert"
	end
	if not shop_session_allows_trade(name) and #ids == 1 then
		ids[#ids + 1] = "sell"
	end
	return ids
end

local function shop_secondary_tab_label(name)
	if shop_show_discard_tab(name) then
		return UI.discard_tab
	end
	return UI.sell
end

local function shop_buy_tab_label(name)
	if shop_session_plan_mode(name) then
		return UI.plan_buy_tab
	end
	return UI.buy
end

local function shop_tab_tablist_string(name)
	local ids = shop_tab_id_list(name)
	local parts = {}
	for _, id in ipairs(ids) do
		local label
		if id == "buy" then
			label = shop_buy_tab_label(name)
		elseif id == "sell" then
			label = shop_secondary_tab_label(name)
		else
			label = UI.convert_tab
		end
		parts[#parts + 1] = F(tostring(label or ""))
	end
	return table.concat(parts, ",")
end

local function shop_tab_index_for(name, tab)
	local ids = shop_tab_id_list(name)
	tab = tab or "buy"
	for i, id in ipairs(ids) do
		if id == tab then
			return i
		end
	end
	return 1
end

local function shop_tab_id_for_index(name, index)
	local ids = shop_tab_id_list(name)
	index = tonumber(index) or 1
	return ids[index] or ids[1] or "buy"
end

local function plan_discard_stack_allowed(stack)
	if stack:is_empty() then
		return true
	end
	local mp = mcc_plan_mod()
	if mp and mp.stack_has_plan_meta then
		return mp.stack_has_plan_meta(stack)
	end
	return false
end

local function bridge_sync_inventory_now(player)
	local bridge = rawget(_G, "mcc_bridge")
	if bridge and bridge.sync_player_inventory_now then
		bridge.sync_player_inventory_now(player)
	end
end

local function maybe_plan_mod_missing_hint(name)
    if not shop_session_plan_mode(name) then
        return
    end
    if mcc_plan_mod() then
        return
    end
    if not shop_mod_storage then
        shop_mod_storage = core.get_mod_storage()
    end
    local key = "plan_hint_" .. name
    if shop_mod_storage:get_string(key) == "1" then
        return
    end
    shop_mod_storage:set_string(key, "1")
    core.chat_send_player(name, UI.plan_mod_missing)
    shop_debugf("plan_mod_missing_hint player=%s", name)
end

local function shop_plan_on(name, _st)
	if shop_session_plan_mode(name) then
		return true
	end
	return false
end

local function apply_shop_plan_toggle(name, st, on)
	if st then
		st.plan_active = on
	end
	local mp = mcc_plan_mod()
	if mp and mp.set_active then
		mp.set_active(name, on)
	end
end

local function resolve_planning_for_buy(name, st, fields)
	if shop_session_plan_mode(name) then
		apply_shop_plan_toggle(name, st, true)
		return true
	end
	return false
end

local function sync_shop_plan_state(name, st)
	if not st then
		return
	end
	st.plan_active = player_planning_shop(name)
end

-- Checkbox value is echoed on many submits (e.g. item grid); only apply on real toggle.
local function should_apply_plan_toggle(fields, st, player_name)
	if fields.plan_toggle == nil then
		return false
	end
	local want = fields.plan_toggle == "true"
	if want == player_planning_shop(player_name) then
		return false
	end
	if fields.do_buy or fields.do_sell or fields.sell_all or fields.plan_discard or fields.do_convert
		or fields.shop_tabs or fields.tab_buy or fields.tab_sell
		or fields.page_prev
		or fields.page_next or fields.do_filter or fields.clear_filter or fields.return_sell
		or fields.qty_dec or fields.qty_inc or fields.close or fields.quit then
		return false
	end
	for iid, _ in pairs(st.by_id or {}) do
		if fields["item_" .. iid] ~= nil then
			return false
		end
	end
	if fields.catlist then
		return false
	end
	return true
end

local function apply_grant_stack(stack, grant)
    local mp = mcc_plan_mod()
    if type(grant.meta) == "table" and mp and mp.apply_meta_to_stack then
        return mp.apply_meta_to_stack(stack, grant.meta)
    end
	return stack
end

local function esc(s)
    return F(tostring(s or ""))
end

local function wallet_display_name(st)
    local n = st and st.wallet_group_name
    if type(n) == "string" then
        n = n:match("^%s*(.-)%s*$")
    end
    if n and n ~= "" then
        return n
    end
    return UI.wallet_unknown
end

local function apply_wallet_from_response(st, data)
    if st and data and data.wallet_group_name ~= nil then
        st.wallet_group_name = tostring(data.wallet_group_name or "")
    end
    if st and data and data.wallet_group_id ~= nil then
        st.wallet_group_id = tonumber(data.wallet_group_id)
    end
end

local function normalize_group_label(name)
    if name == nil then
        return ""
    end
    local s = tostring(name):match("^%s*(.-)%s*$") or ""
    s = string.lower(s)
    s = s:gsub("%s+", " ")
    s = s:gsub("–", "-"):gsub("—", "-"):gsub("−", "-")
    return s
end

local function shop_wallet_matches_funding_pool(sum, st)
    local wid = tonumber(st and st.wallet_group_id)
    if not wid and type(sum.player_wallet) == "table" then
        wid = tonumber(sum.player_wallet.group_id)
    end
    local wname = normalize_group_label(wallet_display_name(st))
    local pools = type(sum) == "table" and sum.funding_pools
    if type(pools) ~= "table" then
        return false
    end
    for _, row in ipairs(pools) do
        if wid and tonumber(row.group_id) == wid then
            return true
        end
        if row.is_shop_wallet == true then
            return true
        end
        if wname ~= "" and normalize_group_label(row.group_name) == wname then
            return true
        end
    end
    return false
end

local SHOP_SEARCH_HITS_SUFFIX_DE = "Treffer im gesamten Shop"
-- Layout in one table (Lua limit: max 60 upvalues per function).
local G = {
	FORMSPEC_W = 12.8,
	TITLE_APPROX_W = 2.35,
	HEADER_Y = 0.28,
	CAT_LABEL_Y = 1.63,
	FILTER_ROW_Y = 1.82,
	CAT_LIST_X = 0.3,
	CAT_LIST_W = 4.05,
	GRID_COL_STEP = 1.0,
	BUY_ROW_H = 0.55,
	BUY_INFO_LINE_DY = 0.38,
	BUY_PRICE_QTY_GAP = 0.58,
	BUY_BOTTOM_PAD = 0.28,
	FORMSPEC_H = 10.05,
	CAT_LIST_Y = 1.80,
	GRID_ITEM_H = 0.95,
	GRID_ROW_DY = 1.05,
	PAGE_CTRL_H = 0.55,
	PAGE_CTRL_GAP = 0.18,
	PAGE_BTN_W = 1.2,
	PAGE_SEL_GAP = 0.34,
	FILTER_FIELD_W = 3.85,
	TAB_ROW_Y = 0.38,
	TAB_HEADER_H = 0.63,
	TAB_HEADER_W = 7.2,
	WALLET_HINT_X = 7.0,
}
G.ITEM_PANEL_X = G.CAT_LIST_X + G.CAT_LIST_W + 0.2
G.BUY_QTY_ROW_Y = G.FORMSPEC_H - G.BUY_BOTTOM_PAD - G.BUY_ROW_H
G.BUY_PRICE_Y = G.BUY_QTY_ROW_Y - G.BUY_PRICE_QTY_GAP
G.BUY_PLAN_NOTE_Y = G.BUY_PRICE_Y - G.BUY_INFO_LINE_DY
G.BUY_SELECTED_Y_PLAN = G.BUY_PLAN_NOTE_Y - G.BUY_INFO_LINE_DY
G.BUY_SELECTED_Y = G.BUY_PRICE_Y - G.BUY_INFO_LINE_DY
G.BUY_INFO_TOP_Y = G.BUY_SELECTED_Y_PLAN
G.CAT_LIST_BOTTOM = G.BUY_QTY_ROW_Y + G.BUY_ROW_H
G.CAT_LIST_H = G.CAT_LIST_BOTTOM - G.CAT_LIST_Y
G.PAGE_Y_MAX = G.BUY_INFO_TOP_Y - G.PAGE_CTRL_H - G.PAGE_SEL_GAP
G.GRID_BOTTOM_Y = G.PAGE_Y_MAX - G.PAGE_CTRL_GAP
G.GRID_Y_DEFAULT = G.GRID_BOTTOM_Y - (PAGE_H - 1) * G.GRID_ROW_DY - G.GRID_ITEM_H
G.FILTER_BTN_X = G.ITEM_PANEL_X + G.FILTER_FIELD_W + 0.15
G.FILTER_CLEAR_X = G.FILTER_BTN_X + 1.25
G.BUY_PANEL_X = G.ITEM_PANEL_X
G.QTY_FIELD_X = G.BUY_PANEL_X + 0.9
G.QTY_INC_X = G.BUY_PANEL_X + 2.4
G.QTY_BUY_X = G.BUY_PANEL_X + 3.4
G.SELL_BTN_Y = G.FORMSPEC_H - G.BUY_BOTTOM_PAD - G.BUY_ROW_H
G.SELL_ZONE_LABEL_Y = 1.38
G.SELL_LIST_X = 0.35
G.SELL_LIST_Y = 1.58
G.SELL_LIST_W = 9
G.SELL_LIST_H = 3
-- Match style_type[list;size=0.95;spacing=0.08] for centered section titles.
G.SELL_LIST_PANEL_W = G.SELL_LIST_W * 0.95 + (G.SELL_LIST_W - 1) * 0.08
G.SELL_ZONE_LABEL_H = 0.38
-- Manual X nudge for simple labels (client font metrics differ from estimate).
G.SELL_HDR_LABEL_X_SHIFT = -0.42
G.INV_LABEL_X_SHIFT = -0.15
G.SELL_MAIN_Y = 4.92
-- Center "Inventar" label in gap between sell slots and main inventory (label Y = top of text).
G.INV_ZONE_LABEL_Y = (G.SELL_LIST_Y + G.SELL_LIST_H + G.SELL_MAIN_Y) * 0.5 + 0.03
G.SELL_HOTBAR_Y = 7.82
G.SELL_BTN_W = 4.2
G.PAGE_PREV_X = G.BUY_PANEL_X
G.PAGE_NEXT_X = G.BUY_PANEL_X + G.PAGE_BTN_W
G.PAGE_TEXT_X = G.PAGE_NEXT_X + G.PAGE_BTN_W + 0.12
G.PAGE_TEXT_Y_OFFSET = 0.26
G.TAB_WALLET_HINT_Y = 1.08
-- Plan session: wallet line centered under tabs (slightly above default right-aligned row).
G.PLAN_WALLET_HINT_Y = 1.04 - G.BUY_INFO_LINE_DY
G.CONVERT_LINE_DY = 0.36
G.CONVERT_SECTION_GAP = 0.14
G.CONVERT_ZONE_Y = 1.35
G.CONVERT_HEADLINE_Y = G.CONVERT_ZONE_Y - G.CONVERT_LINE_DY
G.CONVERT_NOTE_Y = G.CONVERT_ZONE_Y + G.CONVERT_LINE_DY
G.CONVERT_FUNDING_COLS = 2
G.CONVERT_FUNDING_ROWS_PER_COL = 5
G.CONVERT_FUNDING_MAX_ENTRIES = 10
G.CONVERT_FUNDING_COL1_X = 0.45
G.CONVERT_FUNDING_COL2_X = 6.35
G.CONVERT_QTY_BELOW_AUTO_DY = 0.48
G.CONVERT_BTN_W = 2.8
G.CONVERT_BTN_Y = G.FORMSPEC_H - G.BUY_BOTTOM_PAD - G.BUY_ROW_H
G.CONVERT_BTN_X = (G.FORMSPEC_W - G.CONVERT_BTN_W) * 0.5
-- Plan / mode hints sit on a second row below wallet caption.
G.TAB_STATUS_LINE_X = 0.3
G.TAB_STATUS_LINE_Y = 1.32 - G.BUY_INFO_LINE_DY
-- Play/watch browse hint above centered shop-konto (buy tab) — avoid label overlap.
G.PLAY_BROWSE_NOTE_Y = G.TAB_WALLET_HINT_Y - 0.5
-- Plan note: below tab row.
G.PLAN_STATUS_LINE_Y = G.TAB_ROW_Y + G.TAB_HEADER_H + 0.22
G.TITLE_X = (G.FORMSPEC_W - G.TITLE_APPROX_W) * 0.5

local function shop_wallet_hint_x(_name, _tab)
	return G.WALLET_HINT_X
end

local function shop_wallet_velos_suffix(st)
	local v = tonumber(st and st.velos) or 0
	return " (" .. UI.velos .. ": " .. tostring(v) .. ")"
end

local function shop_wallet_caption(name, tab, st)
	local base
	if tab == "convert" then
		return ""
	elseif shop_session_plan_mode(name) then
		base = UI.wallet_plan_buy_prefix .. " " .. wallet_display_name(st)
	elseif tab == "sell" then
		if shop_session_build_mode(name) then
			base = UI.wallet_sell_prefix .. " " .. wallet_display_name(st)
		else
			base = UI.wallet_play_sell_note
		end
	elseif shop_session_allows_trade(name) then
		base = UI.wallet_buy_prefix .. " " .. wallet_display_name(st)
	else
		base = UI.wallet_play_buy_prefix .. " " .. wallet_display_name(st)
	end
	return base .. shop_wallet_velos_suffix(st)
end

local function shop_status_line_y(name)
	if shop_session_plan_mode(name) then
		return G.PLAN_STATUS_LINE_Y
	end
	if not shop_session_allows_trade(name) then
		return G.PLAY_BROWSE_NOTE_Y
	end
	return G.TAB_STATUS_LINE_Y
end

local function shop_status_line_text(name)
	if shop_session_plan_mode(name) then
		return UI.plan_session_note
	end
	if not shop_session_allows_trade(name) then
		return UI.play_browse_note
	end
	return nil
end

local function shop_primary_buy_button_label(name)
	if shop_session_plan_mode(name) then
		return UI.plan_buy_action
	end
	return UI.buy
end

-- Area labels (w,h) are unsupported on some Luanti builds; center via approximate text width.
local function approx_sell_label_width(text)
    local n = #tostring(text)
    local scale = n > 42 and 0.1 or 0.088
    return n * scale
end

local function append_sell_area_label(fs, y, text, x_shift)
    x_shift = tonumber(x_shift) or 0
    local tw = approx_sell_label_width(text)
    local x = G.SELL_LIST_X + math.max(0, (G.SELL_LIST_PANEL_W - tw) * 0.5) + x_shift
    fs[#fs + 1] = string.format("label[%f,%f;%s]", x, y, esc(text))
end

local function append_centered_header_label(fs, y, text)
    local tw = approx_sell_label_width(text)
    local panel_w = G.FORMSPEC_W - 0.6
    local x = 0.3 + math.max(0, (panel_w - tw) * 0.5)
    fs[#fs + 1] = string.format("label[%f,%f;%s]", x, y, esc(text))
    return y
end

-- Heading without styled element names (some Luanti builds reject label[x,y;name;text]).
local function append_convert_headline(fs, y, text)
    local display = "— " .. tostring(text or "") .. " —"
    return append_centered_header_label(fs, y, display)
end

local function append_convert_wrapped_lines(fs, y, lines)
	if type(lines) ~= "table" then
		return y
	end
	for _, line in ipairs(lines) do
		if line and line ~= "" then
			fs[#fs + 1] = string.format("label[0.3,%f;%s]", y, esc(line))
			y = y + G.CONVERT_LINE_DY
		end
	end
	return y
end

local function append_convert_funding_pool_lines(fs, sum, y, summary_ok, pool_total)
	local pool = pool_total
	if pool == nil and summary_ok then
		pool = tonumber(sum.available_velos)
	end
	local pool_text = pool ~= nil and tostring(pool) or "—"
	fs[#fs + 1] = string.format(
		"label[0.3,%f;%s]",
		y,
		esc(string.format(UI.convert_pool_total, pool_text))
	)
	y = y + G.CONVERT_LINE_DY
	local pools = summary_ok and sum.funding_pools
	if type(pools) == "table" and #pools > 0 then
		local max_show = math.min(#pools, G.CONVERT_FUNDING_MAX_ENTRIES)
		local rows_used
		if max_show <= G.CONVERT_FUNDING_ROWS_PER_COL then
			rows_used = max_show
		else
			rows_used = G.CONVERT_FUNDING_ROWS_PER_COL
		end
		local function pool_entry_label(idx)
			local row = pools[idx]
			if type(row) ~= "table" then
				return nil
			end
			local gname = tostring(row.group_name or "?")
			local gv = tonumber(row.velos_spendable) or 0
			local line_tpl = UI.convert_pool_line
			if row.is_shop_wallet == true then
				line_tpl = UI.convert_pool_line_shop
			end
			return string.format(line_tpl, idx, gname, gv)
		end
		for r = 1, rows_used do
			local row_y = y + (r - 1) * G.CONVERT_LINE_DY
			local left_idx = r
			local right_idx = r + G.CONVERT_FUNDING_ROWS_PER_COL
			if left_idx <= max_show then
				local text = pool_entry_label(left_idx)
				if text then
					fs[#fs + 1] = string.format(
						"label[%f,%f;%s]",
						G.CONVERT_FUNDING_COL1_X,
						row_y,
						esc(text)
					)
				end
			end
			if right_idx <= max_show then
				local text = pool_entry_label(right_idx)
				if text then
					fs[#fs + 1] = string.format(
						"label[%f,%f;%s]",
						G.CONVERT_FUNDING_COL2_X,
						row_y,
						esc(text)
					)
				end
			end
		end
		y = y + rows_used * G.CONVERT_LINE_DY
		local rest = #pools - max_show
		if rest > 0 then
			fs[#fs + 1] = string.format(
				"label[0.45,%f;%s]",
				y,
				esc(string.format(UI.convert_pool_more, rest))
			)
			y = y + G.CONVERT_LINE_DY
		end
	elseif summary_ok and pool and pool > 0 then
		fs[#fs + 1] = string.format(
			"label[0.45,%f;%s]",
			y,
			esc(UI.wallet_plan_pool_prefix .. " " .. tostring(pool) .. " Velos")
		)
		y = y + G.CONVERT_LINE_DY
	elseif summary_ok then
		fs[#fs + 1] = string.format(
			"label[0.45,%f;%s]",
			y,
			esc(UI.err_no_funding_pool)
		)
		y = y + G.CONVERT_LINE_DY
	end
	return y
end

local function append_convert_shop_account_line(fs, y, st, sum, summary_ok)
	if not summary_ok then
		return y
	end
	local wname = wallet_display_name(st)
	if wname == UI.wallet_unknown then
		return y
	end
	local velos = tonumber(st.velos) or 0
	local pw = sum.player_wallet
	if type(pw) == "table" and (pw.group_name or "") ~= "" then
		wname = tostring(pw.group_name)
	end
	if type(pw) == "table" and pw.velos_spendable ~= nil then
		velos = tonumber(pw.velos_spendable) or velos
	end
	fs[#fs + 1] = string.format(
		"label[0.3,%f;%s]",
		y,
		esc(string.format(UI.convert_shop_account_fmt, wname, tostring(velos)))
	)
	return y + G.CONVERT_LINE_DY
end

local function convert_sell_owner_lines(sum)
	local lines = {}
	for _, line in ipairs(UI.convert_sell_section_lines) do
		lines[#lines + 1] = line
	end
	local wname = "—"
	local pw = sum and sum.player_wallet
	if type(pw) == "table" and (pw.group_name or "") ~= "" then
		wname = tostring(pw.group_name)
	end
	local tname = "—"
	local top = sum and sum.region_top_group
	if type(top) == "table" and (top.group_name or "") ~= "" then
		tname = tostring(top.group_name)
	end
	lines[#lines + 1] = string.format(UI.convert_sell_own_fmt, wname)
	lines[#lines + 1] = string.format(UI.convert_sell_top_fmt, tname)
	return lines
end

local function convert_spendable_velos(sum)
	if type(sum) ~= "table" then
		return 0
	end
	local extra = tonumber(sum.available_convert_velos)
	if extra ~= nil then
		return extra
	end
	return tonumber(sum.available_velos) or 0
end

local function append_wallet_hint_label(fs, name, tab, st)
	if tab == "convert" then
		return
	end
	local text = shop_wallet_caption(name, tab, st)
	if shop_session_plan_mode(name) and tab ~= "convert" then
		local tw = approx_sell_label_width(text)
		local panel_w = G.FORMSPEC_W - 0.6
		local x = 0.3 + math.max(0, (panel_w - tw) * 0.5)
		fs[#fs + 1] = string.format(
			"label[%f,%f;%s]",
			x,
			G.PLAN_WALLET_HINT_Y,
			esc(text)
		)
		return
	end
	if tab == "sell" then
		append_sell_area_label(fs, G.TAB_WALLET_HINT_Y, text, G.SELL_HDR_LABEL_X_SHIFT)
		return
	end
	if tab == "buy" then
		append_centered_header_label(fs, G.TAB_WALLET_HINT_Y, text)
		return
	end
	fs[#fs + 1] = string.format(
		"label[%f,%f;%s]",
		shop_wallet_hint_x(name, tab),
		G.TAB_WALLET_HINT_Y,
		esc(text)
	)
end

local SELL_BTN_READY_BG = "#16e34a"
local SELL_BTN_READY_TEXT = "#ffffff"

-- Upper verkaufsauswahl grid only (9x3 in formspec), not player main/hotbar below.
local function sell_selection_slot_limit()
    return G.SELL_LIST_W * G.SELL_LIST_H
end

local function sell_list_has_items(name)
    local player = core.get_player_by_name(name)
    if not player then
        return false
    end
    local inv = player:get_inventory()
    if not inv or inv:get_size(SELL_LIST) <= 0 then
        return false
    end
    local limit = math.min(inv:get_size(SELL_LIST), sell_selection_slot_limit())
    for i = 1, limit do
        if not inv:get_stack(SELL_LIST, i):is_empty() then
            return true
        end
    end
    return false
end

local function sell_selection_inventory_touched(action, info)
    if type(info) ~= "table" then
        return false
    end
    if info.listname == SELL_LIST or info.from_list == SELL_LIST or info.to_list == SELL_LIST then
        return true
    end
    if type(action) == "table" then
        if action.from_list == SELL_LIST or action.to_list == SELL_LIST then
            return true
        end
    end
    return false
end

local function append_sell_action_button_styles(fs, ready, button_name)
    button_name = button_name or "sell_all"
    if ready then
        fs[#fs + 1] = string.format(
            "style[%s;bgcolor=%s;textcolor=%s;border=true]",
            button_name,
            SELL_BTN_READY_BG,
            SELL_BTN_READY_TEXT
        )
        fs[#fs + 1] = string.format(
            "style[%s:pressed;bgcolor=#15803d;textcolor=%s;border=true]",
            button_name,
            SELL_BTN_READY_TEXT
        )
    else
        fs[#fs + 1] = string.format("style[%s;bgcolor=;textcolor=;border=]", button_name)
    end
end

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

local function inventory_sell_hint_item_names(player)
    local inv = player:get_inventory()
    if not inv then
        return {}
    end
    if inv:get_size("main") < 36 then
        inv:set_size("main", 36)
    end
    local names = {}
    local seen = {}
    for i = 1, 36 do
        local stack = inv:get_stack("main", i)
        if not stack:is_empty() then
            local n = stack:get_name()
            if n and n ~= "" and not seen[n] then
                seen[n] = true
                names[#names + 1] = n
            end
        end
    end
    return names
end

local function sell_refund_velos_line(hint, stack_count)
    local price = tonumber(hint.buy_price_velos) or 0
    if price <= 0 then
        return ""
    end
    local count = math.max(1, tonumber(stack_count) or 1)
    local credit = tonumber(hint.credit_available) or 0
    local sell_count = count
    if hint.sellable and credit > 0 then
        sell_count = math.min(count, credit)
    elseif not hint.sellable then
        return ""
    end
    local total = price * sell_count
    local parts = { string.format(UI.sell_tip_refund_total, total) }
    if sell_count > 1 then
        parts[#parts + 1] = string.format(UI.sell_tip_refund_detail, sell_count, price)
    end
    if hint.sellable and count > sell_count then
        parts[#parts + 1] = string.format(UI.sell_tip_refund_capped, sell_count, count)
    end
    return table.concat(parts, "\n")
end

local function sell_hint_tooltip_line(hint, stack_count)
    if type(hint) ~= "table" then
        return UI.sell_tip_no_credit
    end
    local lines = {}
    if hint.sellable then
        local wallet = tostring(hint.wallet_group_name or "?")
        local credit = tostring(hint.credit_group_name or wallet)
        local avail = tonumber(hint.credit_available) or 0
        if credit == wallet then
            if avail > 0 then
                lines[#lines + 1] = string.format(UI.sell_tip_ok, avail, wallet)
            else
                lines[#lines + 1] = string.format(UI.sell_tip_ok_wallet, wallet)
            end
        else
            lines[#lines + 1] = string.format(UI.sell_tip_ok, avail, credit)
        end
        local refund = sell_refund_velos_line(hint, stack_count)
        if refund ~= "" then
            lines[#lines + 1] = refund
        end
        return table.concat(lines, "\n")
    end
    if hint.reason == "other_group" then
        local other = tostring(hint.credit_group_name or "?")
        local wallet = tostring(hint.wallet_group_name or "?")
        return string.format(UI.sell_tip_other, other, wallet)
    end
    if hint.reason == "parent_pool_locked" then
        local pool = tostring(hint.credit_group_name or "?")
        return string.format(UI.sell_tip_parent_pool_locked, pool)
    end
    if hint.reason == "not_in_shop" then
        return UI.sell_tip_not_shop
    end
    return UI.sell_tip_no_credit
end

local function clear_sell_inventory_tooltips(player)
    local inv = player:get_inventory()
    if not inv or inv:get_size("main") < 1 then
        return
    end
    for i = 1, 36 do
        local stack = inv:get_stack("main", i)
        if not stack:is_empty() then
            local meta = stack:get_meta()
            if meta:get_string(SELL_HINT_META_MARK) == "1" then
                local saved = meta:get_string(SELL_HINT_META_SAVED)
                if saved ~= "" then
                    meta:set_string("description", saved)
                else
                    meta:set_string("description", "")
                end
                meta:set_string(SELL_HINT_META_SAVED, "")
                meta:set_string(SELL_HINT_META_MARK, "")
                inv:set_stack("main", i, stack)
            end
        end
    end
end

local function leave_sell_tab_side_effects(name)
	local player = core.get_player_by_name(name)
	if player then
		clear_sell_inventory_tooltips(player)
	end
	return_sell_slots_to_player(name)
end

local function ensure_shop_tab_for_session(name, st)
	if not st then
		return
	end
	local tab = st.tab or "buy"
	if tab == "convert" and not shop_show_convert_tab(name) then
		st.tab = "buy"
		tab = "buy"
	end
	if tab == "sell" and not shop_show_secondary_tab(name) then
		st.tab = "buy"
		leave_sell_tab_side_effects(name)
		return
	end
	if shop_session_plan_mode(name) and tab == "convert" then
		st.tab = "buy"
	end
end

local function shop_world_name()
	local bridge = rawget(_G, "mcc_bridge")
	if bridge and bridge.mcc_world_name then
		return bridge.mcc_world_name()
	end
	return "mycyclingcity"
end

local function player_feet_block(player)
	local pos = player and player:get_pos()
	if not pos then
		return nil
	end
	return {
		x = math.floor(pos.x + 0.5),
		y = math.floor(pos.y + 0.5),
		z = math.floor(pos.z + 0.5),
	}
end

local PLAN_SUMMARY_REFRESH_SEC = 2

local function shop_client_build_zone(name)
	local bridge = rawget(_G, "mcc_bridge")
	if bridge and bridge.build_region_at_player then
		return bridge.build_region_at_player(name)
	end
	return nil
end

local function shop_plan_summary_stale(st)
	if not st or st.plan_summary_busy then
		return false
	end
	local sum = st.plan_summary
	if not sum or sum.ok ~= true or not sum.region_id then
		return true
	end
	local fetched = tonumber(st.plan_summary_fetched_at) or 0
	if fetched <= 0 then
		return true
	end
	return os.time() - fetched >= PLAN_SUMMARY_REFRESH_SEC
end

local function fetch_shop_plan_summary(name, st, cb)
	if not api_post then
		st.plan_summary = nil
		if cb then
			cb(false)
		end
		return
	end
	local player = core.get_player_by_name(name)
	local feet = player and player_feet_block(player)
	if not feet then
		st.plan_summary = { ok = false, error = "convert_requires_position" }
		if cb then
			cb(false)
		end
		return
	end
	local body = {
		player = name,
		world = shop_world_name(),
		x = feet.x,
		y = feet.y,
		z = feet.z,
	}
	if st.plan_summary_busy then
		if cb then
			cb(false)
		end
		return
	end
	st.plan_summary_busy = true
	api_post("/api/luanti/plan/summary/", body, function(ok, data)
		st.plan_summary_busy = false
		if ok and data and data.ok then
			st.plan_summary = data
			st.plan_summary_fetched_at = os.time()
			if type(data.player_wallet) == "table" and data.player_wallet.group_id ~= nil then
				st.wallet_group_id = tonumber(data.player_wallet.group_id)
			end
			if type(data.player_wallet) == "table" and data.player_wallet.group_name then
				st.wallet_group_name = tostring(data.player_wallet.group_name)
			end
		else
			st.plan_summary = data or { ok = false, error = "no_region" }
		end
		if cb then
			cb(ok and data and data.ok)
		end
	end)
end

local function maybe_refresh_shop_plan_summary(name, st)
	if not shop_session_build_mode(name) then
		return
	end
	if (st.tab or "buy") ~= "convert" then
		return
	end
	if not shop_plan_summary_stale(st) then
		return
	end
	fetch_shop_plan_summary(name, st, function()
		show_shop(name)
	end)
end

local function clamp_convert_qty(qty, st)
	qty = tonumber(qty) or 4
	qty = math.max(1, math.min(qty, 256))
	local planned = st and st.plan_summary and tonumber(st.plan_summary.planned_count)
	if planned and planned > 0 then
		qty = math.min(qty, planned)
	end
	return qty
end

local function apply_sell_inventory_tooltips(player, hints)
    if not player or type(hints) ~= "table" then
        return
    end
    local inv = player:get_inventory()
    if not inv then
        return
    end
    for i = 1, 36 do
        local stack = inv:get_stack("main", i)
        if not stack:is_empty() then
            local iname = stack:get_name()
            local hint = hints[iname]
            if hint then
                local meta = stack:get_meta()
                if meta:get_string(SELL_HINT_META_MARK) ~= "1" then
                    meta:set_string(SELL_HINT_META_SAVED, meta:get_string("description") or "")
                    meta:set_string(SELL_HINT_META_MARK, "1")
                end
                local saved = meta:get_string(SELL_HINT_META_SAVED)
                local ann = sell_hint_tooltip_line(hint, stack:get_count())
                if saved ~= "" then
                    meta:set_string("description", saved .. "\n" .. ann)
                else
                    meta:set_string("description", ann)
                end
                inv:set_stack("main", i, stack)
            end
        end
    end
end

local function sell_stack_allowed(name, stack)
    if stack:is_empty() then
        return true
    end
    local st = player_state[name]
    if not st or not st.sell_hints_ready or type(st.sell_hints) ~= "table" then
        return true
    end
    local hint = st.sell_hints[stack:get_name()]
    return type(hint) == "table" and hint.sellable == true
end

local function sync_sell_hints_for_player(name, after_fn)
    local st = player_state[name]
    if not st then
        if after_fn then
            after_fn()
        end
        return
    end
    local player = core.get_player_by_name(name)
    if not player or not api_post then
        st.sell_hints_ready = false
        if after_fn then
            after_fn()
        end
        return
    end
    local item_names = inventory_sell_hint_item_names(player)
    if #item_names == 0 then
        st.sell_hints = {}
        st.sell_hints_ready = true
        clear_sell_inventory_tooltips(player)
        if after_fn then
            after_fn()
        end
        return
    end
    api_post("/api/luanti/shop/sell_hints/", {
        player = name,
        item_names = item_names,
    }, function(ok, data)
        if not st or player_state[name] ~= st then
            if after_fn then
                after_fn()
            end
            return
        end
        if ok and data and data.ok then
            st.sell_hints = data.hints or {}
            if data.wallet_group_name then
                st.wallet_group_name = tostring(data.wallet_group_name)
            end
            st.sell_hints_ready = true
            local p = core.get_player_by_name(name)
            if p then
                clear_sell_inventory_tooltips(p)
                apply_sell_inventory_tooltips(p, st.sell_hints)
            end
        else
            st.sell_hints_ready = false
        end
        if after_fn then
            after_fn()
        end
    end)
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

local function append_convert_tab_body(fs, name, st)
    st.convert_qty = clamp_convert_qty(st.convert_qty or 4, st)
	local sum = st.plan_summary or {}
	local busy = st.plan_summary_busy and " …" or ""
	local summary_ok = sum.ok == true and (sum.region_id or "") ~= ""
	local client_zone = shop_client_build_zone(name)
	local zone_label
	if summary_ok then
		zone_label = tostring(sum.display_name or sum.region_id or "—")
	elseif client_zone and client_zone.display_name then
		zone_label = client_zone.display_name
	else
		local err = shop_plan_error_message(sum)
		if err == "" or err == "?" then
			local code = sum and sum.error
			if code == "convert_requires_position" then
				err = UI.err_convert_requires_position
			elseif code == "no_region" then
				err = UI.err_no_region
			elseif code == "not_member" then
				err = UI.err_not_member
			else
				err = UI.err_no_region
			end
		end
		zone_label = err
	end
	local planned = summary_ok and (tonumber(sum.planned_count) or 0) or 0
	local velos_need = summary_ok and (tonumber(sum.total_velos_planned) or 0) or 0
	local pool = summary_ok and convert_spendable_velos(sum)
	local pool_only = summary_ok and tonumber(sum.available_velos)
	local y = G.CONVERT_HEADLINE_Y
	y = append_convert_headline(fs, y, UI.convert_headline)
	y = y + G.CONVERT_LINE_DY
	fs[#fs + 1] = string.format(
		"label[0.3,%f;%s]",
		y,
		esc(UI.convert_current_zone .. ": " .. tostring(zone_label or "—") .. busy)
	)
	y = y + G.CONVERT_LINE_DY
	fs[#fs + 1] = string.format("label[0.3,%f;%s]", y, esc(UI.convert_velos_order))
	y = y + G.CONVERT_LINE_DY
    fs[#fs + 1] = string.format(
        "label[0.3,%f;%s]",
        y,
        esc(UI.convert_planned .. ": " .. tostring(planned))
    )
    y = y + G.CONVERT_LINE_DY
    fs[#fs + 1] = string.format(
        "label[0.3,%f;%s]",
        y,
        esc(UI.convert_velos_need .. ": " .. tostring(velos_need) .. " Velos")
    )
    y = y + G.CONVERT_LINE_DY
	y = append_convert_shop_account_line(fs, y, st, sum, summary_ok)
    y = y + G.CONVERT_SECTION_GAP
	if summary_ok then
		y = append_convert_wrapped_lines(fs, y, convert_sell_owner_lines(sum))
		y = y + G.CONVERT_SECTION_GAP
	end
	y = append_convert_funding_pool_lines(fs, sum, y, summary_ok, pool_only)
	if summary_ok and (pool or 0) <= 0 and planned > 0 and not st.plan_summary_busy then
		fs[#fs + 1] = string.format("label[0.3,%f;%s]", y, esc(UI.convert_pool_empty))
		y = y + G.CONVERT_LINE_DY
	end
    local mp = mcc_plan_mod()
    local auto_on = mp and mp.is_autoconvert_on and mp.is_autoconvert_on(name)
    y = y + G.CONVERT_LINE_DY + 0.08
    fs[#fs + 1] = string.format(
        "checkbox[0.3,%f;autoconvert_toggle;%s;%s]",
        y,
        esc(UI.autoconvert_label),
        auto_on and "true" or "false"
    )
    local qty_y = y + G.CONVERT_QTY_BELOW_AUTO_DY
    local can_convert = summary_ok and planned > 0 and (pool or 0) > 0 and not st.busy
        and not st.plan_summary_busy
    append_sell_action_button_styles(fs, can_convert, "do_convert")
    local qty = st.convert_qty
    fs[#fs + 1] = string.format(
        "button[%f,%f;0.8,%f;convert_qty_dec;-]",
        G.BUY_PANEL_X,
        qty_y,
        G.BUY_ROW_H
    )
    fs[#fs + 1] = string.format(
        "field[%f,%f;1.4,%f;convert_qty;%s;%s]",
        G.QTY_FIELD_X,
        qty_y,
        G.BUY_ROW_H,
        esc(UI.convert_qty_label),
        tostring(qty)
    )
    fs[#fs + 1] = "field_close_on_enter[convert_qty;false]"
    fs[#fs + 1] = string.format(
        "button[%f,%f;0.8,%f;convert_qty_inc;+]",
        G.QTY_INC_X,
        qty_y,
        G.BUY_ROW_H
    )
    fs[#fs + 1] = string.format(
        "button[%f,%f;1.1,%f;convert_qty_all;%s]",
        G.QTY_INC_X + 1.0,
        qty_y,
        G.BUY_ROW_H,
        esc(UI.convert_qty_all)
    )
    fs[#fs + 1] = string.format(
        "button[%f,%f;%f,%f;do_convert;%s]",
        G.CONVERT_BTN_X,
        G.CONVERT_BTN_Y,
        G.CONVERT_BTN_W,
        G.BUY_ROW_H,
        esc(UI.convert_action)
    )
end

local function shop_apply_tab_change(name, st, new_tab)
    local prev = st.tab or "buy"
    if new_tab == prev then
        return
    end
    if prev == "sell" and new_tab ~= "sell" then
        leave_sell_tab_side_effects(name)
        st.sell_hints_ready = false
        st.sell_hints = nil
    end
    st.tab = new_tab
    if new_tab == "sell" then
        if shop_show_discard_tab(name) then
            ensure_sell_inv(name)
            st.sell_slots_ready = sell_list_has_items(name)
            show_shop(name)
        elseif shop_show_sell_tab(name) then
            ensure_sell_inv(name)
            st.sell_slots_ready = sell_list_has_items(name)
            st.sell_hints_ready = false
            sync_sell_hints_for_player(name, function()
                show_shop(name)
            end)
        else
            core.chat_send_player(name, UI.shop_mode_sell_denied)
            st.tab = "buy"
            show_shop(name)
        end
    elseif new_tab == "convert" then
        if not shop_show_convert_tab(name) then
            core.chat_send_player(name, UI.shop_mode_convert_denied)
            st.tab = "buy"
            show_shop(name)
            return
        end
        st.convert_qty = st.convert_qty or 4
        st.plan_summary = nil
        st.plan_summary_fetched_at = nil
        fetch_shop_plan_summary(name, st, function()
            show_shop(name)
        end)
        show_shop(name)
    else
        show_shop(name)
    end
end

local function run_shop_convert(name, st)
    if not shop_session_build_mode(name) then
        core.chat_send_player(name, UI.shop_mode_convert_denied)
        return
    end
    if st.busy or st.plan_summary_busy then
        core.chat_send_player(name, UI.convert_busy)
        return
    end
    local qty = clamp_convert_qty(st.convert_qty, st)
    st.convert_qty = qty
    local mp = mcc_plan_mod()
    if not mp or not mp.run_convert then
        core.chat_send_player(name, UI.convert_failed)
        return
    end
    st.busy = true
    show_shop(name)
    local started, err = mp.run_convert(name, qty, function(ok, msg, data2)
        st.busy = false
        if msg and msg ~= "" then
            if ok then
                core.chat_send_player(name, msg)
            else
                core.chat_send_player(name, UI.convert_failed .. ": " .. tostring(msg))
            end
        end
        if ok then
            st.plan_summary = nil
            st.plan_summary_fetched_at = nil
        end
        fetch_shop_plan_summary(name, st, function()
            show_shop(name)
        end)
    end)
    if not started then
        st.busy = false
        core.chat_send_player(name, UI.convert_failed .. ": " .. tostring(err or "?"))
        show_shop(name)
    end
end

local function build_formspec(name)
    local st = get_state(name)
    if not st then
        return ""
    end
    ensure_shop_tab_for_session(name, st)
    local tab = st.tab or "buy"
    local show_secondary_tab = shop_show_secondary_tab(name)
    local plan_discard_tab = shop_session_plan_mode(name)
    local fs = {
        "formspec_version[6]",
        "size[" .. tostring(G.FORMSPEC_W) .. "," .. tostring(G.FORMSPEC_H) .. "]",
        "position[0.5,0.5]",
        "anchor[0.5,0.5]",
    }
    append_centered_header_label(fs, G.HEADER_Y, UI.title)
    local tab_idx = shop_tab_index_for(name, tab)
    fs[#fs + 1] = "style_type[tabheader;textcolor=#e8f4ff]"
    -- Auto tab width (H-only syntax); no draw_border — fixed W left empty stripe + black edge.
    fs[#fs + 1] = string.format(
        "tabheader[0.3,%f;%f;shop_tabs;%s;%d;true;false]",
        G.TAB_ROW_Y,
        G.TAB_HEADER_H,
        shop_tab_tablist_string(name),
        tab_idx
    )
    append_wallet_hint_label(fs, name, tab, st)

    if tab == "convert" then
        append_convert_tab_body(fs, name, st)
    elseif tab == "buy" then
        local status_line = shop_status_line_text(name)
        if status_line then
			local status_y = shop_status_line_y(name)
			if not shop_session_allows_trade(name) and not shop_session_plan_mode(name) then
				append_centered_header_label(fs, status_y, status_line)
			else
				fs[#fs + 1] = string.format(
					"label[%f,%f;%s]",
					G.TAB_STATUS_LINE_X,
					status_y,
					esc(status_line)
				)
			end
        end
        -- Plan region stats (e.g. "Planungs-Sub …") only in mcc_plan HUD, not in shop UI.
        -- Full category list (all categories, including empty).
        local cat_count = #(st.cats or {})
        if st.cat_idx < 1 then
            st.cat_idx = 1
        end
        if cat_count > 0 and st.cat_idx > cat_count then
            st.cat_idx = cat_count
        end
        fs[#fs + 1] = string.format("label[0.3,%f;%s]", G.CAT_LABEL_Y, esc(UI.categories))
        fs[#fs + 1] = string.format(
            "textlist[%f,%f;%f,%f;catlist;%s;%d;false]",
            G.CAT_LIST_X,
            G.CAT_LIST_Y,
            G.CAT_LIST_W,
            G.CAT_LIST_H,
            category_list_string(st),
            st.cat_idx
        )

        fs[#fs + 1] = string.format(
            "field[%f,%f;%f,0.55;filter;%s;%s]",
            G.ITEM_PANEL_X,
            G.FILTER_ROW_Y,
            G.FILTER_FIELD_W,
            esc(UI.search),
            esc(st.filter or "")
        )
        fs[#fs + 1] = "field_close_on_enter[filter;false]"
        fs[#fs + 1] = string.format(
            "button[%f,%f;1.1,0.55;do_filter;%s]",
            G.FILTER_BTN_X,
            G.FILTER_ROW_Y,
            esc(UI.filter)
        )
        if search_query_active(st) then
            fs[#fs + 1] = string.format(
                "button[%f,%f;1.35,0.55;clear_filter;%s]",
                G.FILTER_CLEAR_X,
                G.FILTER_ROW_Y,
                esc(UI.clear)
            )
        end

        local items = filtered_item_entries(st)
        if search_query_active(st) then
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                G.BUY_PANEL_X,
                G.GRID_Y_DEFAULT - 0.18,
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
        local grid_y = search_query_active(st) and (G.GRID_Y_DEFAULT + 0.2) or G.GRID_Y_DEFAULT
        local grid_bottom = grid_y + (PAGE_H - 1) * G.GRID_ROW_DY + G.GRID_ITEM_H
        local page_y = math.min(grid_bottom + G.PAGE_CTRL_GAP, G.PAGE_Y_MAX)
        local start = (st.page - 1) * PAGE_SIZE
        for row = 0, PAGE_H - 1 do
            for col = 0, PAGE_W - 1 do
                local idx = start + row * PAGE_W + col + 1
                local entry = items[idx]
                local px = G.ITEM_PANEL_X + col * G.GRID_COL_STEP
                local py = grid_y + row * G.GRID_ROW_DY
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
            G.PAGE_PREV_X,
            page_y,
            G.PAGE_BTN_W,
            G.PAGE_CTRL_H
        )
        fs[#fs + 1] = string.format(
            "button[%f,%f;%f,%f;page_next;>]",
            G.PAGE_NEXT_X,
            page_y,
            G.PAGE_BTN_W,
            G.PAGE_CTRL_H
        )
        fs[#fs + 1] = string.format(
            "label[%f,%f;%s]",
            G.PAGE_TEXT_X,
            page_y + G.PAGE_TEXT_Y_OFFSET,
            esc(page_text)
        )

        local sel = st.selected_id and st.by_id[st.selected_id]
        local sel_label = selection_display_text(sel, st.catalog_lang)
        local price = sel and tonumber(sel.buy_price_velos) or 0
        local qty = clamp_shop_qty(st.qty, sel)
        st.qty = qty
        local total = price * qty
        local plan_on_buy = shop_plan_on(name, st)
        local buy_selected_y = plan_on_buy and G.BUY_SELECTED_Y_PLAN or G.BUY_SELECTED_Y
        if sel then
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                G.BUY_PANEL_X,
                buy_selected_y,
                esc(UI.selected .. ":")
            )
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                G.BUY_PANEL_X + 1.35,
                buy_selected_y,
                esc(sel_label)
            )
        else
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                G.BUY_PANEL_X,
                buy_selected_y,
                esc(UI.selected .. ": " .. UI.none_selected)
            )
        end
        if shop_session_plan_mode(name) and plan_on_buy then
            fs[#fs + 1] = string.format(
                "label[%f,%f;%s]",
                G.BUY_PANEL_X,
                G.BUY_PLAN_NOTE_Y,
                esc(UI.plan_note)
            )
        end
        local total_label = plan_on_buy and UI.total_conversion or UI.total
        local price_line = UI.price .. ": " .. tostring(price) .. "  |  " .. total_label .. ": " .. tostring(total)
        fs[#fs + 1] = string.format(
            "label[%f,%f;%s]",
            G.BUY_PANEL_X,
            G.BUY_PRICE_Y,
            esc(price_line)
        )
        fs[#fs + 1] = string.format(
            "button[%f,%f;0.8,%f;qty_dec;-]",
            G.BUY_PANEL_X,
            G.BUY_QTY_ROW_Y,
            G.BUY_ROW_H
        )
        fs[#fs + 1] = string.format(
            "field[%f,%f;1.4,%f;qty;%s;%s]",
            G.QTY_FIELD_X,
            G.BUY_QTY_ROW_Y,
            G.BUY_ROW_H,
            esc(UI.qty),
            tostring(qty)
        )
        fs[#fs + 1] = "field_close_on_enter[qty;false]"
        fs[#fs + 1] = string.format(
            "button[%f,%f;0.8,%f;qty_inc;+]",
            G.QTY_INC_X,
            G.BUY_QTY_ROW_Y,
            G.BUY_ROW_H
        )
        fs[#fs + 1] = string.format(
            "button[%f,%f;2.2,%f;do_buy;%s]",
            G.QTY_BUY_X,
            G.BUY_QTY_ROW_Y,
            G.BUY_ROW_H,
            esc(shop_primary_buy_button_label(name))
        )
        -- Buy tab: no player inventory row (items are delivered via API after "Kaufen").
    elseif tab == "sell" then
        -- Sell tab (build) or discard tab (plan): same slot grid layout.
        ensure_sell_inv(name)
        local zone_title = plan_discard_tab
            and (UI.discard_zone .. " - " .. UI.discard_hint)
            or (UI.sell_zone .. " - " .. UI.sell_hint)
        append_sell_area_label(
            fs,
            G.SELL_ZONE_LABEL_Y,
            zone_title,
            G.SELL_HDR_LABEL_X_SHIFT
        )
        fs[#fs + 1] = "listcolors[#1e2d3acc;#2d4566cc;#8ab4d8ff]"
        fs[#fs + 1] = "style_type[list;size=0.95;spacing=0.08]"
        fs[#fs + 1] = string.format(
            "list[current_player;%s;%f,%f;%d,%d;0]",
            SELL_LIST,
            G.SELL_LIST_X,
            G.SELL_LIST_Y,
            G.SELL_LIST_W,
            G.SELL_LIST_H
        )
        append_sell_area_label(fs, G.INV_ZONE_LABEL_Y, UI.inv_zone, G.INV_LABEL_X_SHIFT)
        fs[#fs + 1] = string.format(
            "list[current_player;main;%f,%f;9,3;9]",
            G.SELL_LIST_X,
            G.SELL_MAIN_Y
        )
        fs[#fs + 1] = string.format(
            "list[current_player;main;%f,%f;9,1;0]",
            G.SELL_LIST_X,
            G.SELL_HOTBAR_Y
        )
        fs[#fs + 1] = "listring[current_player;" .. SELL_LIST .. "]"
        fs[#fs + 1] = "listring[current_player;main]"
        local sell_ready = sell_list_has_items(name)
        if st then
            st.sell_slots_ready = sell_ready
        end
        local action_btn = plan_discard_tab and "plan_discard" or "sell_all"
        append_sell_action_button_styles(fs, sell_ready, action_btn)
        if plan_discard_tab then
            fs[#fs + 1] = string.format(
                "button[0.3,%f;%f,0.55;plan_discard;%s]",
                G.SELL_BTN_Y,
                G.SELL_BTN_W,
                esc(UI.discard_all)
            )
        else
            fs[#fs + 1] = string.format(
                "button[0.3,%f;%f,0.55;sell_all;%s]",
                G.SELL_BTN_Y,
                G.SELL_BTN_W,
                esc(UI.sell_all)
            )
        end
        fs[#fs + 1] = string.format(
            "button[%f,%f;3.5,0.55;return_sell;%s]",
            0.3 + G.SELL_BTN_W + 0.15,
            G.SELL_BTN_Y,
            esc(UI.return_items)
        )
    end

    return table.concat(fs, "")
end

show_shop = function(name)
    local st = get_state(name)
    if not st then
        core.log("warning", "[mcc_bridge shop] show_shop no state player=" .. tostring(name))
        shop_debugf("show_shop no_state player=%s", tostring(name))
        return
    end
    local fs = build_formspec(name)
    if fs == "" then
        core.log("warning", "[mcc_bridge shop] show_shop empty formspec player=" .. tostring(name))
        shop_debugf("show_shop empty_formspec player=%s", tostring(name))
        return
    end
    shop_debugf("show_shop player=%s form_len=%s", name, tostring(#fs))
    core.show_formspec(name, FORMNAME, fs)
    maybe_refresh_shop_plan_summary(name, st)
end

local function refresh_sell_button_if_needed(name)
    local st = player_state[name]
    if not st or (st.tab or "buy") ~= "sell" then
        return
    end
    local now = sell_list_has_items(name)
    if st.sell_slots_ready ~= now then
        st.sell_slots_ready = now
        show_shop(name)
    end
end

local function refresh_after_catalog(name, data)
    local cats, by_id = flatten_catalog(data)
    local st = player_state[name] or {}
    st.cats = cats
    st.by_id = by_id
    st.velos = tonumber(data.velos_spendable) or st.velos or 0
    st.wallet_group_name = tostring(data.wallet_group_name or st.wallet_group_name or "")
    if data.wallet_group_id ~= nil then
        st.wallet_group_id = tonumber(data.wallet_group_id)
    end
    st.tab = st.tab or "buy"
    st.cat_idx = st.cat_idx or 1
    if st.cat_idx > #cats then
        st.cat_idx = 1
    end
    st.page = st.page or 1
    st.qty = st.qty or 1
    st.filter = st.filter or ""
    st.busy = false
    st.session_ok = data.session_ok ~= false
    st.session_paused = data.session_paused == true
    st.catalog_lang = normalize_language_code(
        data.catalog_lang or st.catalog_request_lang or st.catalog_lang or "de"
    )
    if not st.selected_id or not st.by_id[st.selected_id] then
        clear_shop_selection(st)
    else
        st.qty = clamp_shop_qty(st.qty or 1, st.by_id[st.selected_id])
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
    sync_shop_plan_state(name, st)
    ensure_shop_tab_for_session(name, st)
    local function safe_show_shop()
        local ok, err = pcall(show_shop, name)
        if not ok then
            core.log("error", "[mcc_bridge shop] show_shop crashed player=" .. name .. " err=" .. tostring(err))
            shop_debugf("safe_show_shop crash player=%s err=%s", name, tostring(err))
            core.chat_send_player(name, "MCC-Shop UI-Fehler / Shop UI error")
        end
    end
    shop_debugf(
        "refresh_after_catalog player=%s cats=%s velos=%s",
        name,
        tostring(#cats),
        tostring(st.velos or 0)
    )
    -- Open immediately after catalog; do not block on /plan/summary/ (HTTP can lag).
    safe_show_shop()
    maybe_plan_mod_missing_hint(name)
end

local function open_shop_gui(name, resync_attempted)
    shop_debugf("open_shop_gui player=%s resync=%s", name, tostring(resync_attempted))
    if not api_post then
        core.chat_send_player(name, UI.shop_offline)
        return
    end
    local client_lang = client_language_code()
    player_state[name] = player_state[name] or {}
    sync_shop_plan_state(name, player_state[name])
    clear_shop_selection(player_state[name])
    player_state[name].client_lang = client_lang
    player_state[name].catalog_request_lang = client_lang
    api_post("/api/luanti/shop/catalog/", { player = name, lang = client_lang }, function(ok, data)
        if not ok or not data or not data.ok then
            local err = (data and data.error) or "unreachable"
            core.log(
                "warning",
                "[mcc_bridge shop] catalog failed player=" .. name .. " err=" .. tostring(err)
            )
            shop_debugf("catalog_cb failed player=%s ok=%s err=%s", name, tostring(ok), tostring(err))
            core.chat_send_player(name, UI.shop_offline)
            return
        end
        core.log(
            "action",
            "[mcc_bridge shop] catalog ok player="
                .. name
                .. " session_ok="
                .. tostring(data.session_ok)
                .. " paused="
                .. tostring(data.session_paused)
                .. " cats="
                .. tostring(#(data.categories or {}))
        )
        shop_debugf(
            "catalog_cb ok player=%s session_ok=%s paused=%s cats=%s",
            name,
            tostring(data.session_ok),
            tostring(data.session_paused),
            tostring(#(data.categories or {}))
        )
        if data.session_paused == true then
            core.chat_send_player(name, UI.session_paused)
            return
        end
        if data.session_ok == false then
            shop_debugf("catalog session_ok=false player=%s resync=%s", name, tostring(resync_attempted))
            if not resync_attempted then
                local bridge = rawget(_G, "mcc_bridge")
                if bridge and bridge.request_session_join then
                    bridge.request_session_join(name, {})
                end
                core.chat_send_player(name, UI.no_session)
            end
        end
        -- Open catalog UI even without session (buy/sell fail via API until freigabe).
        ensure_sell_inv(name)
        player_state[name] = player_state[name] or {}
        refresh_after_catalog(name, data)
        core.log("action", "[mcc_bridge shop] opening UI player=" .. name)
        shop_debugf("open_shop_gui done player=%s", name)
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

local function shop_field_pressed(fields, key)
    return fields[key] ~= nil
end

local function shop_wants_sell(fields)
    return shop_field_pressed(fields, "do_sell") or shop_field_pressed(fields, "sell_all")
end

local function shop_wants_plan_discard(fields)
    return shop_field_pressed(fields, "plan_discard")
end

local function run_shop_plan_discard(name, st)
    if not shop_session_plan_mode(name) then
        core.chat_send_player(name, UI.shop_mode_sell_denied)
        return
    end
    if st.busy then
        core.chat_send_player(name, UI.sell_busy)
        return
    end
    local player = core.get_player_by_name(name)
    if not player then
        return
    end
    local inv = player:get_inventory()
    if not inv or inv:get_size(SELL_LIST) <= 0 then
        core.chat_send_player(name, UI.nothing_to_discard)
        return
    end
    local limit = math.min(inv:get_size(SELL_LIST), sell_selection_slot_limit())
    local removed = 0
    for i = 1, limit do
        local stack = inv:get_stack(SELL_LIST, i)
        if not stack:is_empty() then
            if plan_discard_stack_allowed(stack) then
                removed = removed + stack:get_count()
                inv:set_stack(SELL_LIST, i, ItemStack(""))
            else
                local leftover = inv:add_item("main", stack)
                inv:set_stack(SELL_LIST, i, ItemStack(""))
                if not leftover:is_empty() then
                    local pos = player:get_pos()
                    if pos then
                        core.add_item(pos, leftover)
                    end
                end
            end
        end
    end
    if removed <= 0 then
        core.chat_send_player(name, UI.nothing_to_discard)
        show_shop(name)
        return
    end
    bridge_sync_inventory_now(player)
    core.chat_send_player(name, string.format(UI.discard_done, removed))
    shop_debugf("plan_discard player=%s removed=%s", name, tostring(removed))
    show_shop(name)
end

local function shop_fields_key_summary(fields)
    local keys = {}
    for k in pairs(fields) do
        keys[#keys + 1] = tostring(k)
    end
    table.sort(keys)
    return table.concat(keys, ",")
end

local function run_shop_sell(name, st)
    if not shop_session_build_mode(name) then
        core.chat_send_player(name, UI.shop_mode_sell_denied)
        return
    end
    if st.busy then
        core.chat_send_player(name, UI.sell_busy)
        return
    end
    if shop_plan_on(name, st) then
        core.chat_send_player(name, UI.plan_sell_disabled)
        show_shop(name)
        return
    end
    local items = collect_sell_items(name)
    shop_debugf("do_sell player=%s items=%s", name, tostring(#items))
    core.log(
        "action",
        "[mcc_bridge shop] do_sell player="
            .. name
            .. " items="
            .. tostring(#items)
    )
    if #items == 0 then
        core.chat_send_player(name, UI.nothing_to_sell)
        return
    end
    st.busy = true
    local tx = name .. "-gui-sell-" .. tostring(os.time())
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
            shop_debugf("do_sell fail player=%s err=%s", name, tostring(err))
            show_shop(name)
            return
        end
        apply_sell_result(name, data)
        st.velos = tonumber(data.velos_spendable) or st.velos
        apply_wallet_from_response(st, data)
        local refunded = tonumber(data.refunded_total) or 0
        if refunded > 0 then
            core.chat_send_player(name, UI.sold .. " +" .. tostring(refunded) .. " " .. UI.velos)
            shop_debugf("do_sell ok player=%s refunded=%s", name, tostring(refunded))
        else
            local rejected = data.rejected or {}
            if #rejected > 0 then
                core.chat_send_player(name, UI.sell_rejected)
                shop_debugf("do_sell rejected player=%s count=%s", name, tostring(#rejected))
            else
                core.chat_send_player(name, UI.not_sellable)
            end
        end
        sync_sell_hints_for_player(name, function()
            show_shop(name)
        end)
    end)
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
        if shop_wants_sell(fields) then
            core.log("warning", "[mcc_bridge shop] sell ignored no state player=" .. name)
            core.chat_send_player(name, "Shop erneut öffnen (/mccshop)")
        end
        return true
    end
    local active_tab = st.tab or "buy"
    local buy_tab = active_tab == "buy"

    if active_tab == "sell" then
        core.log(
            "action",
            "[mcc_bridge shop] receive_fields player="
                .. name
                .. " keys="
                .. shop_fields_key_summary(fields)
        )
    end

    -- Tab bar first: convert tab echoes checkbox/fields on every submit and would block shop_tabs.
    if fields.shop_tabs then
        local idx = tonumber(fields.shop_tabs)
        if idx then
            local new_tab = shop_tab_id_for_index(name, idx)
            shop_apply_tab_change(name, st, new_tab)
        end
        return true
    end

    -- Primary actions first (clients echo qty/filter/catlist on sell tab).
    if fields.do_convert then
        run_shop_convert(name, st)
        return true
    end
    if fields.autoconvert_toggle ~= nil and active_tab == "convert" and not fields.do_convert
        and fields.shop_tabs == nil then
        if shop_session_build_mode(name) then
            local mp = mcc_plan_mod()
            local want = fields.autoconvert_toggle == "true"
            local cur = mp and mp.is_autoconvert_on and mp.is_autoconvert_on(name)
            if mp and mp.set_autoconvert_on and want ~= cur then
                mp.set_autoconvert_on(name, want)
            end
        end
        show_shop(name)
        return true
    end
    if active_tab == "convert" and fields.convert_qty_dec then
        st.convert_qty = clamp_convert_qty((st.convert_qty or 4) - 1, st)
        show_shop(name)
        return true
    end
    if active_tab == "convert" and fields.convert_qty_inc then
        st.convert_qty = clamp_convert_qty((st.convert_qty or 4) + 1, st)
        show_shop(name)
        return true
    end
    if active_tab == "convert" and fields.convert_qty_all then
        local planned = st.plan_summary and tonumber(st.plan_summary.planned_count) or 256
        st.convert_qty = clamp_convert_qty(math.max(planned, 1), st)
        show_shop(name)
        return true
    end
    if active_tab == "convert" and fields.key_enter_field == "convert_qty" then
        st.convert_qty = clamp_convert_qty(tonumber(fields.convert_qty) or st.convert_qty, st)
        show_shop(name)
        return true
    end
    if shop_wants_plan_discard(fields) then
        core.log("action", "[mcc_bridge shop] plan_discard player=" .. name)
        run_shop_plan_discard(name, st)
        return true
    end
    if shop_wants_sell(fields) then
        core.log("action", "[mcc_bridge shop] sell button player=" .. name)
        run_shop_sell(name, st)
        return true
    end

    if fields.do_buy then
        if not shop_session_build_mode(name) and not shop_session_plan_mode(name) then
            core.chat_send_player(name, UI.shop_mode_buy_denied)
            return true
        end
        if st.busy then
            core.chat_send_player(name, UI.buy_busy)
            return true
        end
        local sel = st.by_id and st.by_id[st.selected_id]
        local q = clamp_shop_qty(tonumber(fields.qty) or st.qty or 1, sel)
        st.qty = q
        if not sel then
            core.chat_send_player(name, UI.none_selected)
            return true
        end
        st.busy = true
        local planning = resolve_planning_for_buy(name, st, fields)
        local tx = name .. "-gui-buy-" .. tostring(os.time()) .. "-" .. tostring(sel.id)
        shop_debugf(
            "do_buy player=%s item_id=%s qty=%s planning=%s",
            name,
            tostring(sel.id),
            tostring(q),
            tostring(planning)
        )
        api_post("/api/luanti/shop/buy/", {
            player = name,
            item_id = sel.id,
            quantity = q,
            client_tx_id = tx,
            planning = planning,
            lang = normalize_language_code(st.catalog_lang or client_language_code()),
        }, function(ok, data)
            st.busy = false
            if not ok or not data or not data.ok then
                local err = (data and data.error) or "buy_failed"
                core.chat_send_player(name, UI.buy_failed .. ": " .. shop_buy_error_message(err))
                show_shop(name)
                return
            end
            local p = core.get_player_by_name(name)
            if p and data.grant then
                if not room_for_grant(p, data.grant) then
                    core.chat_send_player(name, UI.inventory_full)
                end
                local inv = p:get_inventory()
                for _, g in ipairs(data.grant) do
                    local stack = ItemStack((g.item_name or "") .. " " .. tostring(g.count or 1))
                    stack = apply_grant_stack(stack, g)
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
            apply_wallet_from_response(st, data)
            core.chat_send_player(name, UI.velos .. ": " .. tostring(st.velos))
            show_shop(name)
        end)
        return true
    end

    if buy_tab and fields.clear_filter then
        st.filter = ""
        st.page = 1
        clear_shop_selection(st)
        show_shop(name)
        return true
    end
    if buy_tab and (fields.do_filter or fields.key_enter_field == "filter") then
        st.filter = fields.filter or st.filter or ""
        st.page = 1
        if normalize_search_query(st.filter) == "" then
            clear_shop_selection(st)
        end
        show_shop(name)
        return true
    end
    if buy_tab and fields.key_enter_field == "qty" then
        local q = tonumber(fields.qty)
        if q then
            local sel = st.selected_id and st.by_id and st.by_id[st.selected_id]
            st.qty = clamp_shop_qty(q, sel)
        end
        show_shop(name)
        return true
    end

    if fields.quit or fields.close then
        if shop_wants_sell(fields) or fields.do_buy ~= nil or fields.do_convert
            or fields.shop_tabs or fields.tab_sell or fields.tab_buy or fields.return_sell then
            return true
        end
        if fields.key_enter_field == "filter" then
            st.filter = fields.filter or st.filter or ""
            st.page = 1
            show_shop(name)
            return true
        end
        if fields.key_enter_field == "qty" then
            local q = tonumber(fields.qty)
            if q then
                local sel = st.selected_id and st.by_id and st.by_id[st.selected_id]
                st.qty = clamp_shop_qty(q, sel)
            end
            show_shop(name)
            return true
        end
        clear_shop_selection(st)
        local p = core.get_player_by_name(name)
        if p then
            clear_sell_inventory_tooltips(p)
        end
        return_sell_slots_to_player(name)
        player_state[name] = nil
        return true
    end
    if fields.return_sell then
        return_sell_slots_to_player(name)
        if shop_session_build_mode(name) and active_tab == "sell" then
            sync_sell_hints_for_player(name, function()
                show_shop(name)
            end)
        else
            show_shop(name)
        end
        return true
    end
    if buy_tab and fields.page_prev then
        st.page = math.max(1, (st.page or 1) - 1)
        show_shop(name)
        return true
    end
    if buy_tab and fields.page_next then
        st.page = (st.page or 1) + 1
        show_shop(name)
        return true
    end
    -- Item grid clicks (before catlist: clients echo textlist on every submit).
    for iid, it in pairs(st.by_id or {}) do
        if not buy_tab then
            break
        end
        if fields["item_" .. iid] ~= nil then
            st.selected_id = iid
            st.qty = clamp_shop_qty(st.qty or 1, it)
            shop_debug_selection_to_player(name, st, it)
            show_shop(name)
            return true
        end
    end
    -- textlist: only act on CHG/DCL (1-based index)
    if buy_tab and fields.catlist then
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
    if buy_tab and fields.qty_dec then
        st.qty = math.max(1, (tonumber(fields.qty) or st.qty or 1) - 1)
        show_shop(name)
        return true
    end
    if buy_tab and fields.qty_inc then
        local sel = st.selected_id and st.by_id and st.by_id[st.selected_id]
        local next_q = (tonumber(fields.qty) or st.qty or 1) + 1
        st.qty = clamp_shop_qty(next_q, sel)
        show_shop(name)
        return true
    end
    if buy_tab and fields.qty and not fields.do_buy then
        local q = tonumber(fields.qty)
        if q then
            local sel = st.selected_id and st.by_id and st.by_id[st.selected_id]
            st.qty = clamp_shop_qty(q, sel)
        end
    end

    if (st.tab or "buy") == "sell" then
        local now = sell_list_has_items(name)
        if st.sell_slots_ready ~= now then
            st.sell_slots_ready = now
            show_shop(name)
        end
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

core.register_on_player_inventory_action(function(player, action, inventory, info)
    if not player or not player_state[player:get_player_name()] then
        return
    end
    if not sell_selection_inventory_touched(action, info) then
        return
    end
    local pname = player:get_player_name()
    core.after(0, function()
        refresh_sell_button_if_needed(pname)
    end)
end)

core.register_allow_player_inventory_action(function(player, action, inv, info)
    if not player or type(info) ~= "table" then
        return
    end
    local pname = player:get_player_name()
    local st = player_state[pname]
    if not st or (st.tab or "buy") ~= "sell" then
        return
    end
    local to_sell = false
    local stack = ItemStack("")
    if action == "move" and info.to_list == SELL_LIST then
        to_sell = true
        if type(info.from_list) == "string" and type(info.from_index) == "number" then
            stack = inv:get_stack(info.from_list, info.from_index)
            local count = tonumber(info.count) or stack:get_count()
            if count > 0 and count < stack:get_count() then
                stack = stack:peek_item(count)
            end
        end
    elseif action == "put" and info.listname == SELL_LIST and info.stack then
        to_sell = true
        stack = info.stack
    end
    if not to_sell then
        return
    end
    if shop_session_plan_mode(pname) then
        if plan_discard_stack_allowed(stack) then
            return
        end
        core.after(0, function()
            core.chat_send_player(pname, UI.discard_move_denied)
        end)
        return 0
    end
    if sell_stack_allowed(pname, stack) then
        return
    end
    local hint = st.sell_hints and st.sell_hints[stack:get_name()]
    local msg = type(hint) == "table" and sell_hint_tooltip_line(hint) or UI.sell_move_denied
    core.after(0, function()
        core.chat_send_player(pname, msg)
    end)
    return 0
end)

function mcc_bridge.init_shop_gui(post_fn)
    api_post = post_fn
end

function mcc_bridge.open_shop_gui(name)
    open_shop_gui(name)
end

function mcc_bridge.shop_gui_on_leave(name)
    local p = core.get_player_by_name(name)
    if p then
        clear_sell_inventory_tooltips(p)
    end
    destroy_sell_inv(name)
    player_state[name] = nil
end
