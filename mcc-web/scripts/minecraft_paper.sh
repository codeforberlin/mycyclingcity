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
# Canonical start name only (symlink to the active build, e.g. paper-26.2-112.jar).
# Ignore any versioned MCC_MINECRAFT_PAPER_JAR_NAME override — must always be paper.jar.
if [ -n "${MCC_MINECRAFT_PAPER_JAR_NAME:-}" ] && [ "$MCC_MINECRAFT_PAPER_JAR_NAME" != "paper.jar" ]; then
    echo "Warning: ignoring MCC_MINECRAFT_PAPER_JAR_NAME=$MCC_MINECRAFT_PAPER_JAR_NAME (forcing paper.jar)" >&2
fi
PAPER_JAR_NAME="paper.jar"
PAPER_JAR_MATCH="${MCC_MINECRAFT_PAPER_JAR_MATCH:-paper.jar}"
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
    # Only the configured jar name — never fall back to paper-*.jar versioned files.
    if [ -z "$PAPER_JAR_NAME" ]; then
        echo "PAPER_JAR_NAME is empty" >&2
        return 1
    fi
    if [ -f "$PAPER_DIR/$PAPER_JAR_NAME" ]; then
        echo "$PAPER_DIR/$PAPER_JAR_NAME"
        return 0
    fi
    echo "$PAPER_JAR_NAME not found in $PAPER_DIR" >&2
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
    # Broad match: paper.jar and any paper-*.jar (catches stale versioned starts).
    for pid in $(pgrep -f 'java.*-jar paper' 2>/dev/null || true); do
        if ! pid_alive "$pid"; then
            continue
        fi
        if [ -r "/proc/$pid/cmdline" ]; then
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
            case "$cmdline" in
                *"-jar paper.jar"*|*" -jar paper-"*) ;;
                *) continue ;;
            esac
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
    local i cmdline

    if ! pid_alive "$pid"; then
        rm -f "$PAPER_PIDFILE"
        echo "Paper already stopped (stale PID file)"
        return 0
    fi

    if ! cmdline_matches_jar "$pid" "$PAPER_JAR_MATCH"; then
        # Allow stopping legacy starts that used a versioned paper-*.jar name.
        cmdline=""
        if [ -r "/proc/$pid/cmdline" ]; then
            cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
        fi
        case "$cmdline" in
            *"-jar paper-"*|*"-jar paper.jar"*) ;;
            *)
                echo "Warning: PID $pid does not look like Paper ($PAPER_JAR_MATCH); refusing to kill"
                return 1
                ;;
        esac
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
        echo "Configured Paper jar not found in $PAPER_DIR (expected: $PAPER_JAR_NAME)"
        return 1
    }
    # Resolve symlink so logs show the real build; still start via paper.jar name.
    jar_resolved=$(readlink -f "$jar" 2>/dev/null || echo "$jar")

    cd "$PAPER_DIR" || return 1
    # Truncate previous console capture (avoids leftover jline spam from older starts)
    : > "$PAPER_LOG"
    # stdin from /dev/null: prevents interactive console prompt spam when redirected
    # Always pass -jar paper.jar (never a versioned filename).
    # shellcheck disable=SC2086
    nohup "$java_cmd" $PAPER_JAVA_OPTS -jar "$PAPER_JAR_NAME" --nogui \
        < /dev/null >> "$PAPER_LOG" 2>&1 &
    echo $! > "$PAPER_PIDFILE"
    sleep 2
    if paper_running; then
        echo "Paper started (PID: $(read_pid "$PAPER_PIDFILE"))"
        echo "Jar: $PAPER_JAR_NAME"
        echo "Build: $(basename "$jar_resolved")"
        case "$(basename "$jar_resolved")" in
            paper-*.jar)
                _v="$(basename "$jar_resolved")"
                _v="${_v#paper-}"
                echo "Version: ${_v%.jar}"
                ;;
        esac
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

paper_jar_version_line() {
    # Resolve PAPER_JAR_NAME (usually paper.jar symlink) to the real build filename.
    local jar_path target base version
    jar_path="$PAPER_DIR/$PAPER_JAR_NAME"
    if [ ! -e "$jar_path" ]; then
        echo "Jar: $PAPER_JAR_NAME (missing)"
        return
    fi
    echo "Jar: $PAPER_JAR_NAME"
    if [ -L "$jar_path" ]; then
        target=$(readlink -f "$jar_path" 2>/dev/null || readlink "$jar_path" || true)
        base=$(basename "${target:-}")
        if [ -n "$base" ]; then
            echo "Build: $base"
            case "$base" in
                paper-*.jar)
                    version="${base#paper-}"
                    version="${version%.jar}"
                    echo "Version: $version"
                    ;;
            esac
        fi
    elif [ -f "$jar_path" ]; then
        echo "Build: $PAPER_JAR_NAME"
    fi
}

status_paper() {
    local pid
    pid=$(read_pid "$PAPER_PIDFILE")
    if verify_pid "$pid"; then
        echo "Paper running (PID: $pid)"
        paper_jar_version_line
        echo "Dir: $PAPER_DIR"
        echo "Log: $PAPER_LOG"
        return 0
    fi
    echo "Paper stopped"
    paper_jar_version_line
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
