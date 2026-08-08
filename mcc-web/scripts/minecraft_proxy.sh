#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft_proxy.sh
# @note    Start/stop/status for Velocity proxy and Limbo waiting room (Java).
# Usage: ./minecraft_proxy.sh {velocity-start|velocity-stop|velocity-status|
#                              limbo-start|limbo-stop|limbo-status|status|start-all|stop-all}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    TMP_DIR="/data/var/mcc/tmp"
    LOG_DIR="/data/var/mcc/logs"
    DEFAULT_VELOCITY_DIR="/data/games/mcc/proxy"
    DEFAULT_LIMBO_DIR="/data/games/mcc/limbo"
else
    TMP_DIR="$PROJECT_DIR/data/tmp"
    LOG_DIR="$PROJECT_DIR/data/logs"
    DEFAULT_VELOCITY_DIR="${MCC_MINECRAFT_VELOCITY_DIR:-}"
    DEFAULT_LIMBO_DIR="${MCC_MINECRAFT_LIMBO_DIR:-}"
fi

VELOCITY_DIR="${MCC_MINECRAFT_VELOCITY_DIR:-$DEFAULT_VELOCITY_DIR}"
LIMBO_DIR="${MCC_MINECRAFT_LIMBO_DIR:-$DEFAULT_LIMBO_DIR}"

VELOCITY_PIDFILE="${MCC_MINECRAFT_VELOCITY_PIDFILE:-$TMP_DIR/minecraft-velocity.pid}"
LIMBO_PIDFILE="${MCC_MINECRAFT_LIMBO_PIDFILE:-$TMP_DIR/minecraft-limbo.pid}"
VELOCITY_LOG="${MCC_MINECRAFT_VELOCITY_LOG:-$LOG_DIR/minecraft-velocity.log}"
LIMBO_LOG="${MCC_MINECRAFT_LIMBO_LOG:-$LOG_DIR/minecraft-limbo.log}"

VELOCITY_JAR_MATCH="${MCC_MINECRAFT_VELOCITY_JAR_MATCH:-velocity.jar}"
LIMBO_JAR_MATCH="${MCC_MINECRAFT_LIMBO_JAR_MATCH:-limbo.jar}"

STOP_WAIT_SECONDS="${MCC_MINECRAFT_PROXY_STOP_WAIT:-20}"

mkdir -p "$TMP_DIR" "$LOG_DIR"

java_bin() {
    if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        echo "$JAVA_HOME/bin/java"
        return
    fi
    command -v java
}

read_pid() {
    local pidfile="$1"
    if [ -f "$pidfile" ]; then
        tr -d ' \n\r\t' < "$pidfile"
    fi
}

pid_alive() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cmdline_matches_jar() {
    local pid="$1"
    local jar_match="$2"
    local cmdline
    if [ ! -r "/proc/$pid/cmdline" ]; then
        return 1
    fi
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
    case "$cmdline" in
        *"$jar_match"*) return 0 ;;
        *) return 1 ;;
    esac
}

verify_pid() {
    local pid="$1"
    local jar_match="$2"
    pid_alive "$pid" && cmdline_matches_jar "$pid" "$jar_match"
}

find_orphan_pids() {
    local jar_match="$1"
    local work_dir="$2"
    local pid cmdline cwd
    for pid in $(pgrep -f "$jar_match" 2>/dev/null || true); do
        if ! pid_alive "$pid"; then
            continue
        fi
        if ! cmdline_matches_jar "$pid" "$jar_match"; then
            continue
        fi
        if [ -n "$work_dir" ] && [ -r "/proc/$pid/cwd" ]; then
            cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
            work_dir_norm=$(readlink -f "$work_dir" 2>/dev/null || echo "$work_dir")
            if [ -n "$cwd" ] && [ "$cwd" != "$work_dir_norm" ]; then
                continue
            fi
        fi
        echo "$pid"
    done
}

stop_pid_graceful() {
    local pid="$1"
    local pidfile="$2"
    local label="$3"
    local jar_match="$4"
    local i

    if ! pid_alive "$pid"; then
        rm -f "$pidfile"
        echo "$label already stopped (stale PID file)"
        return 0
    fi

    if ! cmdline_matches_jar "$pid" "$jar_match"; then
        echo "Warning: PID $pid does not look like $label ($jar_match); refusing to kill"
        return 1
    fi

    echo "Stopping $label (PID: $pid)..."
    kill -TERM "$pid" 2>/dev/null || true

    for i in $(seq 1 "$STOP_WAIT_SECONDS"); do
        if ! pid_alive "$pid"; then
            rm -f "$pidfile"
            echo "$label stopped gracefully"
            return 0
        fi
        sleep 1
    done

    echo "$label did not stop in time, forcing kill..."
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
    if ! pid_alive "$pid"; then
        rm -f "$pidfile"
        echo "$label force stopped"
        return 0
    fi
    echo "$label could not be stopped"
    return 1
}

kill_orphans() {
    local jar_match="$1"
    local work_dir="$2"
    local label="$3"
    local pid
    local found=0
    for pid in $(find_orphan_pids "$jar_match" "$work_dir"); do
        found=1
        echo "Found orphaned $label PID: $pid"
        kill -TERM "$pid" 2>/dev/null || true
    done
    if [ "$found" -eq 1 ]; then
        sleep 2
        for pid in $(find_orphan_pids "$jar_match" "$work_dir"); do
            kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned $label PID: $pid"
        done
    fi
}

# --- Velocity -----------------------------------------------------------------

velocity_running() {
    local pid
    pid=$(read_pid "$VELOCITY_PIDFILE")
    verify_pid "$pid" "$VELOCITY_JAR_MATCH"
}

start_velocity() {
    local java_cmd jar
    java_cmd=$(java_bin) || {
        echo "java not found"
        return 1
    }
    if [ -z "$VELOCITY_DIR" ] || [ ! -d "$VELOCITY_DIR" ]; then
        echo "Velocity directory missing: ${VELOCITY_DIR:-"(unset)"}"
        return 1
    fi
    if velocity_running; then
        echo "Velocity already running (PID: $(read_pid "$VELOCITY_PIDFILE"))"
        return 0
    fi
    jar="$VELOCITY_DIR/velocity.jar"
    if [ ! -f "$jar" ]; then
        jar=$(ls "$VELOCITY_DIR"/velocity*.jar 2>/dev/null | head -1)
    fi
    if [ -z "$jar" ] || [ ! -f "$jar" ]; then
        echo "velocity.jar not found in $VELOCITY_DIR"
        return 1
    fi

    cd "$VELOCITY_DIR" || return 1
    # Without a TTY, Velocity/jline floods the log with "> " prompts (hundreds of MB).
    : > "$VELOCITY_LOG"
    nohup "$java_cmd" \
        -Dterminal.jline=false -Dterminal.ansi=false \
        -Xms1G -Xmx1G \
        -XX:+UseG1GC -XX:G1HeapRegionSize=4M \
        -XX:+UnlockExperimentalVMOptions \
        -XX:+ParallelRefProcEnabled -XX:+AlwaysPreTouch \
        -XX:MaxInlineLevel=15 \
        -jar "$(basename "$jar")" \
        < /dev/null >> "$VELOCITY_LOG" 2>&1 &
    echo $! > "$VELOCITY_PIDFILE"
    sleep 1
    if velocity_running; then
        echo "Velocity started (PID: $(read_pid "$VELOCITY_PIDFILE"))"
        return 0
    fi
    echo "Velocity failed to start; see $VELOCITY_LOG"
    return 1
}

stop_velocity() {
    local pid
    pid=$(read_pid "$VELOCITY_PIDFILE")
    if [ -z "$pid" ] || ! pid_alive "$pid"; then
        echo "Velocity is not running"
        rm -f "$VELOCITY_PIDFILE"
        kill_orphans "$VELOCITY_JAR_MATCH" "$VELOCITY_DIR" "Velocity"
        return 0
    fi
    stop_pid_graceful "$pid" "$VELOCITY_PIDFILE" "Velocity" "$VELOCITY_JAR_MATCH"
    local rc=$?
    kill_orphans "$VELOCITY_JAR_MATCH" "$VELOCITY_DIR" "Velocity"
    return $rc
}

status_velocity() {
    local pid
    pid=$(read_pid "$VELOCITY_PIDFILE")
    if verify_pid "$pid" "$VELOCITY_JAR_MATCH"; then
        echo "Velocity running (PID: $pid)"
        echo "Dir: $VELOCITY_DIR"
        echo "Log: $VELOCITY_LOG"
        return 0
    fi
    echo "Velocity stopped"
    echo "Dir: $VELOCITY_DIR"
    echo "Log: $VELOCITY_LOG"
    return 1
}

# --- Limbo --------------------------------------------------------------------

limbo_running() {
    local pid
    pid=$(read_pid "$LIMBO_PIDFILE")
    verify_pid "$pid" "$LIMBO_JAR_MATCH"
}

start_limbo() {
    local java_cmd jar
    java_cmd=$(java_bin) || {
        echo "java not found"
        return 1
    }
    if [ -z "$LIMBO_DIR" ] || [ ! -d "$LIMBO_DIR" ]; then
        echo "Limbo directory missing: ${LIMBO_DIR:-"(unset)"}"
        return 1
    fi
    if limbo_running; then
        echo "Limbo already running (PID: $(read_pid "$LIMBO_PIDFILE"))"
        return 0
    fi
    jar="$LIMBO_DIR/limbo.jar"
    if [ ! -f "$jar" ]; then
        jar=$(ls "$LIMBO_DIR"/Limbo*.jar 2>/dev/null | head -1)
    fi
    if [ -z "$jar" ] || [ ! -f "$jar" ]; then
        echo "limbo.jar not found in $LIMBO_DIR"
        return 1
    fi

    cd "$LIMBO_DIR" || return 1
    # Same jline prompt spam as Velocity/Paper when stdout is redirected.
    : > "$LIMBO_LOG"
    nohup "$java_cmd" \
        -Dterminal.jline=false -Dterminal.ansi=false \
        -jar "$(basename "$jar")" --nogui \
        < /dev/null >> "$LIMBO_LOG" 2>&1 &
    echo $! > "$LIMBO_PIDFILE"
    sleep 1
    if limbo_running; then
        echo "Limbo started (PID: $(read_pid "$LIMBO_PIDFILE"))"
        return 0
    fi
    echo "Limbo failed to start; see $LIMBO_LOG"
    return 1
}

stop_limbo() {
    local pid
    pid=$(read_pid "$LIMBO_PIDFILE")
    if [ -z "$pid" ] || ! pid_alive "$pid"; then
        echo "Limbo is not running"
        rm -f "$LIMBO_PIDFILE"
        kill_orphans "$LIMBO_JAR_MATCH" "$LIMBO_DIR" "Limbo"
        return 0
    fi
    stop_pid_graceful "$pid" "$LIMBO_PIDFILE" "Limbo" "$LIMBO_JAR_MATCH"
    local rc=$?
    kill_orphans "$LIMBO_JAR_MATCH" "$LIMBO_DIR" "Limbo"
    return $rc
}

status_limbo() {
    local pid
    pid=$(read_pid "$LIMBO_PIDFILE")
    if verify_pid "$pid" "$LIMBO_JAR_MATCH"; then
        echo "Limbo running (PID: $pid)"
        echo "Dir: $LIMBO_DIR"
        echo "Log: $LIMBO_LOG"
        return 0
    fi
    echo "Limbo stopped"
    echo "Dir: $LIMBO_DIR"
    echo "Log: $LIMBO_LOG"
    return 1
}

status_all() {
    local vel_ok=1 lim_ok=1
    if velocity_running; then
        echo "Velocity: running (PID: $(read_pid "$VELOCITY_PIDFILE"))"
        vel_ok=0
    else
        echo "Velocity: stopped"
    fi
    if limbo_running; then
        echo "Limbo: running (PID: $(read_pid "$LIMBO_PIDFILE"))"
        lim_ok=0
    else
        echo "Limbo: stopped"
    fi
    if [ "$vel_ok" -eq 0 ] && [ "$lim_ok" -eq 0 ]; then
        return 0
    fi
    return 1
}

start_all() {
    start_velocity || true
    start_limbo || true
    return 0
}

stop_all() {
    stop_velocity || true
    stop_limbo || true
    return 0
}

case "${1:-}" in
    velocity-start) start_velocity; exit $? ;;
    velocity-stop) stop_velocity; exit $? ;;
    velocity-status) status_velocity; exit $? ;;
    limbo-start) start_limbo; exit $? ;;
    limbo-stop) stop_limbo; exit $? ;;
    limbo-status) status_limbo; exit $? ;;
    status) status_all; exit $? ;;
    start-all) start_all; exit $? ;;
    stop-all) stop_all; exit $? ;;
    *)
        echo "Usage: $0 {velocity-start|velocity-stop|velocity-status|limbo-start|limbo-stop|limbo-status|status|start-all|stop-all}"
        exit 1
        ;;
esac
