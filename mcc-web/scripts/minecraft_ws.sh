#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Daphne ASGI server for Minecraft WebSocket events (no Apache required).
# Usage: ./minecraft_ws.sh {start|stop|restart|status}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    VENV_DIR="/data/appl/mcc/venv"
    TMP_DIR="/data/var/mcc/tmp"
    LOG_DIR="/data/var/mcc/logs"
    ENV_FILE="/data/appl/mcc/.env"
else
    VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
    TMP_DIR="$PROJECT_DIR/data/tmp"
    LOG_DIR="$PROJECT_DIR/data/logs"
    ENV_FILE="$PROJECT_DIR/.env"
fi

PYTHON_BIN="$VENV_DIR/bin/python"
DAPHNE_BIN="$VENV_DIR/bin/daphne"
PIDFILE="$TMP_DIR/minecraft-ws.pid"
LOG_FILE="$LOG_DIR/minecraft-ws.log"

mkdir -p "$TMP_DIR" "$LOG_DIR"

load_env() {
    WS_BIND_HOST="0.0.0.0"
    WS_PORT="8002"
    WS_URL_HOST="127.0.0.1"
    if [ -f "$ENV_FILE" ]; then
        # shellcheck disable=SC1090
        set -a
        source <(grep -E '^(MCC_MINECRAFT_WS_(BIND_HOST|PORT|ENABLED|PUBLIC_HOST)|ALLOWED_HOSTS)=' "$ENV_FILE" | sed 's/\r$//')
        set +a
        WS_BIND_HOST="${MCC_MINECRAFT_WS_BIND_HOST:-0.0.0.0}"
        WS_PORT="${MCC_MINECRAFT_WS_PORT:-8002}"
        WS_URL_HOST="$(resolve_ws_url_host "$WS_BIND_HOST" "${ALLOWED_HOSTS:-}")"
    fi
}

# Host for bridge config hints: LAN IP / PUBLIC_HOST; no public DNS when bind is loopback.
is_private_ipv4() {
    local host="$1"
    [[ "$host" =~ ^10\. ]] && return 0
    [[ "$host" =~ ^192\.168\. ]] && return 0
    [[ "$host" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]] && return 0
    return 1
}

resolve_ws_url_host() {
    local bind_host="$1"
    local allowed_hosts="$2"
    if [ -n "${MCC_MINECRAFT_WS_PUBLIC_HOST:-}" ]; then
        echo "$MCC_MINECRAFT_WS_PUBLIC_HOST"
        return
    fi
    case "$bind_host" in
        ""|0.0.0.0|::) ;;
        127.0.0.1|localhost|::1) ;;
        *)
            echo "$bind_host"
            return
            ;;
    esac
    local IFS=','
    for host in $allowed_hosts; do
        host="${host#"${host%%[![:space:]]*}"}"
        host="${host%"${host##*[![:space:]]}"}"
        [ -z "$host" ] && continue
        case "$host" in
            127.0.0.1|localhost|::1) continue ;;
        esac
        if is_private_ipv4 "$host"; then
            echo "$host"
            return
        fi
    done
    case "$bind_host" in
        127.0.0.1|localhost|::1)
            echo "127.0.0.1"
            return
            ;;
    esac
    for host in $allowed_hosts; do
        host="${host#"${host%%[![:space:]]*}"}"
        host="${host%"${host##*[![:space:]]}"}"
        [ -z "$host" ] && continue
        case "$host" in
            127.0.0.1|localhost|::1) continue ;;
        esac
        if [[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$host" == *:* ]]; then
            echo "$host"
            return
        fi
    done
    for host in $allowed_hosts; do
        host="${host#"${host%%[![:space:]]*}"}"
        host="${host%"${host##*[![:space:]]}"}"
        [ -z "$host" ] && continue
        case "$host" in
            127.0.0.1|localhost|::1) continue ;;
        esac
        echo "$host"
        return
    done
    echo "127.0.0.1"
}

ws_events_url() {
    echo "ws://${WS_URL_HOST}:${WS_PORT}/ws/minecraft/events"
}

get_pid() {
    if [ -f "$PIDFILE" ]; then
        cat "$PIDFILE"
    fi
}

is_running() {
    PID=$(get_pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        return 0
    fi
    return 1
}

start() {
    if [ ! -x "$DAPHNE_BIN" ]; then
        echo "Daphne not found at $DAPHNE_BIN (pip install daphne channels?)"
        exit 1
    fi

    if is_running; then
        echo "WebSocket server already running (PID: $(get_pid))"
        exit 1
    fi

    load_env
    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    unset PYTHONPATH

    nohup "$DAPHNE_BIN" -b "$WS_BIND_HOST" -p "$WS_PORT" config.asgi:application >> "$LOG_FILE" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    if is_running; then
        echo "WebSocket server started on ${WS_BIND_HOST}:${WS_PORT} (PID: $(get_pid))"
        echo "URL: $(ws_events_url)"
    else
        echo "WebSocket server failed to start — see $LOG_FILE"
        rm -f "$PIDFILE"
        exit 1
    fi
}

stop() {
    if ! is_running; then
        echo "WebSocket server is not running"
        rm -f "$PIDFILE"
        ORPHANED=$(ps aux | grep -E "[d]aphne.*config.asgi:application" | awk '{print $2}' | tr '\n' ' ')
        if [ -n "$ORPHANED" ]; then
            for pid in $ORPHANED; do
                kill -TERM "$pid" 2>/dev/null || true
            done
        fi
        exit 0
    fi

    PID=$(get_pid)
    echo "Stopping WebSocket server (PID: $PID)..."
    kill -TERM "$PID" 2>/dev/null || true
    for _ in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$PIDFILE"
            echo "WebSocket server stopped"
            exit 0
        fi
        sleep 1
    done
    kill -KILL "$PID" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "WebSocket server force stopped"
}

status() {
    load_env
    if is_running; then
        echo "WebSocket server running (PID: $(get_pid)) on ${WS_BIND_HOST}:${WS_PORT}"
        echo "URL: $(ws_events_url)"
        exit 0
    fi
    echo "WebSocket server is not running"
    exit 1
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop || true; start ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|restart|status}" ; exit 1 ;;
esac
