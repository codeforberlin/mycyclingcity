#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    mcc-web.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Management script for MCC-Web Gunicorn server
# Usage: ./mcc-web.sh {start|stop|restart|status|reload}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
GUNICORN_BIN="$VENV_DIR/bin/gunicorn"
GUNICORN_CONFIG="$PROJECT_DIR/config/gunicorn_config.py"
PIDFILE="$PROJECT_DIR/mcc-web.pid"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/mcc-web-script.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Log helper (append to file, keep console output unchanged)
log_line() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${timestamp} [${level}] ${message}" >> "$LOG_FILE"
}

# Check if running as correct user
check_user() {
    return 0
}

# Check if gunicorn is installed
check_gunicorn() {
    if [ ! -f "$GUNICORN_BIN" ]; then
        echo -e "${RED}Error: Gunicorn not found at $GUNICORN_BIN${NC}"
        echo -e "${YELLOW}Please ensure the virtual environment is set up correctly.${NC}"
        log_line "ERROR" "Gunicorn not found at $GUNICORN_BIN"
        exit 1
    fi
}

# Check if config file exists
check_config() {
    if [ ! -f "$GUNICORN_CONFIG" ]; then
        echo -e "${RED}Error: Gunicorn config not found at $GUNICORN_CONFIG${NC}"
        log_line "ERROR" "Gunicorn config not found at $GUNICORN_CONFIG"
        exit 1
    fi
}

# Get PID from PID file
get_pid() {
    if [ -f "$PIDFILE" ]; then
        cat "$PIDFILE"
    fi
}

# Check if process is running
is_running() {
    PID=$(get_pid)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Start the server
start() {
    check_gunicorn
    check_config
    
    if is_running; then
        PID=$(get_pid)
        echo -e "${YELLOW}Server is already running (PID: $PID)${NC}"
        log_line "WARN" "Start requested but already running (PID: $PID)"
        return 1
    fi
    
    echo -e "${BLUE}Starting MCC-Web server...${NC}"
    log_line "INFO" "Starting server: project_dir=$PROJECT_DIR venv_dir=$VENV_DIR gunicorn_bin=$GUNICORN_BIN"
    
    cd "$PROJECT_DIR" || exit 1
    
    # Get Gunicorn configuration from database (if available)
    # This requires Django to be set up, so we try to get it via management command
    GUNICORN_LOG_LEVEL="info"  # Default
    GUNICORN_WORKERS="0"  # Default (auto-calculated)
    GUNICORN_THREADS="2"  # Default
    GUNICORN_WORKER_CLASS="gthread"  # Default
    GUNICORN_BIND="127.0.0.1:8001"  # Default
    if [ -f "$PROJECT_DIR/manage.py" ]; then
        # Try to get config from database
        PYTHON_BIN="$VENV_DIR/bin/python"
        if [ -f "$PYTHON_BIN" ]; then
            # Set Django settings module
            export DJANGO_SETTINGS_MODULE=config.settings
            export PYTHONPATH="$PROJECT_DIR"
            
            CONFIG_OUTPUT=$("$PYTHON_BIN" "$PROJECT_DIR/manage.py" get_gunicorn_config 2>/dev/null)
            if [ $? -eq 0 ] && [ -n "$CONFIG_OUTPUT" ]; then
                # Extract values from output (format: GUNICORN_XXX=value)
                while IFS= read -r line; do
                    if echo "$line" | grep -q "GUNICORN_LOG_LEVEL="; then
                        EXTRACTED=$(echo "$line" | cut -d'=' -f2 | tr -d '[:space:]')
                        if [ -n "$EXTRACTED" ]; then
                            GUNICORN_LOG_LEVEL="$EXTRACTED"
                        fi
                    elif echo "$line" | grep -q "GUNICORN_WORKERS="; then
                        EXTRACTED=$(echo "$line" | cut -d'=' -f2 | tr -d '[:space:]')
                        if [ -n "$EXTRACTED" ]; then
                            GUNICORN_WORKERS="$EXTRACTED"
                        fi
                    elif echo "$line" | grep -q "GUNICORN_THREADS="; then
                        EXTRACTED=$(echo "$line" | cut -d'=' -f2 | tr -d '[:space:]')
                        if [ -n "$EXTRACTED" ]; then
                            GUNICORN_THREADS="$EXTRACTED"
                        fi
                    elif echo "$line" | grep -q "GUNICORN_WORKER_CLASS="; then
                        EXTRACTED=$(echo "$line" | cut -d'=' -f2 | tr -d '[:space:]')
                        if [ -n "$EXTRACTED" ]; then
                            GUNICORN_WORKER_CLASS="$EXTRACTED"
                        fi
                    elif echo "$line" | grep -q "GUNICORN_BIND="; then
                        EXTRACTED=$(echo "$line" | cut -d'=' -f2 | tr -d '[:space:]')
                        if [ -n "$EXTRACTED" ]; then
                            GUNICORN_BIND="$EXTRACTED"
                        fi
                    fi
                done <<< "$CONFIG_OUTPUT"
                
                echo -e "${BLUE}Using config from database:${NC}"
                echo -e "${BLUE}  Bind Address: $GUNICORN_BIND${NC}"
                echo -e "${BLUE}  Workers: $GUNICORN_WORKERS (0 = auto: CPU * 2 + 1)${NC}"
                echo -e "${BLUE}  Threads: $GUNICORN_THREADS${NC}"
                echo -e "${BLUE}  Worker Class: $GUNICORN_WORKER_CLASS${NC}"
                echo -e "${BLUE}  Log Level: $GUNICORN_LOG_LEVEL${NC}"
                log_line "INFO" "Using DB config: bind=$GUNICORN_BIND workers=$GUNICORN_WORKERS threads=$GUNICORN_THREADS class=$GUNICORN_WORKER_CLASS level=$GUNICORN_LOG_LEVEL"
            else
                log_line "WARN" "DB config not available; using defaults"
            fi
        else
            log_line "WARN" "Python not found at $PYTHON_BIN; skipping DB config"
        fi
    fi
    
    # Export configuration as environment variables
    export GUNICORN_LOG_LEVEL
    export GUNICORN_WORKERS
    export GUNICORN_THREADS
    export GUNICORN_WORKER_CLASS
    export GUNICORN_BIND
    
    # Start gunicorn in background
    nohup "$GUNICORN_BIN" \
        --config "$GUNICORN_CONFIG" \
        --pid "$PIDFILE" \
        --daemon \
        config.wsgi:application > "$LOG_DIR/gunicorn_startup.log" 2>&1
    log_line "INFO" "Gunicorn start command executed; output redirected to $LOG_DIR/gunicorn_startup.log"
    
    # Wait a moment for startup
    sleep 2
    
    if is_running; then
        PID=$(get_pid)
        echo -e "${GREEN}✓ Server started successfully (PID: $PID)${NC}"
        log_line "INFO" "Server started successfully (PID: $PID)"
        return 0
    else
        echo -e "${RED}✗ Failed to start server${NC}"
        echo -e "${YELLOW}Check logs: $LOG_DIR/gunicorn_startup.log${NC}"
        log_line "ERROR" "Server failed to start; check $LOG_DIR/gunicorn_startup.log"
        return 1
    fi
}

# Stop the server
stop() {
    check_user stop
    
    if ! is_running; then
        echo -e "${YELLOW}Server is not running${NC}"
        log_line "WARN" "Stop requested but server is not running"
        # Clean up stale PID file
        if [ -f "$PIDFILE" ]; then
            rm -f "$PIDFILE"
            echo -e "${BLUE}Removed stale PID file${NC}"
            log_line "INFO" "Removed stale PID file: $PIDFILE"
        fi
        return 0
    fi
    
    PID=$(get_pid)
    echo -e "${BLUE}Stopping MCC-Web server (PID: $PID)...${NC}"
    log_line "INFO" "Stopping server (PID: $PID)"
    
    # Try graceful shutdown first
    kill -TERM "$PID" 2>/dev/null
    
    # Wait for process to stop
    for i in {1..30}; do
        if [ "$i" -eq 1 ] || [ "$i" -eq 10 ] || [ "$i" -eq 20 ] || [ "$i" -eq 30 ]; then
            log_line "INFO" "Stop wait loop: second=$i pid=$PID"
        fi
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$PIDFILE"
            echo -e "${GREEN}✓ Server stopped successfully${NC}"
            log_line "INFO" "Server stopped successfully"
            return 0
        fi
        sleep 1
    done

    log_line "INFO" "Stop wait loop completed; checking if PID still alive: $PID"
    
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${YELLOW}Graceful shutdown failed, forcing stop...${NC}"
        log_line "WARN" "Graceful shutdown failed; forcing stop (PID: $PID)"
        kill -KILL "$PID" 2>/dev/null
        log_line "INFO" "Force kill sent (PID: $PID) exit_code=$?"
        sleep 1
        rm -f "$PIDFILE"
        echo -e "${GREEN}✓ Server force-stopped${NC}"
        log_line "INFO" "Server force-stopped"
    else
        log_line "INFO" "Stop completed without force kill (PID: $PID)"
    fi
    
    return 0
}

# Restart the server
restart() {
    check_user restart
    log_line "INFO" "Restart requested"
    stop
    log_line "INFO" "Restart: stop completed with exit code $?"
    sleep 2
    start
    log_line "INFO" "Restart: start completed with exit code $?"
}

# Reload the server (HUP signal)
reload() {
    check_user reload
    
    if ! is_running; then
        echo -e "${YELLOW}Server is not running, starting instead...${NC}"
        log_line "WARN" "Reload requested but server is not running; starting instead"
        start
        return $?
    fi
    
    PID=$(get_pid)
    echo -e "${BLUE}Reloading MCC-Web server (PID: $PID)...${NC}"
    log_line "INFO" "Reloading server (PID: $PID)"
    
    kill -HUP "$PID" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Reload signal sent${NC}"
        log_line "INFO" "Reload signal sent"
        return 0
    else
        echo -e "${RED}✗ Failed to send reload signal${NC}"
        log_line "ERROR" "Failed to send reload signal"
        return 1
    fi
}

# Show server status
status() {
    if is_running; then
        PID=$(get_pid)
        echo -e "${GREEN}✓ Server is running (PID: $PID)${NC}"
        log_line "INFO" "Status: running (PID: $PID)"
        
        # Show process info
        if command -v ps >/dev/null 2>&1; then
            echo ""
            ps -p "$PID" -o pid,ppid,user,start,time,cmd 2>/dev/null || true
        fi
        return 0
    else
        echo -e "${RED}✗ Server is not running${NC}"
        log_line "INFO" "Status: not running"
        return 1
    fi
}

# Main
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    reload)
        reload
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|reload|status}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the MCC-Web server"
        echo "  stop    - Stop the MCC-Web server"
        echo "  restart - Restart the MCC-Web server"
        echo "  reload  - Reload configuration (HUP signal)"
        echo "  status  - Show server status"
        echo ""
        echo "Environment variables:"
        echo "  MCC_USER     - User to run as (default: mcc)"
        echo "  MCC_GROUP    - Group to run as (default: mcc)"
        echo "  VENV_DIR     - Virtual environment directory (default: \$PROJECT_DIR/venv)"
        exit 1
        ;;
esac

exit $?
