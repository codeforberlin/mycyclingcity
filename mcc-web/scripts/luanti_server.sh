#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    luanti_server.sh
# @note    Start/stop/status for the Luanti (Mineclonia) dedicated server.
# Usage: ./luanti_server.sh {start|stop|status|restart}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    TMP_DIR="/data/var/mcc/tmp"
    LOG_DIR="/data/var/mcc/logs"
    DEFAULT_SERVER_DIR="/data/games/mcc/luanti"
else
    TMP_DIR="$PROJECT_DIR/data/tmp"
    LOG_DIR="$PROJECT_DIR/data/logs"
    DEFAULT_SERVER_DIR="${MCC_LUANTI_SERVER_DIR:-/data/games/mcc/luanti}"
fi

SERVER_DIR="${MCC_LUANTI_SERVER_DIR:-$DEFAULT_SERVER_DIR}"
PIDFILE="${MCC_LUANTI_SERVER_PIDFILE:-$TMP_DIR/luanti-server.pid}"
LOG_FILE="${MCC_LUANTI_SERVER_LOG:-$LOG_DIR/luanti-server.log}"
WORLD_NAME="${MCC_LUANTI_WORLD:-world}"
CONFIG_FILE="${MCC_LUANTI_CONFIG:-$SERVER_DIR/minetest.conf}"
BIN_NAME="${MCC_LUANTI_BIN_NAME:-luantiserver}"
STOP_WAIT_SECONDS="${MCC_LUANTI_STOP_WAIT:-30}"

mkdir -p "$TMP_DIR" "$LOG_DIR"

read_pid() {
    if [ -f "$PIDFILE" ]; then
        tr -d ' \n\r\t' < "$PIDFILE"
    fi
}

pid_alive() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

verify_pid() {
    local pid="$1"
    local cmdline
    if ! pid_alive "$pid"; then
        return 1
    fi
    if [ ! -r "/proc/$pid/cmdline" ]; then
        return 1
    fi
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
    case "$cmdline" in
        *luantiserver*|*minetestserver*) return 0 ;;
        *) return 1 ;;
    esac
}

server_running() {
    local pid
    pid=$(read_pid "$PIDFILE")
    verify_pid "$pid"
}

find_bin() {
    if [ -x "$SERVER_DIR/bin/$BIN_NAME" ]; then
        echo "$SERVER_DIR/bin/$BIN_NAME"
        return 0
    fi
    if [ -x "$SERVER_DIR/bin/minetestserver" ]; then
        echo "$SERVER_DIR/bin/minetestserver"
        return 0
    fi
    echo "Luanti server binary not found in $SERVER_DIR/bin" >&2
    return 1
}

find_orphan_pids() {
    local pid cmdline cwd work_dir_norm
    work_dir_norm=$(readlink -f "$SERVER_DIR" 2>/dev/null || echo "$SERVER_DIR")
    for pid in $(pgrep -f 'luantiserver|minetestserver' 2>/dev/null || true); do
        if ! pid_alive "$pid"; then
            continue
        fi
        cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
        if [ -n "$cwd" ] && [ "$cwd" = "$work_dir_norm" ]; then
            echo "$pid"
            continue
        fi
        if [ -r "/proc/$pid/cmdline" ]; then
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
            case "$cmdline" in
                *"$SERVER_DIR"*) echo "$pid" ;;
            esac
        fi
    done
}

start_server() {
    local bin world_path
    if [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR" ]; then
        echo "Luanti directory missing: ${SERVER_DIR:-"(unset)"}"
        return 1
    fi
    if server_running; then
        echo "Luanti already running (PID: $(read_pid "$PIDFILE"))"
        return 0
    fi
    if [ -n "$(find_orphan_pids)" ]; then
        echo "Luanti appears already running without PID file; refusing start. Use stop first."
        find_orphan_pids | while read -r p; do echo "  orphan PID: $p"; done
        return 1
    fi
    bin=$(find_bin) || return 1
    world_path="$SERVER_DIR/worlds/$WORLD_NAME"
    if [ ! -d "$world_path" ]; then
        echo "World missing: $world_path"
        return 1
    fi
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Config missing: $CONFIG_FILE"
        return 1
    fi

    cd "$SERVER_DIR" || return 1
    : > "$LOG_FILE"
    nohup "$bin" --world "$world_path" --config "$CONFIG_FILE" \
        < /dev/null >> "$LOG_FILE" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    if server_running; then
        echo "Luanti started (PID: $(read_pid "$PIDFILE"))"
        echo "Dir: $SERVER_DIR"
        echo "World: $WORLD_NAME"
        echo "Log: $LOG_FILE"
        return 0
    fi
    echo "Luanti failed to start; see $LOG_FILE"
    return 1
}

stop_graceful() {
    local pid="$1"
    local i
    echo "Stopping Luanti (PID: $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    for i in $(seq 1 "$STOP_WAIT_SECONDS"); do
        if ! pid_alive "$pid"; then
            rm -f "$PIDFILE"
            echo "Luanti stopped"
            return 0
        fi
        sleep 1
    done
    echo "Luanti did not stop in time, sending SIGKILL..."
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
    if ! pid_alive "$pid"; then
        rm -f "$PIDFILE"
        echo "Luanti force stopped"
        return 0
    fi
    echo "Luanti could not be stopped"
    return 1
}

kill_orphans() {
    local pid found=0
    for pid in $(find_orphan_pids); do
        found=1
        echo "Found orphaned Luanti PID: $pid"
        kill -TERM "$pid" 2>/dev/null || true
    done
    if [ "$found" -eq 1 ]; then
        sleep 2
        for pid in $(find_orphan_pids); do
            kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned Luanti PID: $pid"
        done
    fi
}

prepare_sessions_before_stop() {
    # Kick players via Django so /session/leave/ can persist inventories before SIGTERM.
    local manage="$PROJECT_DIR/manage.py"
    local py=""
    local wait_s="${MCC_LUANTI_PREPARE_WAIT:-25}"
    if [ -x "/data/appl/mcc/venv/bin/python" ]; then
        py="/data/appl/mcc/venv/bin/python"
    elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
        py="$VIRTUAL_ENV/bin/python"
    elif command -v python3 >/dev/null 2>&1; then
        py="$(command -v python3)"
    fi
    if [ -z "$py" ] || [ ! -f "$manage" ]; then
        echo "Warning: cannot prepare sessions (python/manage.py missing)"
        return 0
    fi
    echo "Preparing Luanti sessions (save inventories, end sessions)..."
    if ! "$py" "$manage" luanti_prepare_shutdown --wait "$wait_s"; then
        echo "Warning: luanti_prepare_shutdown failed; continuing with stop"
    fi
}

stop_server() {
    local pid
    prepare_sessions_before_stop
    pid=$(read_pid "$PIDFILE")
    if [ -z "$pid" ] || ! pid_alive "$pid"; then
        echo "Luanti is not running (no valid PID file)"
        rm -f "$PIDFILE"
        kill_orphans
        return 0
    fi
    stop_graceful "$pid"
    local rc=$?
    kill_orphans
    return $rc
}

status_server() {
    local pid
    pid=$(read_pid "$PIDFILE")
    if verify_pid "$pid"; then
        echo "Luanti running (PID: $pid)"
        echo "Dir: $SERVER_DIR"
        echo "World: $WORLD_NAME"
        echo "Config: $CONFIG_FILE"
        echo "Log: $LOG_FILE"
        return 0
    fi
    echo "Luanti stopped"
    echo "Dir: $SERVER_DIR"
    echo "World: $WORLD_NAME"
    echo "Config: $CONFIG_FILE"
    echo "Log: $LOG_FILE"
    return 1
}

case "${1:-}" in
    start) start_server ;;
    stop) stop_server ;;
    restart)
        stop_server || true
        start_server
        ;;
    status) status_server ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 2
        ;;
esac
