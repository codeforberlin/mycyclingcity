# Deploy note: symlink mods into the Luanti mods folder, e.g.
# After shop/locale changes: bump `version` in mcc_bridge/mod.conf so clients refresh mod media.
# Client translation cache: delete `~/.minetest/client/mod_storage.sqlite` (and/or
# `~/.local/share/luanti/client/mod_storage.sqlite` on XDG installs) after mcc_bridge locale changes.
# Shop formspec uses hardcoded German in shop_gui.lua (no gettext) to avoid client T@mcc_bridge errors.
# Debug Auswahl line: SHOP_SELECTION_DEBUG_TO_PLAYER in shop_gui.lua (chat + luanti-server.log on item click).
#   ln -sfn "$(pwd)/mcc_bridge" /data/games/mcc/luanti/mods/mcc_bridge
#   ln -sfn "$(pwd)/mcc_texture_painter" /data/games/mcc/luanti/mods/mcc_texture_painter
# Ensure minetest.conf contains:
#   secure.http_mods = mcc_bridge
#   enable_player_registration = false
# After deploy or world restore, run: python manage.py provision_all_luanti_passwords
# Luanti world name (default mycyclingcity): MCC_LUANTI_WORLD in config/settings.py
