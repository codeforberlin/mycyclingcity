#!/bin/bash
#
# Installiert einen Cron-Job für tägliche MyCyclingCity Backups
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_mcc.sh"
CRON_TIME="${1:-22}"  # Standard: 22:00 Uhr abends
CONFIG_FILE="${2:-}"  # Optional: Konfigurationsdatei

# Prüfe ob Backup-Script existiert
if [[ ! -f "${BACKUP_SCRIPT}" ]]; then
    echo "Fehler: Backup-Script nicht gefunden: ${BACKUP_SCRIPT}"
    exit 1
fi

# Prüfe ob Script ausführbar ist
if [[ ! -x "${BACKUP_SCRIPT}" ]]; then
    echo "Mache Backup-Script ausführbar..."
    chmod +x "${BACKUP_SCRIPT}"
fi

# Cron-Job erstellen
# Wenn Konfigurationsdatei angegeben, verwende diese, sonst Standard
if [[ -n "${CONFIG_FILE}" ]]; then
    CRON_ENTRY="0 ${CRON_TIME} * * * ${BACKUP_SCRIPT} ${CONFIG_FILE} >> /data/var/mcc/logs/backup_cron.log 2>&1"
else
    CRON_ENTRY="0 ${CRON_TIME} * * * ${BACKUP_SCRIPT} >> /data/var/mcc/logs/backup_cron.log 2>&1"
fi

# Prüfe ob bereits ein Cron-Job existiert
if crontab -l 2>/dev/null | grep -q "${BACKUP_SCRIPT}"; then
    echo "Warnung: Ein Cron-Job für das Backup-Script existiert bereits."
    echo "Aktueller Cron-Job:"
    crontab -l | grep "${BACKUP_SCRIPT}"
    echo ""
    read -p "Möchten Sie den bestehenden Eintrag ersetzen? (j/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[JjYy]$ ]]; then
        echo "Abgebrochen."
        exit 0
    fi
    # Entferne alten Eintrag
    crontab -l 2>/dev/null | grep -v "${BACKUP_SCRIPT}" | crontab -
fi

# Neuen Cron-Job hinzufügen
(crontab -l 2>/dev/null; echo "${CRON_ENTRY}") | crontab -

echo "Cron-Job erfolgreich installiert!"
echo "Backup wird täglich um ${CRON_TIME}:00 Uhr ausgeführt."
if [[ -n "${CONFIG_FILE}" ]]; then
    echo "Verwendet Konfigurationsdatei: ${CONFIG_FILE}"
fi
echo ""
echo "Aktuelle Cron-Jobs:"
crontab -l | grep -A 1 -B 1 "${BACKUP_SCRIPT}" || crontab -l
