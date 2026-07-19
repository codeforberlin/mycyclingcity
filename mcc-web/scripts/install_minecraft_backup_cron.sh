#!/bin/bash
#
# Installiert einen stündlichen Cron-Job für Minecraft-Welt-Backups
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_minecraft_world.sh"
CONFIG_FILE="${1:-${SCRIPT_DIR}/backup_minecraft_world.conf}"
CRON_MINUTE="${2:-5}"  # Minute innerhalb der Stunde (Standard: :05)

if [[ ! -f "${BACKUP_SCRIPT}" ]]; then
    echo "Fehler: Backup-Script nicht gefunden: ${BACKUP_SCRIPT}"
    exit 1
fi

if [[ ! -x "${BACKUP_SCRIPT}" ]]; then
    echo "Fehler: Backup-Script ist nicht ausführbar: ${BACKUP_SCRIPT}"
    echo "Bitte als Eigentümer (z.B. mcc) ausführen: chmod +x ${BACKUP_SCRIPT}"
    exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
    EXAMPLE="${SCRIPT_DIR}/backup_minecraft_world.conf.example"
    if [[ -f "${EXAMPLE}" ]]; then
        echo "Erstelle Konfiguration aus Beispiel: ${CONFIG_FILE}"
        cp "${EXAMPLE}" "${CONFIG_FILE}"
    else
        echo "Warnung: Keine Konfigurationsdatei – Script nutzt Defaults."
    fi
fi

CRON_ENTRY="${CRON_MINUTE} * * * * ${BACKUP_SCRIPT} ${CONFIG_FILE} >> /data/var/mcc/logs/minecraft_backup_cron.log 2>&1"

mkdir -p /data/var/mcc/logs /data/var/mcc/backups/minecraft

if crontab -l 2>/dev/null | grep -qF "${BACKUP_SCRIPT}"; then
    echo "Bestehenden Cron-Eintrag für Minecraft-Backup ersetzen..."
    crontab -l 2>/dev/null | grep -vF "${BACKUP_SCRIPT}" | crontab - || true
fi

(crontab -l 2>/dev/null; echo "${CRON_ENTRY}") | crontab -

echo "Cron-Job installiert: stündlich zur Minute ${CRON_MINUTE}"
echo "Script: ${BACKUP_SCRIPT}"
echo "Config: ${CONFIG_FILE}"
echo ""
echo "Aktuelle Cron-Einträge (Minecraft-Backup):"
crontab -l | grep -F "${BACKUP_SCRIPT}" || true
