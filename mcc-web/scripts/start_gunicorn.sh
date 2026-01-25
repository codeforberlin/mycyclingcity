#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    start_gunicorn.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Startet Gunicorn für mcc-web

PROJECT_DIR="/data/appl/mcc/mcc-web"
VENV_DIR="/data/appl/mcc/venv"
PIDFILE="/data/var/mcc/tmp/mcc-web.pid"
LOG_DIR="/data/var/mcc/logs"

# Prüfe ob wir in Produktion sind (Pfad existiert)
if [ ! -d "$PROJECT_DIR" ] || [[ "$PROJECT_DIR" != *"/data/appl/mcc"* ]]; then
    # Fallback für Entwicklung
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
    VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
    PIDFILE="$PROJECT_DIR/tmp/mcc-web.pid"
    LOG_DIR="$PROJECT_DIR/logs"
fi

cd "$PROJECT_DIR" || exit 1

# Erstelle Verzeichnisse
mkdir -p "$(dirname "$PIDFILE")"
mkdir -p "$LOG_DIR"

# Prüfe ob bereits läuft
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Gunicorn läuft bereits (PID: $PID)"
        exit 1
    else
        # Alte PID-Datei entfernen
        rm -f "$PIDFILE"
    fi
fi

# Setze Umgebungsvariablen
export DJANGO_SETTINGS_MODULE=config.settings
export PYTHONPATH="$PROJECT_DIR"

# Prüfe ob venv existiert
if [ ! -f "$VENV_DIR/bin/gunicorn" ]; then
    echo "Fehler: Gunicorn nicht gefunden in $VENV_DIR/bin/gunicorn"
    echo "Bitte venv installieren: python3 -m venv $VENV_DIR"
    exit 1
fi

# Starte Gunicorn
"$VENV_DIR/bin/gunicorn" -c config/gunicorn_config.py config.wsgi:application

if [ -f "$PIDFILE" ]; then
    echo "Gunicorn gestartet (PID: $(cat $PIDFILE))"
else
    echo "Fehler: Gunicorn konnte nicht gestartet werden"
    exit 1
fi
