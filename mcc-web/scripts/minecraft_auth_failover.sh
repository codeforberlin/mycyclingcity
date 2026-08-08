#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft_auth_failover.sh
# @note    Toggle Velocity online-mode and restart proxy for Auth-Failover.
# Usage: ./minecraft_auth_failover.sh {status|set-online-mode true|false|restart-velocity}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROXY_SCRIPT="${SCRIPT_DIR}/minecraft_proxy.sh"

if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    DEFAULT_VELOCITY_DIR="/data/games/mcc/proxy"
else
    DEFAULT_VELOCITY_DIR="${MCC_MINECRAFT_VELOCITY_DIR:-}"
fi

VELOCITY_DIR="${MCC_MINECRAFT_VELOCITY_DIR:-$DEFAULT_VELOCITY_DIR}"
# Velocity 3 uses velocity.toml; some installs use config.toml
CONFIG_CANDIDATES=(
    "${VELOCITY_DIR}/velocity.toml"
    "${VELOCITY_DIR}/config.toml"
)

find_config() {
    local f
    for f in "${CONFIG_CANDIDATES[@]}"; do
        if [[ -f "$f" ]]; then
            echo "$f"
            return 0
        fi
    done
    return 1
}

read_online_mode() {
    local cfg
    cfg="$(find_config)" || {
        echo "config_missing"
        return 1
    }
    # Match online-mode = true|false (toml)
    local line
    line="$(grep -E '^[[:space:]]*online-mode[[:space:]]*=' "$cfg" | head -n1 || true)"
    if [[ -z "$line" ]]; then
        echo "unknown ($cfg)"
        return 0
    fi
    if echo "$line" | grep -qi 'true'; then
        echo "true ($cfg)"
    elif echo "$line" | grep -qi 'false'; then
        echo "false ($cfg)"
    else
        echo "unknown ($cfg): $line"
    fi
}

set_online_mode() {
    local want="$1"
    if [[ "$want" != "true" && "$want" != "false" ]]; then
        echo "online-mode must be true or false" >&2
        return 1
    fi
    local cfg
    cfg="$(find_config)" || {
        echo "No velocity.toml/config.toml under $VELOCITY_DIR" >&2
        return 1
    }
    if grep -qE '^[[:space:]]*online-mode[[:space:]]*=' "$cfg"; then
        # portable sed: write temp
        local tmp
        tmp="$(mktemp)"
        sed -E "s/^[[:space:]]*online-mode[[:space:]]*=.*/online-mode = ${want}/" "$cfg" >"$tmp"
        mv "$tmp" "$cfg"
    else
        printf '\nonline-mode = %s\n' "$want" >>"$cfg"
    fi
    echo "Set online-mode = ${want} in ${cfg}"
}

cmd_status() {
    echo "VELOCITY_DIR=${VELOCITY_DIR:-unset}"
    if [[ -z "${VELOCITY_DIR}" ]]; then
        echo "online-mode=unknown (no VELOCITY_DIR)"
        return 1
    fi
    echo -n "online-mode="
    read_online_mode || true
    if [[ -x "$PROXY_SCRIPT" ]]; then
        "$PROXY_SCRIPT" velocity-status || true
    fi
}

cmd_restart() {
    if [[ ! -x "$PROXY_SCRIPT" ]]; then
        echo "minecraft_proxy.sh not executable: $PROXY_SCRIPT" >&2
        return 1
    fi
    "$PROXY_SCRIPT" velocity-stop || true
    "$PROXY_SCRIPT" velocity-start
}

usage() {
    echo "Usage: $0 {status|set-online-mode true|false|restart-velocity}"
}

main() {
    local cmd="${1:-}"
    case "$cmd" in
        status)
            cmd_status
            ;;
        set-online-mode)
            set_online_mode "${2:-}"
            ;;
        restart-velocity)
            cmd_restart
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
