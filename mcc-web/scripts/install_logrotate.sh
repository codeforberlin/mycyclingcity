#!/bin/bash
#
# Installiert die logrotate-Konfiguration für MyCyclingCity
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGROTATE_CONF="${SCRIPT_DIR}/mcc-logrotate.conf"
TARGET_CONF="/etc/logrotate.d/mcc"

# Prüfe ob als root ausgeführt
if [[ $EUID -ne 0 ]]; then
    echo "Fehler: Dieses Script muss als root ausgeführt werden"
    echo "Verwendung: sudo $0"
    exit 1
fi

# Prüfe ob Konfigurationsdatei existiert
if [[ ! -f "${LOGROTATE_CONF}" ]]; then
    echo "Fehler: Logrotate-Konfiguration nicht gefunden: ${LOGROTATE_CONF}"
    exit 1
fi

# Prüfe ob bereits eine Konfiguration existiert
if [[ -f "${TARGET_CONF}" ]]; then
    echo "Warnung: Eine Logrotate-Konfiguration existiert bereits: ${TARGET_CONF}"
    echo ""
    read -p "Möchten Sie die bestehende Konfiguration ersetzen? (j/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[JjYy]$ ]]; then
        echo "Abgebrochen."
        exit 0
    fi
    echo "Erstelle Backup der alten Konfiguration..."
    cp "${TARGET_CONF}" "${TARGET_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Konfiguration kopieren
echo "Installiere Logrotate-Konfiguration..."
cp "${LOGROTATE_CONF}" "${TARGET_CONF}"
chmod 644 "${TARGET_CONF}"

echo "Logrotate-Konfiguration erfolgreich installiert: ${TARGET_CONF}"
echo ""

# Test durchführen
echo "Teste Konfiguration..."
if logrotate -d "${TARGET_CONF}" > /dev/null 2>&1; then
    echo "✓ Konfiguration ist gültig"
else
    echo "⚠ Warnung: Konfiguration könnte Probleme haben"
    echo "Führen Sie manuell aus: sudo logrotate -d ${TARGET_CONF}"
fi

echo ""
echo "Die Log-Rotation wird täglich durch logrotate ausgeführt."
echo "Sie können die Rotation manuell testen mit:"
echo "  sudo logrotate -f ${TARGET_CONF}"
