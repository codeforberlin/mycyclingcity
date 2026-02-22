#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_fail2ban_filter_single.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Testet einen einzelnen Fail2ban-Filter gegen eine Log-Datei
# 
# Verwendung:
#   sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban_filter_single.sh <filter-name> <log-file>
#
# Beispiele:
#   sudo bash test_fail2ban_filter_single.sh mcc-apache-auth /var/log/apache2/MCC_ssl_access_log.20260222
#   sudo bash test_fail2ban_filter_single.sh mcc-django-scanner /data/var/mcc/logs/gunicorn_access.log

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging-Funktionen
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_result() {
    echo -e "${CYAN}[RESULT]${NC} $1"
}

# Prüfe Parameter
if [ $# -lt 2 ]; then
    log_error "Verwendung: $0 <filter-name> <log-file>"
    echo ""
    echo "Beispiele:"
    echo "  $0 mcc-apache-auth /var/log/apache2/MCC_ssl_access_log.20260222"
    echo "  $0 mcc-django-scanner /data/var/mcc/logs/gunicorn_access.log"
    echo ""
    echo "Verfügbare Filter:"
    echo "  Apache:"
    echo "    - mcc-apache-auth"
    echo "    - mcc-apache-scanner"
    echo "    - mcc-apache-attack"
    echo "    - mcc-apache-bruteforce"
    echo "    - mcc-apache-badbots"
    echo "    - mcc-apache-noscript"
    echo "  Django:"
    echo "    - mcc-django-auth"
    echo "    - mcc-django-scanner"
    echo "    - mcc-django-attack"
    echo "    - mcc-django-bruteforce"
    echo "    - mcc-gunicorn-error"
    exit 1
fi

FILTER_NAME="$1"
LOG_FILE="$2"
FILTER_PATH="/etc/fail2ban/filter.d/${FILTER_NAME}.conf"

# Prüfe ob Filter existiert
if [ ! -f "${FILTER_PATH}" ]; then
    log_error "Filter nicht gefunden: ${FILTER_PATH}"
    exit 1
fi

# Prüfe ob Log-Datei existiert
if [ ! -f "${LOG_FILE}" ]; then
    log_error "Log-Datei nicht gefunden: ${LOG_FILE}"
    exit 1
fi

# Prüfe ob als root ausgeführt (für fail2ban-regex)
if [ "$EUID" -ne 0 ]; then 
    log_warn "Nicht als root ausgeführt - einige Funktionen könnten eingeschränkt sein"
fi

echo ""
log_test "=== Teste Filter: ${FILTER_NAME} ==="
log_info "Log-Datei: ${LOG_FILE}"
log_info "Filter: ${FILTER_PATH}"
echo ""

# Zeige Log-Datei-Info
size=$(du -h "${LOG_FILE}" | cut -f1)
lines=$(wc -l < "${LOG_FILE}")
log_info "Log-Datei Größe: ${size}, Zeilen: ${lines}"
echo ""

# Führe fail2ban-regex aus
log_test "Führe fail2ban-regex aus..."
echo ""

if command -v fail2ban-regex &> /dev/null; then
    result=$(fail2ban-regex "${LOG_FILE}" "${FILTER_PATH}" 2>&1)
    
    # Zeige vollständiges Ergebnis
    echo "${result}"
    echo ""
    
    # Extrahiere wichtige Informationen
    matches=$(echo "${result}" | grep -oP "Matched: \K[0-9]+" || echo "0")
    lines_checked=$(echo "${result}" | grep -oP "Lines: \K[0-9]+" || echo "0")
    
    if [ "${matches}" -gt 0 ]; then
        log_result "✓ ${matches} Matches gefunden in ${lines_checked} Zeilen"
        
        # Zeige Beispiel-Matches
        echo ""
        log_info "Beispiel-Matches (erste 10):"
        echo "${result}" | grep -A 1 "Matched:" | head -20 | while read line; do
            if echo "${line}" | grep -q "^[0-9]"; then
                echo "  ${line}"
            fi
        done
    else
        log_info "Keine Matches gefunden"
        log_info "Dies ist normal, wenn keine Angriffe im Log sind"
    fi
else
    log_error "fail2ban-regex nicht gefunden!"
    log_info "Installieren Sie Fail2ban: sudo apt-get install fail2ban"
    exit 1
fi

echo ""
log_info "=== Test abgeschlossen ==="
echo ""
