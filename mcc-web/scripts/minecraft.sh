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
    TMP_DIR="$PROJECT_DIR/data/tmp"
    LOG_DIR="$PROJECT_DIR/data/logs"
fi

PYTHON_BIN="$VENV_DIR/bin/python"
PIDFILE="$TMP_DIR/minecraft.pid"
SNAPSHOT_PIDFILE="$TMP_DIR/minecraft-snapshot.pid"
SESSION_PIDFILE="$TMP_DIR/minecraft-session.pid"
ARENA_PIDFILE="$TMP_DIR/minecraft-arena-motion.pid"
LOG_FILE="$LOG_DIR/minecraft-worker.log"
SNAPSHOT_LOG_FILE="$LOG_DIR/minecraft-snapshot.log"
SESSION_LOG_FILE="$LOG_DIR/minecraft-session.log"
ARENA_LOG_FILE="$LOG_DIR/minecraft-arena-motion.log"

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

get_session_pid() {
    if [ -f "$SESSION_PIDFILE" ]; then
        cat "$SESSION_PIDFILE"
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

is_session_running() {
    PID=$(get_session_pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

get_arena_pid() {
    if [ -f "$ARENA_PIDFILE" ]; then
        cat "$ARENA_PIDFILE"
    fi
}

is_arena_running() {
    PID=$(get_arena_pid)
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
        start_session || true
        exit 0
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_bridge_worker >> "$LOG_FILE" 2>&1 &
    echo $! > "$PIDFILE"
    echo "Worker started (PID: $(get_pid))"
    start_session || true
}

start_snapshot() {
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "Python not found at $PYTHON_BIN"
        exit 1
    fi

    if is_snapshot_running; then
        echo "Snapshot worker already running (PID: $(get_snapshot_pid))"
        exit 0
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_snapshot_worker >> "$SNAPSHOT_LOG_FILE" 2>&1 &
    echo $! > "$SNAPSHOT_PIDFILE"
    echo "Snapshot worker started (PID: $(get_snapshot_pid))"
}

start_session() {
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "Python not found at $PYTHON_BIN"
        exit 1
    fi

    if is_session_running; then
        echo "Session worker already running (PID: $(get_session_pid))"
        exit 0
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_session_worker >> "$SESSION_LOG_FILE" 2>&1 &
    echo $! > "$SESSION_PIDFILE"
    echo "Session worker started (PID: $(get_session_pid))"
}

start_arena() {
    if [ ! -f "$PYTHON_BIN" ]; then
        echo "Python not found at $PYTHON_BIN"
        exit 1
    fi

    if is_arena_running; then
        echo "Arena motion worker already running (PID: $(get_arena_pid))"
        exit 0
    fi

    cd "$PROJECT_DIR" || exit 1
    export DJANGO_SETTINGS_MODULE=config.settings
    export PYTHONPATH="$PROJECT_DIR"

    nohup "$PYTHON_BIN" "$PROJECT_DIR/manage.py" minecraft_arena_motion_worker >> "$ARENA_LOG_FILE" 2>&1 &
    echo $! > "$ARENA_PIDFILE"
    echo "Arena motion worker started (PID: $(get_arena_pid))"
}

stop() {
    if ! is_running; then
        echo "Worker is not running"
        if [ -f "$PIDFILE" ]; then
            rm -f "$PIDFILE"
        fi
        # Also check for orphaned processes (more robust method)
        ORPHANED=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned worker process(es): $ORPHANED"
            for pid in $ORPHANED; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -TERM "$pid" 2>/dev/null || true
                fi
            done
            sleep 2
            # Force kill if still running
            STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
            if [ -n "$STILL_RUNNING" ]; then
                for pid in $STILL_RUNNING; do
                    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                        kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned worker PID: $pid"
                    fi
                done
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
    
    # Last resort: try to find and kill by process name (more robust method)
    echo "Attempting to find and kill by process name..."
    ORPHANED=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
    if [ -n "$ORPHANED" ]; then
        echo "Found process(es) by name: $ORPHANED"
        for pid in $ORPHANED; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null && echo "Killed bridge worker PID: $pid"
            fi
        done
        sleep 2
        STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -z "$STILL_RUNNING" ]; then
            rm -f "$PIDFILE"
            echo "Worker killed by process name"
            exit 0
        else
            echo "Warning: Some processes still running after kill: $STILL_RUNNING"
            # Try pkill as last resort
            if command -v pkill >/dev/null 2>&1; then
                pkill -9 -f "minecraft_bridge_worker" 2>/dev/null
                sleep 1
                FINAL_CHECK=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
                if [ -z "$FINAL_CHECK" ]; then
                    rm -f "$PIDFILE"
                    echo "Worker killed via pkill"
                    exit 0
                fi
            fi
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
        # Also check for orphaned processes (more robust method)
        ORPHANED=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned snapshot worker process(es): $ORPHANED"
            for pid in $ORPHANED; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -TERM "$pid" 2>/dev/null || true
                fi
            done
            sleep 2
            # Force kill if still running
            STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
            if [ -n "$STILL_RUNNING" ]; then
                for pid in $STILL_RUNNING; do
                    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                        kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned snapshot worker PID: $pid"
                    fi
                done
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
    
    # Last resort: try to find and kill by process name (more robust method)
    echo "Attempting to find and kill by process name..."
    ORPHANED=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
    if [ -n "$ORPHANED" ]; then
        echo "Found process(es) by name: $ORPHANED"
        for pid in $ORPHANED; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null && echo "Killed snapshot worker PID: $pid"
            fi
        done
        sleep 2
        STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -z "$STILL_RUNNING" ]; then
            rm -f "$SNAPSHOT_PIDFILE"
            echo "Snapshot worker killed by process name"
            exit 0
        else
            echo "Warning: Some processes still running after kill: $STILL_RUNNING"
            # Try pkill as last resort
            if command -v pkill >/dev/null 2>&1; then
                pkill -9 -f "minecraft_snapshot_worker" 2>/dev/null
                sleep 1
                FINAL_CHECK=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
                if [ -z "$FINAL_CHECK" ]; then
                    rm -f "$SNAPSHOT_PIDFILE"
                    echo "Snapshot worker killed via pkill"
                    exit 0
                fi
            fi
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

stop_session() {
    if ! is_session_running; then
        echo "Session worker is not running"
        if [ -f "$SESSION_PIDFILE" ]; then
            rm -f "$SESSION_PIDFILE"
        fi
        ORPHANED=$(ps aux | grep -E "[m]inecraft_session_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned session worker process(es): $ORPHANED"
            for pid in $ORPHANED; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -TERM "$pid" 2>/dev/null || true
                fi
            done
            sleep 2
            STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_session_worker" | awk '{print $2}' | tr '\n' ' ')
            if [ -n "$STILL_RUNNING" ]; then
                for pid in $STILL_RUNNING; do
                    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                        kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned session worker PID: $pid"
                    fi
                done
            fi
        fi
        exit 0
    fi

    PID=$(get_session_pid)
    echo "Stopping session worker (PID: $PID)..."
    kill -TERM "$PID" 2>/dev/null || {
        echo "Warning: Could not send TERM signal to PID $PID"
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$SESSION_PIDFILE"
            echo "Session worker already stopped (stale PID file)"
            exit 0
        fi
    }

    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$SESSION_PIDFILE"
            echo "Session worker stopped gracefully"
            exit 0
        fi
        sleep 1
    done

    echo "Session worker did not stop in time, forcing kill..."
    kill -KILL "$PID" 2>/dev/null || echo "Warning: Could not send KILL signal to PID $PID"
    sleep 1
    rm -f "$SESSION_PIDFILE"
    echo "Session worker force stopped"
}

status_session() {
    if is_session_running; then
        echo "Session worker is running (PID: $(get_session_pid))"
        exit 0
    fi
    echo "Session worker is not running"
    exit 1
}

stop_arena() {
    if ! is_arena_running; then
        echo "Arena motion worker is not running"
        if [ -f "$ARENA_PIDFILE" ]; then
            rm -f "$ARENA_PIDFILE"
        fi
        ORPHANED=$(ps aux | grep -E "[m]inecraft_arena_motion_worker" | awk '{print $2}' | tr '\n' ' ')
        if [ -n "$ORPHANED" ]; then
            echo "Found orphaned arena motion worker process(es): $ORPHANED"
            for pid in $ORPHANED; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -TERM "$pid" 2>/dev/null || true
                fi
            done
            sleep 2
            STILL_RUNNING=$(ps aux | grep -E "[m]inecraft_arena_motion_worker" | awk '{print $2}' | tr '\n' ' ')
            if [ -n "$STILL_RUNNING" ]; then
                for pid in $STILL_RUNNING; do
                    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                        kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned arena motion worker PID: $pid"
                    fi
                done
            fi
        fi
        exit 0
    fi

    PID=$(get_arena_pid)
    echo "Stopping arena motion worker (PID: $PID)..."
    kill -TERM "$PID" 2>/dev/null || {
        echo "Warning: Could not send TERM signal to PID $PID"
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$ARENA_PIDFILE"
            echo "Arena motion worker already stopped (stale PID file)"
            exit 0
        fi
    }

    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$ARENA_PIDFILE"
            echo "Arena motion worker stopped gracefully"
            exit 0
        fi
        sleep 1
    done

    echo "Arena motion worker did not stop in time, forcing kill..."
    kill -KILL "$PID" 2>/dev/null || echo "Warning: Could not send KILL signal to PID $PID"
    sleep 1
    rm -f "$ARENA_PIDFILE"
    echo "Arena motion worker force stopped"
}

status_arena() {
    if is_arena_running; then
        echo "Arena motion worker is running (PID: $(get_arena_pid))"
        exit 0
    fi
    echo "Arena motion worker is not running"
    exit 1
}

# Kill all worker processes by name (robust method)
kill_all_worker_processes_by_name() {
    # Method 1: Try pkill if available (most reliable)
    if command -v pkill >/dev/null 2>&1; then
        pkill -9 -f "minecraft_bridge_worker" 2>/dev/null && echo "Killed bridge workers via pkill"
        pkill -9 -f "minecraft_snapshot_worker" 2>/dev/null && echo "Killed snapshot workers via pkill"
        pkill -9 -f "minecraft_session_worker" 2>/dev/null && echo "Killed session workers via pkill"
        pkill -9 -f "minecraft_arena_motion_worker" 2>/dev/null && echo "Killed arena motion workers via pkill"
        sleep 1
    fi
    
    # Method 2: Find and kill by process name (fallback)
    ORPHANED_BRIDGE=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
    ORPHANED_SNAPSHOT=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
    ORPHANED_SESSION=$(ps aux | grep -E "[m]inecraft_session_worker" | awk '{print $2}' | tr '\n' ' ')
    ORPHANED_ARENA=$(ps aux | grep -E "[m]inecraft_arena_motion_worker" | awk '{print $2}' | tr '\n' ' ')
    
    if [ -n "$ORPHANED_BRIDGE" ] || [ -n "$ORPHANED_SNAPSHOT" ] || [ -n "$ORPHANED_SESSION" ] || [ -n "$ORPHANED_ARENA" ]; then
        echo "Found remaining orphaned processes, force killing..."
        
        # Kill bridge workers
        if [ -n "$ORPHANED_BRIDGE" ]; then
            for pid in $ORPHANED_BRIDGE; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -KILL "$pid" 2>/dev/null && echo "Killed bridge worker PID: $pid"
                fi
            done
        fi
        
        # Kill snapshot workers
        if [ -n "$ORPHANED_SNAPSHOT" ]; then
            for pid in $ORPHANED_SNAPSHOT; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -KILL "$pid" 2>/dev/null && echo "Killed snapshot worker PID: $pid"
                fi
            done
        fi

        # Kill session workers
        if [ -n "$ORPHANED_SESSION" ]; then
            for pid in $ORPHANED_SESSION; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -KILL "$pid" 2>/dev/null && echo "Killed session worker PID: $pid"
                fi
            done
        fi

        # Kill arena motion workers
        if [ -n "$ORPHANED_ARENA" ]; then
            for pid in $ORPHANED_ARENA; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    kill -KILL "$pid" 2>/dev/null && echo "Killed arena motion worker PID: $pid"
                fi
            done
        fi
        
        sleep 2
        
        # Verify they are really gone
        REMAINING_BRIDGE=$(ps aux | grep -E "[m]inecraft_bridge_worker" | awk '{print $2}' | tr '\n' ' ')
        REMAINING_SNAPSHOT=$(ps aux | grep -E "[m]inecraft_snapshot_worker" | awk '{print $2}' | tr '\n' ' ')
        REMAINING_SESSION=$(ps aux | grep -E "[m]inecraft_session_worker" | awk '{print $2}' | tr '\n' ' ')
        REMAINING_ARENA=$(ps aux | grep -E "[m]inecraft_arena_motion_worker" | awk '{print $2}' | tr '\n' ' ')
        
        if [ -z "$REMAINING_BRIDGE" ] && [ -z "$REMAINING_SNAPSHOT" ] && [ -z "$REMAINING_SESSION" ] && [ -z "$REMAINING_ARENA" ]; then
            rm -f "$PIDFILE" "$SNAPSHOT_PIDFILE" "$SESSION_PIDFILE" "$ARENA_PIDFILE"
            echo "All orphaned processes killed"
        else
            echo "Warning: Some processes may still be running"
            [ -n "$REMAINING_BRIDGE" ] && echo "  Bridge workers: $REMAINING_BRIDGE"
            [ -n "$REMAINING_SNAPSHOT" ] && echo "  Snapshot workers: $REMAINING_SNAPSHOT"
            [ -n "$REMAINING_SESSION" ] && echo "  Session workers: $REMAINING_SESSION"
            [ -n "$REMAINING_ARENA" ] && echo "  Arena motion workers: $REMAINING_ARENA"
        fi
    else
        rm -f "$PIDFILE" "$SNAPSHOT_PIDFILE" "$SESSION_PIDFILE" "$ARENA_PIDFILE"
        echo "No orphaned processes found"
    fi
}

stop_all() {
    echo "Stopping all Minecraft workers..."
    stop
    stop_snapshot
    stop_session
    stop_arena
    echo "All workers stopped"
    
    # Final check: kill any remaining orphaned processes by process name
    # This ensures all processes are killed, even if PID files are stale
    echo "Checking for remaining worker processes..."
    kill_all_worker_processes_by_name
}

start_all() {
    start || true
    start_snapshot || true
    start_session || true
    start_arena || true
}

restart() {
    stop_all || true
    start_all
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
    session-start) start_session ;;
    session-stop) stop_session ;;
    session-status) status_session ;;
    arena-start) start_arena ;;
    arena-stop) stop_arena ;;
    arena-status) status_arena ;;
    start-all) start_all ;;
    *) echo "Usage: $0 {start|stop|stop-all|restart|status|start-all|snapshot-start|snapshot-stop|snapshot-status|session-start|session-stop|session-status|arena-start|arena-stop|arena-status}" ; exit 1 ;;
esac
