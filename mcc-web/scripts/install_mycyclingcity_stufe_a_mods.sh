#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Copy Phase-1 (Stufe A) mods into the mycyclingcity game tree:
#   carts (MTG) + mesecons core stack (upstream, MTG-compatible).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCC_WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
LUANTI_ROOT="${MCC_LUANTI_ROOT:-/data/games/mcc/luanti}"
GAME_MODS="$LUANTI_ROOT/games/mycyclingcity/mods"
MTG_MODS="${MINETEST_GAME_MODS:-/usr/share/luanti/games/minetest_game/mods}"
MESECONS_SRC="${MESECONS_SRC:-}"

if [ -z "$MESECONS_SRC" ]; then
    MESECONS_TMP="$(mktemp -d)"
    trap 'rm -rf "$MESECONS_TMP"' EXIT
    git clone --depth 1 https://github.com/minetest-mods/mesecons.git "$MESECONS_TMP"
    MESECONS_SRC="$MESECONS_TMP"
fi

mkdir -p "$GAME_MODS"

for mod in mesecons mesecons_gamecompat mesecons_wires mesecons_mvps mesecons_pistons mesecons_alias; do
    rm -rf "$GAME_MODS/$mod"
    cp -a "$MESECONS_SRC/$mod" "$GAME_MODS/$mod"
done

rm -rf "$GAME_MODS/carts"
cp -a "$MTG_MODS/carts" "$GAME_MODS/carts"

# Legacy schematic node names (Mineclonia export)
ALIAS_FILE="$GAME_MODS/mesecons_alias/init.lua"
if [ -f "$ALIAS_FILE" ] && ! grep -q 'mesecons_piston:piston_pusher_normal' "$ALIAS_FILE"; then
    cat >>"$ALIAS_FILE" <<'EOF'

-- Mineclonia / old schematics (singular mod prefix)
minetest.register_alias("mesecons_piston:piston_pusher_normal", "mesecons_pistons:piston_pusher_normal")
EOF
fi

echo "Stufe A mods installed under $GAME_MODS"
ls -1d "$GAME_MODS"/{carts,mesecons,mesecons_wires,mesecons_pistons,mesecons_alias} 2>/dev/null