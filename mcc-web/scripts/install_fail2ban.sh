#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    install_fail2ban.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Installationsskript für Fail2ban-Konfiguration
# 
# Installation:
#   sudo bash /data/appl/mcc/mcc-web/scripts/install_fail2ban.sh
#
# Test:
#   sudo fail2ban-client status
#   sudo fail2ban-client status mcc-django-auth

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging-Funktion
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Prüfe ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    log_error "Dieses Skript muss als root ausgeführt werden (sudo)"
    exit 1
fi

# Pfade
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAIL_CONF="${SCRIPT_DIR}/mcc-fail2ban.conf"
FILTER_DIR="${SCRIPT_DIR}/filter.d"
TARGET_JAIL="/etc/fail2ban/jail.d/mcc.conf"
TARGET_FILTER_DIR="/etc/fail2ban/filter.d"

log_info "Installiere Fail2ban-Konfiguration für MyCyclingCity..."

# Prüfe ob Fail2ban installiert ist
if ! command -v fail2ban-client &> /dev/null; then
    log_error "Fail2ban ist nicht installiert!"
    log_info "Installiere Fail2ban..."
    apt-get update
    apt-get install -y fail2ban
fi

# Prüfe ob Konfigurationsdateien existieren
if [ ! -f "${JAIL_CONF}" ]; then
    log_error "Jail-Konfiguration nicht gefunden: ${JAIL_CONF}"
    exit 1
fi

if [ ! -d "${FILTER_DIR}" ]; then
    log_error "Filter-Verzeichnis nicht gefunden: ${FILTER_DIR}"
    exit 1
fi

# Erstelle Zielverzeichnisse falls nötig
mkdir -p "$(dirname "${TARGET_JAIL}")"
mkdir -p "${TARGET_FILTER_DIR}"

# Kopiere Jail-Konfiguration
log_info "Kopiere Jail-Konfiguration..."
cp "${JAIL_CONF}" "${TARGET_JAIL}"
chmod 644 "${TARGET_JAIL}"

# Kopiere Filter-Dateien
log_info "Kopiere Filter-Dateien..."
for filter_file in "${FILTER_DIR}"/mcc-*.conf; do
    if [ -f "${filter_file}" ]; then
        filename=$(basename "${filter_file}")
        cp "${filter_file}" "${TARGET_FILTER_DIR}/${filename}"
        chmod 644 "${TARGET_FILTER_DIR}/${filename}"
        log_info "  - ${filename}"
    fi
done

# Prüfe Log-Verzeichnis
LOG_DIR="/data/var/mcc/logs"
if [ ! -d "${LOG_DIR}" ]; then
    log_warn "Log-Verzeichnis nicht gefunden: ${LOG_DIR}"
    log_warn "Erstelle Verzeichnis..."
    mkdir -p "${LOG_DIR}"
    chown mcc:mcc "${LOG_DIR}" 2>/dev/null || log_warn "Konnte Besitzer nicht ändern (mcc:mcc)"
fi

# Prüfe ob Log-Dateien existieren
log_info "Prüfe Log-Dateien..."
REQUIRED_LOGS=(
    "${LOG_DIR}/django.log"
    "${LOG_DIR}/gunicorn_access.log"
    "${LOG_DIR}/gunicorn_error.log"
)

for log_file in "${REQUIRED_LOGS[@]}"; do
    if [ ! -f "${log_file}" ]; then
        log_warn "Log-Datei nicht gefunden: ${log_file}"
        log_warn "Erstelle leere Datei..."
        touch "${log_file}"
        chown mcc:mcc "${log_file}" 2>/dev/null || log_warn "Konnte Besitzer nicht ändern"
        chmod 644 "${log_file}"
    fi
done

# Validiere Fail2ban-Konfiguration
log_info "Validiere Fail2ban-Konfiguration..."
if fail2ban-client -t 2>&1 | grep -q "error"; then
    log_error "Fail2ban-Konfiguration hat Fehler!"
    fail2ban-client -t
    exit 1
fi

# Lade Fail2ban neu
log_info "Lade Fail2ban neu..."
systemctl reload fail2ban || systemctl restart fail2ban

# Warte kurz
sleep 2

# Zeige Status
log_info "Fail2ban-Status:"
fail2ban-client status

log_info ""
log_info "MCC-spezifische Jails:"
for jail in mcc-django-auth mcc-django-scanner mcc-django-attack mcc-django-bruteforce mcc-gunicorn-error; do
    if fail2ban-client status "${jail}" &>/dev/null; then
        log_info "  ✓ ${jail} - aktiv"
        banned_count=$(fail2ban-client get "${jail}" banned 2>/dev/null | wc -l)
        if [ "${banned_count}" -gt 0 ]; then
            log_info "    Gebannte IPs: ${banned_count}"
        fi
    else
        log_warn "  ✗ ${jail} - nicht aktiv"
    fi
done

log_info ""
log_info "Installation abgeschlossen!"
log_info ""
log_info "Nützliche Befehle:"
log_info "  sudo fail2ban-client status mcc-django-auth"
log_info "  sudo fail2ban-client get mcc-django-auth banned"
log_info "  sudo fail2ban-client unban <IP> -j mcc-django-auth"
log_info "  sudo fail2ban-client set mcc-django-auth unbanip <IP>"
log_info "  sudo tail -f /var/log/fail2ban.log"
