#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Management script for MCC Minecraft worker
# Usage: ./minecraft.sh {start|stop|restart|status}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prüfe ob wir in Produktion sind (Pfad enthält /data/appl/mcc)
if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    VENV_DIR="/data/appl/mcc/venv"
    TMP_DIR="/data/var/mcc/tmp"
    LOG_DIR="/data/var/mcc/logs"
else
    # Entwicklung: lokale Verzeichnisse
    VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
    TMP_DIR="$PROJECT_DIR/tmp"
    LOG_DIR="$PROJECT_DIR/logs"
fi

PYTHON_BIN="$VENV_DIR/bin/python"
PIDFILE="$TMP_DIR/minecraft.pid"
SNAPSHOT_PIDFILE="$TMP_DIR/minecraft-snapshot.pid"
LOG_FILE="$LOG_DIR/minecraft-worker.log"
SNAPSHOT_LOG_FILE="$LOG_DIR/minecraft-snapshot.log"

mkdir -p "$TMP_DIR"
mkdir -p "$LOG_DIR"

get_pid() {
    if [ -f "$PIDFILE" ]; then
        cat "$PIDFILE"
    fi
}

get_snapshot_pid() {
    if [ -f "$SNAPSHOT_PIDFILE" ]; then
        cat "$SNAPSHOT_PIDFILE"
    fi
}

is_running() {
    PID=$(get_pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

is_snapshot_running() {
    PID=$(get_snapshot_pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

start() {
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "Python not found at $PYTHON_BIN"
        exit 1
    fi

    if is_running; then
        echo "Worker already running (PID: $(get_pid))"
        exit 1
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_bridge_worker >> "$LOG_FILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "Worker started (PID: $(get_pid))"
}

start_snapshot() {
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "Python not found at $PYTHON_BIN"
        exit 1
    fi

    if is_snapshot_running; then
        echo "Snapshot worker already running (PID: $(get_snapshot_pid))"
        exit 1
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_snapshot_worker >> "$SNAPSHOT_LOG_FILE" 2>&1 &
    echo $! > "$SNAPSHOT_PIDFILE"
    echo "Snapshot worker started (PID: $(get_snapshot_pid))"
}

stop() {
    if ! is_running; then
        echo "Worker is not running"
        if [ -f "$PIDFILE" ]; then
            rm -f "$PIDFILE"
        fi
        # Also check for orphaned processes
        ORPHANED=$(pgrep -f "minecraft_bridge_worker" | grep -v "^$$")
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned worker process(es): $ORPHANED"
            kill -TERM $ORPHANED 2>/dev/null
            sleep 2
            # Force kill if still running
            STILL_RUNNING=$(pgrep -f "minecraft_bridge_worker" | grep -v "^$$")
            if [ -n "$STILL_RUNNING" ]; then
                kill -KILL $STILL_RUNNING 2>/dev/null
                echo "Force killed orphaned worker process(es)"
            fi
        fi
        exit 0
    fi

    PID=$(get_pid)
    echo "Stopping worker (PID: $PID)..."
    kill -TERM "$PID" 2>/dev/null || {
        echo "Warning: Could not send TERM signal to PID $PID"
        # Process might already be gone, check if PID file is stale
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$PIDFILE"
            echo "Worker already stopped (stale PID file)"
            exit 0
        fi
    }

    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$PIDFILE"
            echo "Worker stopped gracefully"
            exit 0
        fi
        sleep 1
    done

    # Force kill if TERM didn't work
    echo "Worker did not stop in time, forcing kill..."
    kill -KILL "$PID" 2>/dev/null || echo "Warning: Could not send KILL signal to PID $PID"
    sleep 2
    
    # Check if process is really gone
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE"
        echo "Worker force stopped"
        exit 0
    fi
    
    # Last resort: try to find and kill by process name
    echo "Attempting to find and kill by process name..."
    ORPHANED=$(pgrep -f "minecraft_bridge_worker" | grep -v "^$$")
    if [ -n "$ORPHANED" ]; then
        echo "Found process(es) by name: $ORPHANED"
        kill -KILL $ORPHANED 2>/dev/null
        sleep 1
        STILL_RUNNING=$(pgrep -f "minecraft_bridge_worker" | grep -v "^$$")
        if [ -z "$STILL_RUNNING" ]; then
            rm -f "$PIDFILE"
            echo "Worker killed by process name"
            exit 0
        fi
    fi
    
    echo "Worker could not be stopped"
    exit 1
}

stop_snapshot() {
    if ! is_snapshot_running; then
        echo "Snapshot worker is not running"
        if [ -f "$SNAPSHOT_PIDFILE" ]; then
            rm -f "$SNAPSHOT_PIDFILE"
        fi
        # Also check for orphaned processes
        ORPHANED=$(pgrep -f "minecraft_snapshot_worker" | grep -v "^$$")
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned snapshot worker process(es): $ORPHANED"
            kill -TERM $ORPHANED 2>/dev/null
            sleep 2
            # Force kill if still running
            STILL_RUNNING=$(pgrep -f "minecraft_snapshot_worker" | grep -v "^$$")
            if [ -n "$STILL_RUNNING" ]; then
                kill -KILL $STILL_RUNNING 2>/dev/null
                echo "Force killed orphaned snapshot worker process(es)"
            fi
        fi
        exit 0
    fi

    PID=$(get_snapshot_pid)
    echo "Stopping snapshot worker (PID: $PID)..."
    kill -TERM "$PID" 2>/dev/null || {
        echo "Warning: Could not send TERM signal to PID $PID"
        # Process might already be gone, check if PID file is stale
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$SNAPSHOT_PIDFILE"
            echo "Snapshot worker already stopped (stale PID file)"
            exit 0
        fi
    }

    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$SNAPSHOT_PIDFILE"
            echo "Snapshot worker stopped gracefully"
            exit 0
        fi
        sleep 1
    done

    # Force kill if TERM didn't work
    echo "Snapshot worker did not stop in time, forcing kill..."
    kill -KILL "$PID" 2>/dev/null || echo "Warning: Could not send KILL signal to PID $PID"
    sleep 2
    
    # Check if process is really gone
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$SNAPSHOT_PIDFILE"
        echo "Snapshot worker force stopped"
        exit 0
    fi
    
    # Last resort: try to find and kill by process name
    echo "Attempting to find and kill by process name..."
    ORPHANED=$(pgrep -f "minecraft_snapshot_worker" | grep -v "^$$")
    if [ -n "$ORPHANED" ]; then
        echo "Found process(es) by name: $ORPHANED"
        kill -KILL $ORPHANED 2>/dev/null
        sleep 1
        STILL_RUNNING=$(pgrep -f "minecraft_snapshot_worker" | grep -v "^$$")
        if [ -z "$STILL_RUNNING" ]; then
            rm -f "$SNAPSHOT_PIDFILE"
            echo "Snapshot worker killed by process name"
            exit 0
        fi
    fi
    
    echo "Snapshot worker could not be stopped"
    exit 1
}

status() {
    if is_running; then
        echo "Worker is running (PID: $(get_pid))"
        exit 0
    fi
    echo "Worker is not running"
    exit 1
}

status_snapshot() {
    if is_snapshot_running; then
        echo "Snapshot worker is running (PID: $(get_snapshot_pid))"
        exit 0
    fi
    echo "Snapshot worker is not running"
    exit 1
}

stop_all() {
    echo "Stopping all Minecraft workers..."
    stop
    stop_snapshot
    echo "All workers stopped"
    
    # Final check: kill any remaining orphaned processes
    ORPHANED_BRIDGE=$(pgrep -f "minecraft_bridge_worker" | grep -v "^$$")
    ORPHANED_SNAPSHOT=$(pgrep -f "minecraft_snapshot_worker" | grep -v "^$$")
    
    if [ -n "$ORPHANED_BRIDGE" ] || [ -n "$ORPHANED_SNAPSHOT" ]; then
        echo "Found remaining orphaned processes, force killing..."
        [ -n "$ORPHANED_BRIDGE" ] && kill -KILL $ORPHANED_BRIDGE 2>/dev/null
        [ -n "$ORPHANED_SNAPSHOT" ] && kill -KILL $ORPHANED_SNAPSHOT 2>/dev/null
        sleep 1
        rm -f "$PIDFILE" "$SNAPSHOT_PIDFILE"
        echo "All orphaned processes killed"
    fi
}

restart() {
    stop || true
    start
}

case "$1" in
    start) start ;;
    stop) stop ;;
    stop-all) stop_all ;;
    restart) restart ;;
    status) status ;;
    snapshot-start) start_snapshot ;;
    snapshot-stop) stop_snapshot ;;
    snapshot-status) status_snapshot ;;
    *) echo "Usage: $0 {start|stop|stop-all|restart|status|snapshot-start|snapshot-stop|snapshot-status}" ; exit 1 ;;
esac
