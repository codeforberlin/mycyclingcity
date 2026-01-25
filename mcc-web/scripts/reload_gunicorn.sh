#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    reload_gunicorn.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Lädt Gunicorn neu (HUP Signal)

PIDFILE="/data/var/mcc/tmp/mcc-web.pid"

# Fallback für Entwicklung
if [ ! -f "$PIDFILE" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    PIDFILE="$PROJECT_DIR/tmp/mcc-web.pid"
fi

if [ ! -f "$PIDFILE" ]; then
    echo "PID-Datei nicht gefunden. Gunicorn läuft möglicherweise nicht."
    exit 1
fi

PID=$(cat "$PIDFILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "Prozess mit PID $PID läuft nicht."
    rm -f "$PIDFILE"
    exit 1
fi

echo "Lade Gunicorn neu (PID: $PID)..."
kill -HUP "$PID"
echo "Reload-Signal gesendet."
