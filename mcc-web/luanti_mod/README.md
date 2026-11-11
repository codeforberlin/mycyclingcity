# Deploy (production): Git/NAS dev `luanti_mod/` → rsync to `/data/appl/mcc/mcc-web/luanti_mod/`
# (`scripts/sync_luanti_mod.sh`, `deploy_production.py`). Game loads via symlinks only:
# `/data/games/mcc/luanti/mods/mcc_*` → `…/mcc-web/luanti_mod/mcc_*` (`link_luanti_mods.sh`).
# Manual dev symlink example:
# After shop/locale changes: bump `version` in mcc_bridge/mod.conf so clients refresh mod media.
# Client translation cache: delete `~/.minetest/client/mod_storage.sqlite` (and/or
# `~/.local/share/luanti/client/mod_storage.sqlite` on XDG installs) after mcc_bridge locale changes.
# Shop formspec uses hardcoded German in shop_gui.lua (no gettext) to avoid client T@mcc_bridge errors.
# Debug Auswahl line: SHOP_SELECTION_DEBUG_TO_PLAYER in shop_gui.lua (chat + luanti-server.log on item click).
# Bridge debug (server log only), in minetest.conf / Luanti server config:
#   mcc_bridge.debug = session,shop,http,command   # or true / all
#   mcc_bridge.debug_heartbeat = false              # set true to log /heartbeat/ (very noisy)
# After change: luanti_server.sh restart; tail -f luanti-server.log | grep 'mcc_bridge:debug'
#   ln -sfn "$(pwd)/mcc_bridge" /data/games/mcc/luanti/mods/mcc_bridge
#   ln -sfn "$(pwd)/mcc_texture_painter" /data/games/mcc/luanti/mods/mcc_texture_painter
#   ln -sfn "$(pwd)/mcc_plan" /data/games/mcc/luanti/mods/mcc_plan
# World: load_mod_mcc_plan = true for Plan-Shop (/mccplan, Hologramme). Optional for isolating
# mcc_bridge: set load_mod_mcc_plan = false and remove broken symlink — Shop Kaufen/Verkauf still works;
# server logs once [mcc_bridge] partner_mods plan=missing; first Shop in build shows a one-time chat hint.
# luanti_server.sh enables mcc_bridge, mcc_plan, mcc_texture_painter on start.
# Ensure minetest.conf contains:
#   secure.http_mods = mcc_bridge
#   enable_player_registration = false
# Void/singlenode dig helper (default true): routes drops into inventory during dig only.
# Set false for unmodified Luanti/Mineclonia drop behaviour (e.g. local testing):
#   mcc_bridge.void_safe_dig = true
#
# Treppen (Mineclonia): Im Shop nur Basis-Stufen (z. B. mcl_stairs:stair_oak). Innen- und
# Außen-Ecken sind Welt-Knoten (_inner/_outer); die Engine wählt sie beim Platzieren.
# Abbau liefert wieder die Basis-Stufe ins Inventar — an der Ecke neu setzen erzeugt die Form.
# Plan-Hologramme zeigen die gewählte Form; Plan-Rückerstattung nutzt den Shop-Basis-Itemstring.
# After deploy or world restore, run: python manage.py provision_all_luanti_passwords
# Luanti world name (default mycyclingcity): MCC_LUANTI_WORLD in config/settings.py
