# Deploy note: symlink this mod into the Luanti mods folder, e.g.
#   ln -sfn "$(pwd)/mcc_bridge" /data/games/mcc/luanti/mods/mcc_bridge
# Ensure minetest.conf contains:
#   secure.http_mods = mcc_bridge
#   enable_player_registration = false
# After deploy or world restore, run: python manage.py provision_all_luanti_passwords
