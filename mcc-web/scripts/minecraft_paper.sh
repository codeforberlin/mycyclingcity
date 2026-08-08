#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft_paper.sh
# @note    Start/stop/status for Paper (mc-srv) Java process.
# Usage: ./minecraft_paper.sh {start|stop|status}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$PROJECT_DIR" == *"/data/appl/mcc"* ]]; then
    TMP_DIR="/data/var/mcc/tmp"
    LOG_DIR="/data/var/mcc/logs"
    VENV_DIR="/data/appl/mcc/venv"
    DEFAULT_PAPER_DIR="/data/games/mcc/mc-srv"
else
    TMP_DIR="$PROJECT_DIR/data/tmp"
    LOG_DIR="$PROJECT_DIR/data/logs"
    VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
    DEFAULT_PAPER_DIR="${MCC_MINECRAFT_PAPER_DIR:-}"
fi

PAPER_DIR="${MCC_MINECRAFT_PAPER_DIR:-$DEFAULT_PAPER_DIR}"
PAPER_PIDFILE="${MCC_MINECRAFT_PAPER_PIDFILE:-$TMP_DIR/minecraft-paper.pid}"
PAPER_LOG="${MCC_MINECRAFT_PAPER_LOG:-$LOG_DIR/minecraft-paper.log}"
PAPER_JAR_MATCH="${MCC_MINECRAFT_PAPER_JAR_MATCH:-paper-}"
PAPER_JAR_NAME="${MCC_MINECRAFT_PAPER_JAR_NAME:-}"
STOP_WAIT_SECONDS="${MCC_MINECRAFT_PAPER_STOP_WAIT:-90}"

# Aikar flags from mc-srv/start.sh (override via MCC_MINECRAFT_PAPER_JAVA_OPTS).
# terminal.jline/ansi=false: without a TTY Paper otherwise floods stdout with "> " prompts
# and ANSI codes (multi‑MB junk in minecraft-paper.log).
DEFAULT_JAVA_OPTS="-Dterminal.jline=false -Dterminal.ansi=false -Xms4G -Xmx4G -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8 -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true"
PAPER_JAVA_OPTS="${MCC_MINECRAFT_PAPER_JAVA_OPTS:-$DEFAULT_JAVA_OPTS}"

RCON_HOST="${MCC_MINECRAFT_RCON_HOST:-127.0.0.1}"
RCON_PORT="${MCC_MINECRAFT_RCON_PORT:-25575}"
RCON_PASSWORD="${MCC_MINECRAFT_RCON_PASSWORD:-}"

mkdir -p "$TMP_DIR" "$LOG_DIR"

java_bin() {
    if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        echo "$JAVA_HOME/bin/java"
        return
    fi
    if [ -x /usr/bin/java ]; then
        echo /usr/bin/java
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
    pid_alive "$pid" && cmdline_matches_jar "$pid" "$PAPER_JAR_MATCH"
}

find_paper_jar() {
    local jar
    if [ -n "$PAPER_JAR_NAME" ] && [ -f "$PAPER_DIR/$PAPER_JAR_NAME" ]; then
        echo "$PAPER_DIR/$PAPER_JAR_NAME"
        return 0
    fi
    # Prefer explicitly used production jar if present
    if [ -f "$PAPER_DIR/paper-26.1.2-74.jar" ]; then
        echo "$PAPER_DIR/paper-26.1.2-74.jar"
        return 0
    fi
    jar=$(ls -1 "$PAPER_DIR"/paper-*.jar 2>/dev/null | sort -V | tail -1 || true)
    if [ -n "$jar" ] && [ -f "$jar" ]; then
        echo "$jar"
        return 0
    fi
    return 1
}

paper_running() {
    local pid
    pid=$(read_pid "$PAPER_PIDFILE")
    verify_pid "$pid"
}

find_orphan_pids() {
    local pid cmdline cwd work_dir_norm
    work_dir_norm=$(readlink -f "$PAPER_DIR" 2>/dev/null || echo "$PAPER_DIR")
    for pid in $(pgrep -f "$PAPER_JAR_MATCH" 2>/dev/null || true); do
        if ! pid_alive "$pid"; then
            continue
        fi
        if ! cmdline_matches_jar "$pid" "$PAPER_JAR_MATCH"; then
            continue
        fi
        if [ -r "/proc/$pid/cwd" ]; then
            cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
            if [ -n "$cwd" ] && [ "$cwd" != "$work_dir_norm" ]; then
                continue
            fi
        fi
        echo "$pid"
    done
}

rcon_stop() {
    local py
    if [ -z "$RCON_PASSWORD" ]; then
        echo "RCON password unset; skipping graceful stop"
        return 1
    fi
    py="$VENV_DIR/bin/python"
    if [ ! -x "$py" ]; then
        py=$(command -v python3 || true)
    fi
    if [ -z "$py" ]; then
        echo "python not found for RCON stop"
        return 1
    fi
    "$py" - <<PY
from mcrcon import MCRcon
try:
    with MCRcon("${RCON_HOST}", "${RCON_PASSWORD}", port=int("${RCON_PORT}")) as mcr:
        print(mcr.command("stop") or "stop sent")
except Exception as exc:
    print(f"rcon stop failed: {exc}")
    raise SystemExit(1)
PY
}

stop_graceful() {
    local pid="$1"
    local i

    if ! pid_alive "$pid"; then
        rm -f "$PAPER_PIDFILE"
        echo "Paper already stopped (stale PID file)"
        return 0
    fi

    if ! cmdline_matches_jar "$pid" "$PAPER_JAR_MATCH"; then
        echo "Warning: PID $pid does not look like Paper ($PAPER_JAR_MATCH); refusing to kill"
        return 1
    fi

    echo "Stopping Paper (PID: $pid) via RCON stop..."
    if rcon_stop; then
        :
    else
        echo "RCON stop failed; sending SIGTERM..."
        kill -TERM "$pid" 2>/dev/null || true
    fi

    for i in $(seq 1 "$STOP_WAIT_SECONDS"); do
        if ! pid_alive "$pid"; then
            rm -f "$PAPER_PIDFILE"
            echo "Paper stopped gracefully"
            return 0
        fi
        sleep 1
    done

    echo "Paper did not stop in time, sending SIGTERM..."
    kill -TERM "$pid" 2>/dev/null || true
    for i in $(seq 1 15); do
        if ! pid_alive "$pid"; then
            rm -f "$PAPER_PIDFILE"
            echo "Paper stopped after SIGTERM"
            return 0
        fi
        sleep 1
    done

    echo "Paper still running, forcing SIGKILL..."
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
    if ! pid_alive "$pid"; then
        rm -f "$PAPER_PIDFILE"
        echo "Paper force stopped"
        return 0
    fi
    echo "Paper could not be stopped"
    return 1
}

kill_orphans() {
    local pid found=0
    for pid in $(find_orphan_pids); do
        found=1
        echo "Found orphaned Paper PID: $pid"
        kill -TERM "$pid" 2>/dev/null || true
    done
    if [ "$found" -eq 1 ]; then
        sleep 2
        for pid in $(find_orphan_pids); do
            kill -KILL "$pid" 2>/dev/null && echo "Force killed orphaned Paper PID: $pid"
        done
    fi
}

start_paper() {
    local java_cmd jar
    java_cmd=$(java_bin) || {
        echo "java not found"
        return 1
    }
    if [ -z "$PAPER_DIR" ] || [ ! -d "$PAPER_DIR" ]; then
        echo "Paper directory missing: ${PAPER_DIR:-"(unset)"}"
        return 1
    fi
    if paper_running; then
        echo "Paper already running (PID: $(read_pid "$PAPER_PIDFILE"))"
        return 0
    fi
    # Refuse start if orphan Paper already holds the world
    if [ -n "$(find_orphan_pids)" ]; then
        echo "Paper appears already running without PID file; refusing start. Use stop first."
        find_orphan_pids | while read -r p; do echo "  orphan PID: $p"; done
        return 1
    fi
    jar=$(find_paper_jar) || {
        echo "paper-*.jar not found in $PAPER_DIR"
        return 1
    }

    cd "$PAPER_DIR" || return 1
    # Truncate previous console capture (avoids leftover jline spam from older starts)
    : > "$PAPER_LOG"
    # stdin from /dev/null: prevents interactive console prompt spam when redirected
    # shellcheck disable=SC2086
    nohup "$java_cmd" $PAPER_JAVA_OPTS -jar "$(basename "$jar")" --nogui \
        < /dev/null >> "$PAPER_LOG" 2>&1 &
    echo $! > "$PAPER_PIDFILE"
    sleep 2
    if paper_running; then
        echo "Paper started (PID: $(read_pid "$PAPER_PIDFILE"))"
        echo "Jar: $(basename "$jar")"
        echo "Log: $PAPER_LOG"
        return 0
    fi
    echo "Paper failed to start; see $PAPER_LOG"
    return 1
}

stop_paper() {
    local pid
    pid=$(read_pid "$PAPER_PIDFILE")
    if [ -z "$pid" ] || ! pid_alive "$pid"; then
        echo "Paper is not running (no valid PID file)"
        rm -f "$PAPER_PIDFILE"
        kill_orphans
        return 0
    fi
    stop_graceful "$pid"
    local rc=$?
    kill_orphans
    return $rc
}

status_paper() {
    local pid
    pid=$(read_pid "$PAPER_PIDFILE")
    if verify_pid "$pid"; then
        echo "Paper running (PID: $pid)"
        echo "Dir: $PAPER_DIR"
        echo "Log: $PAPER_LOG"
        return 0
    fi
    echo "Paper stopped"
    echo "Dir: $PAPER_DIR"
    echo "Log: $PAPER_LOG"
    return 1
}

case "${1:-}" in
    start) start_paper; exit $? ;;
    stop) stop_paper; exit $? ;;
    status) status_paper; exit $? ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
