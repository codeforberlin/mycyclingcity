#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    fix_fail2ban.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Behebt fehlerhafte Fail2ban-Konfiguration und installiert korrigierte Version

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

log_info "Behebe fehlerhafte Fail2ban-Konfiguration..."

# Entferne fehlerhafte Konfiguration
if [ -f "/etc/fail2ban/jail.d/mcc-apache.conf" ]; then
    log_info "Entferne fehlerhafte Apache-Konfiguration..."
    rm -f /etc/fail2ban/jail.d/mcc-apache.conf
fi

# Installiere korrigierte Version
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/install_fail2ban_apache.sh" ]; then
    log_info "Installiere korrigierte Apache-Konfiguration..."
    bash "${SCRIPT_DIR}/install_fail2ban_apache.sh"
else
    log_error "Installationsskript nicht gefunden: ${SCRIPT_DIR}/install_fail2ban_apache.sh"
    exit 1
fi

log_info "Fertig!"
