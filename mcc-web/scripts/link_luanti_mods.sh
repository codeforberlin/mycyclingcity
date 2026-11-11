#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Symlink Luanti game mods -> /data/appl/mcc/mcc-web/luanti_mod (real files on deploy).
# Does not copy mod content into /data/games/mcc/luanti/mods.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCC_WEB_DIR="${MCC_WEB_DIR:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"

resolve_abs() {
    readlink -f "$1" 2>/dev/null || realpath "$1" 2>/dev/null || echo "$1"
}

# Keep mcc-web in symlink targets (e.g. /data/appl/mcc/mcc-web/luanti_mod), not mcc-web-1.x.y.
MCC_WEB_LINK="${MCC_WEB_DIR}"
LUANTI_MODS_SRC="${MCC_LUANTI_MODS_DIR:-$MCC_WEB_LINK/luanti_mod}"
LUANTI_MODS_SRC_DEPLOYED="$(resolve_abs "$LUANTI_MODS_SRC")"
GAME_MODS_DIR="${MCC_LUANTI_GAME_MODS_DIR:-/data/games/mcc/luanti/mods}"

MCC_LUANTI_MOD_NAMES="${MCC_LUANTI_MOD_NAMES:-mcc_bridge mcc_plan mcc_texture_painter}"

if [ ! -d "$LUANTI_MODS_SRC_DEPLOYED" ]; then
    echo "Luanti mod deploy dir missing: $LUANTI_MODS_SRC_DEPLOYED" >&2
    echo "Run sync_luanti_mod.sh or deploy_production.py first." >&2
    exit 1
fi
if [ ! -d "$GAME_MODS_DIR" ]; then
    echo "Luanti game mods directory missing: $GAME_MODS_DIR" >&2
    exit 1
fi

echo "Luanti mods: symlinks $GAME_MODS_DIR -> $LUANTI_MODS_SRC"

linked=0
for mod in $MCC_LUANTI_MOD_NAMES; do
    src_deployed="$LUANTI_MODS_SRC_DEPLOYED/$mod"
    link_target="$LUANTI_MODS_SRC/$mod"
    dst="$GAME_MODS_DIR/$mod"
    if [ ! -d "$src_deployed" ]; then
        echo "  skip $mod (no directory at $src_deployed)" >&2
        continue
    fi
    if [ -d "$dst" ] && [ ! -L "$dst" ]; then
        echo "  error: $dst exists and is not a symlink (refusing to overwrite)" >&2
        exit 1
    fi
    if [ -L "$dst" ]; then
        current_target="$(readlink "$dst" || true)"
        if [ "$current_target" = "$link_target" ]; then
            echo "  ok $mod -> $link_target"
            linked=$((linked + 1))
            continue
        fi
        rm -f "$dst"
    elif [ -e "$dst" ]; then
        rm -f "$dst"
    fi
    ln -sfn "$link_target" "$dst"
    echo "  linked $mod -> $link_target"
    linked=$((linked + 1))
done

if [ "$linked" -eq 0 ]; then
    echo "No Luanti mods linked." >&2
    exit 1
fi

echo "Done ($linked symlink(s))."
