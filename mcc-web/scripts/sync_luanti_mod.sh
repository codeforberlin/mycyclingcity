#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Rsync Luanti mod *files* from NAS dev into the deployed mcc-web tree.
# Game server loads them via symlinks only (see link_luanti_mods.sh).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCC_WEB_DIR="${MCC_WEB_DIR:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"

resolve_abs() {
    readlink -f "$1" 2>/dev/null || realpath "$1" 2>/dev/null || echo "$1"
}

MCC_WEB_DIR="$(resolve_abs "$MCC_WEB_DIR")"
DEPLOY_DIR="${MCC_LUANTI_MODS_DIR:-$MCC_WEB_DIR/luanti_mod}"
DEPLOY_DIR="$(resolve_abs "$DEPLOY_DIR")"

MCC_LUANTI_MOD_NAMES="${MCC_LUANTI_MOD_NAMES:-mcc_bridge mcc_plan mcc_texture_painter}"
RSYNC_DELETE="${MCC_LUANTI_MOD_SYNC_DELETE:-1}"

pick_sync_source() {
    if [ -n "${MCC_LUANTI_MODS_SYNC_SRC:-}" ] && [ -d "$MCC_LUANTI_MODS_SYNC_SRC" ]; then
        echo "$MCC_LUANTI_MODS_SYNC_SRC"
        return 0
    fi
    local candidate
    for candidate in \
        "/home/roland/nas/public/dev/mycyclingcity/mcc-web/luanti_mod" \
        "/nas/public/dev/mycyclingcity/mcc-web/luanti_mod"; do
        if [ -d "$candidate" ]; then
            local cand_abs
            cand_abs="$(resolve_abs "$candidate")"
            if [ "$cand_abs" != "$DEPLOY_DIR" ]; then
                echo "$cand_abs"
                return 0
            fi
        fi
    done
    return 1
}

if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync not found" >&2
    exit 1
fi

mkdir -p "$DEPLOY_DIR"

SOURCE=""
if SOURCE_DIR="$(pick_sync_source)"; then
    SOURCE="$(resolve_abs "$SOURCE_DIR")"
fi

if [ -z "$SOURCE" ]; then
  echo "Luanti mod sync: no NAS dev source (set MCC_LUANTI_MODS_SYNC_SRC); keeping $DEPLOY_DIR"
  if [ ! -d "$DEPLOY_DIR/mcc_bridge" ] && [ ! -d "$DEPLOY_DIR/mcc_plan" ]; then
    echo "  error: deploy target has no mcc_* mods" >&2
    exit 1
  fi
  exit 0
fi

echo "Luanti mod sync: $SOURCE -> $DEPLOY_DIR"

rsync_opts=(-a)
if [ "$RSYNC_DELETE" = "1" ]; then
    rsync_opts+=(--delete)
fi

synced=0
for mod in $MCC_LUANTI_MOD_NAMES; do
    src_mod="$SOURCE/$mod"
    if [ ! -d "$src_mod" ]; then
        echo "  skip $mod (missing in source)" >&2
        continue
    fi
    dest_mod="$DEPLOY_DIR/$mod"
    mkdir -p "$dest_mod"
    rsync "${rsync_opts[@]}" "$src_mod/" "$dest_mod/"
    echo "  synced $mod"
    synced=$((synced + 1))
done

# Optional README at luanti_mod root (not a loadable mod)
if [ -f "$SOURCE/README.md" ]; then
    rsync -a "$SOURCE/README.md" "$DEPLOY_DIR/"
fi

if [ "$synced" -eq 0 ]; then
    echo "Luanti mod sync: nothing synced" >&2
    exit 1
fi

echo "Done ($synced mod(s)) -> $DEPLOY_DIR"
