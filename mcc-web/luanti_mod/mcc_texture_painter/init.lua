-- Copyright (c) 2026 SAI-Lab / MyCyclingCity
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- Mineclonia tool: replace node types while keeping param2 (rotation/facing).

local WAND_NAME = "mcc_texture_painter:painter_wand"
local HOTBAR_SIZE = 8
local ACTIONBAR_TTL = 3

-- Per-player HUD id for actionbar-style feedback.
local actionbar_hud = {}

local function player_can_use(name)
	local privs = core.get_player_privs(name)
	return privs.worldedit == true or privs.painter == true
end

local function deny_priv(player)
	core.chat_send_player(
		player:get_player_name(),
		core.colorize("#FF5555", "You need the worldedit or painter privilege to use this tool.")
	)
end

local function player_may_modify_at(name, pos)
	if not core.is_protected(pos, name) then
		return true
	end
	local privs = core.get_player_privs(name)
	return privs.protection_bypass == true
end

-- Returns false if the action must be cancelled (protected and no bypass).
local function player_can_build_at(player, pos)
	local name = player:get_player_name()
	if player_may_modify_at(name, pos) then
		return true
	end
	core.chat_send_player(
		name,
		core.colorize("#FF5555", "This area is protected. You cannot modify blocks here.")
	)
	return false
end

local function sort_pos(pos1, pos2)
	local p1 = vector.copy(pos1)
	local p2 = vector.copy(pos2)
	if p1.x > p2.x then
		p1.x, p2.x = p2.x, p1.x
	end
	if p1.y > p2.y then
		p1.y, p2.y = p2.y, p1.y
	end
	if p1.z > p2.z then
		p1.z, p2.z = p2.z, p1.z
	end
	return p1, p2
end

local function is_airlike_node_name(name)
	if not name or name == "" then
		return true
	end
	if name == "ignore" or name:find(":ignore") then
		return true
	end
	if name == "air" or name:find(":air$") then
		return true
	end
	local def = core.registered_nodes[name]
	if def and def.air_equivalent then
		return true
	end
	return false
end

-- Paint source must be a known, placeable node (hotbar item).
local function is_valid_paint_source(name)
	if is_airlike_node_name(name) then
		return false
	end
	return core.registered_nodes[name] ~= nil
end

-- Paint target: allow unknown/legacy node names still stored in the map (conversion fixes).
local function can_paint_onto(name)
	return not is_airlike_node_name(name)
end

-- Hotbar slot to the right of the wielded wand (wrap within 1..HOTBAR_SIZE).
local function paint_source_index(wield_index)
	return (wield_index % HOTBAR_SIZE) + 1
end

local function get_paint_source_stack(player)
	local inv = player:get_inventory()
	if not inv then
		return nil
	end
	local wield = player:get_wield_index()
	local idx = paint_source_index(wield)
	return inv:get_stack("main", idx)
end

-- First inventory list index (1-based) holding node_name, or nil.
local function find_stack_slot(inv, node_name, hotbar_only)
	local last = hotbar_only and HOTBAR_SIZE or inv:get_size("main")
	for i = 1, last do
		local stack = inv:get_stack("main", i)
		if not stack:is_empty() and stack:get_name() == node_name then
			return i
		end
	end
	return nil
end

local function first_empty_hotbar_slot(inv)
	for i = 1, HOTBAR_SIZE do
		if inv:get_stack("main", i):is_empty() then
			return i
		end
	end
	return nil
end

-- Select node in hotbar or add a single reference stack (not consumed when painting).
local function ensure_hotbar_reference(player, node_name)
	local inv = player:get_inventory()
	if not inv then
		return false
	end

	local slot = find_stack_slot(inv, node_name, true)
	if not slot then
		slot = find_stack_slot(inv, node_name, false)
	end
	if slot then
		player:set_wield_index(slot)
		return true
	end

	local target = first_empty_hotbar_slot(inv)
	if not target then
		core.chat_send_player(
			player:get_player_name(),
			core.colorize("#FF5555", "No free hotbar slot to add the selected node.")
		)
		return false
	end

	inv:set_stack("main", target, ItemStack(node_name .. " 1"))
	player:set_wield_index(target)
	return true
end

local function show_actionbar(player, text)
	local name = player:get_player_name()
	local hud_id = actionbar_hud[name]
	if not hud_id then
		hud_id = player:hud_add({
			hud_elem_type = "text",
			name = "mcc_texture_painter_actionbar",
			alignment = { x = 0, y = 0 },
			position = { x = 0.5, y = 0.88 },
			offset = { x = 0, y = 0 },
			z_index = 100,
			number = 0xFFFFFF,
			text = text,
		})
		actionbar_hud[name] = hud_id
	else
		player:hud_change(hud_id, "text", text)
	end

	core.after(ACTIONBAR_TTL, function()
		local p = core.get_player_by_name(name)
		if not p then
			actionbar_hud[name] = nil
			return
		end
		local id = actionbar_hud[name]
		if id then
			p:hud_change(id, "text", "")
		end
	end)
end

local function play_quiet_place_sound(player)
	core.sound_play(
		{ name = "default_place_node", gain = 0.25 },
		{ to_player = player:get_player_name() },
		true
	)
end

local function on_wand_use(itemstack, user, pointed_thing)
	if not user or not user:is_player() then
		return itemstack
	end
	if pointed_thing.type ~= "node" then
		return itemstack
	end

	local player = user
	local name = player:get_player_name()
	if not player_can_use(name) then
		deny_priv(player)
		return itemstack
	end

	local pos = pointed_thing.under
	if not player_can_build_at(player, pos) then
		return itemstack
	end

	local source = get_paint_source_stack(player)
	if not source or source:is_empty() then
		core.chat_send_player(
			name,
			core.colorize(
				"#FFAA00",
				"Place a node in the hotbar slot to the right of the painter wand."
			)
		)
		return itemstack
	end

	local new_name = source:get_name()
	if not is_valid_paint_source(new_name) then
		core.chat_send_player(
			name,
			core.colorize(
				"#FFAA00",
				"The selected hotbar item is not a known placeable node: " .. new_name
			)
		)
		return itemstack
	end

	local old = core.get_node(pos)
	if not can_paint_onto(old.name) then
		core.chat_send_player(
			name,
			core.colorize("#FFAA00", "Cannot paint this block type: " .. tostring(old.name))
		)
		return itemstack
	end

	if old.name == new_name then
		return itemstack
	end

	core.set_node(pos, { name = new_name, param2 = old.param2 })
	play_quiet_place_sound(player)
	return itemstack
end

local function on_wand_place(itemstack, placer, pointed_thing)
	if not placer or not placer:is_player() then
		return itemstack
	end
	if pointed_thing.type ~= "node" then
		return itemstack
	end

	local player = placer
	local name = player:get_player_name()
	if not player_can_use(name) then
		deny_priv(player)
		return itemstack
	end

	local pos = pointed_thing.under
	if not player_can_build_at(player, pos) then
		return itemstack
	end

	local node = core.get_node(pos)
	if not can_paint_onto(node.name) then
		core.chat_send_player(
			name,
			core.colorize("#FFAA00", "Cannot sample this block type: " .. tostring(node.name))
		)
		return itemstack
	end

	if ensure_hotbar_reference(player, node.name) then
		show_actionbar(player, "Selected node: " .. node.name)
	end
	return itemstack
end

core.register_on_leaveplayer(function(player)
	actionbar_hud[player:get_player_name()] = nil
end)

core.register_privilege("painter", {
	description = "Use the texture painter wand (node replace, eyedropper)",
	give_to_singleplayer = true,
})

-- WorldEdit //replace only accepts registered node names; legacy map IDs need name-based replace.
core.register_chatcommand("legacy_replace", {
	params = "<legacy node> <registered node>",
	description = "Replace legacy node names in the current WorldEdit region (//pos1, //pos2)",
	func = function(name, param)
		if not player_can_use(name) then
			return false, "Need the worldedit or painter privilege."
		end
		local search_name, replace_name = param:match("^(%S+)%s+(%S+)$")
		if not search_name or not replace_name then
			return false, "Usage: /legacy_replace <legacy node> <registered node>"
		end
		if not is_valid_paint_source(replace_name) then
			return false, "Replace target must be a registered node: " .. replace_name
		end
		local we = rawget(_G, "worldedit")
		if not we or not we.pos1 or not we.pos1[name] or not we.pos2 or not we.pos2[name] then
			return false, "Set a WorldEdit region with //pos1 and //pos2 first."
		end
		local pos1, pos2 = sort_pos(we.pos1[name], we.pos2[name])
		local replaced = 0
		local skipped_prot = 0
		for z = pos1.z, pos2.z do
			for y = pos1.y, pos2.y do
				for x = pos1.x, pos2.x do
					local pos = { x = x, y = y, z = z }
					local node = core.get_node(pos)
					if node.name == search_name then
						if not player_may_modify_at(name, pos) then
							skipped_prot = skipped_prot + 1
						else
							core.set_node(pos, { name = replace_name, param2 = node.param2 })
							replaced = replaced + 1
						end
					end
				end
			end
		end
		local msg = replaced .. " node(s) replaced (" .. search_name .. " -> " .. replace_name .. ")"
		if skipped_prot > 0 then
			msg = msg .. ", " .. skipped_prot .. " protected (skipped)"
		end
		return true, msg
	end,
})

core.register_tool(WAND_NAME, {
	description = "Texture & Node Painter Wand",
	inventory_image = "default_stick.png",
	wield_image = "default_stick.png",
	stack_max = 1,
	tool_capabilities = {
		full_punch_interval = 99,
		max_drop_level = 0,
	},
	on_use = on_wand_use,
	on_place = on_wand_place,
})
