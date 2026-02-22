#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_fail2ban_filters.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Testet Fail2ban-Filter auf dem Produktionssystem mit echten Log-Dateien
# 
# Verwendung:
#   sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban_filters.sh

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

# Prüfe ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    log_error "Dieses Skript muss als root ausgeführt werden (sudo)"
    exit 1
fi

# Prüfe ob Fail2ban installiert ist
if ! command -v fail2ban-regex &> /dev/null; then
    log_error "fail2ban-regex ist nicht installiert!"
    exit 1
fi

echo ""
log_info "=== Fail2ban Filter Test auf Produktionssystem ==="
echo ""

# Apache-Filter testen
log_test "=== Apache-Filter Tests ==="
echo ""

APACHE_FILTERS=(
    "mcc-apache-auth"
    "mcc-apache-scanner"
    "mcc-apache-attack"
    "mcc-apache-bruteforce"
    "mcc-apache-badbots"
    "mcc-apache-noscript"
)

APACHE_LOGS=(
    "/var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d)"
    "/var/log/apache2/MCC_access_log.$(date +%Y%m%d)"
    "/var/log/apache2/MCC_ssl_access_log.$(( $(date +%Y%m%d) - 1 ))"
    "/var/log/apache2/MCC_access_log.$(( $(date +%Y%m%d) - 1 ))"
)

# Finde verfügbare Apache-Log-Dateien
AVAILABLE_APACHE_LOGS=()
for log_pattern in "${APACHE_LOGS[@]}"; do
    if [ -f "${log_pattern}" ]; then
        AVAILABLE_APACHE_LOGS+=("${log_pattern}")
    fi
done

if [ ${#AVAILABLE_APACHE_LOGS[@]} -eq 0 ]; then
    log_warn "Keine Apache-Log-Dateien gefunden!"
    log_warn "Erwartete Pfade:"
    for log in "${APACHE_LOGS[@]}"; do
        echo "  - ${log}"
    done
else
    log_info "Gefundene Apache-Log-Dateien:"
    for log in "${AVAILABLE_APACHE_LOGS[@]}"; do
        size=$(du -h "${log}" | cut -f1)
        lines=$(wc -l < "${log}")
        log_info "  ✓ ${log} (${size}, ${lines} Zeilen)"
    done
    echo ""
    
    # Teste jeden Filter
    for filter in "${APACHE_FILTERS[@]}"; do
        filter_path="/etc/fail2ban/filter.d/${filter}.conf"
        
        if [ ! -f "${filter_path}" ]; then
            log_warn "Filter nicht gefunden: ${filter_path}"
            continue
        fi
        
        log_test "Teste Filter: ${filter}"
        
        total_matches=0
        total_lines=0
        
        for log_file in "${AVAILABLE_APACHE_LOGS[@]}"; do
            log_info "  Analysiere: $(basename ${log_file})"
            
            # Führe fail2ban-regex aus
            result=$(fail2ban-regex "${log_file}" "${filter_path}" 2>&1)
            
            # Extrahiere Anzahl der Matches
            matches=$(echo "${result}" | grep -oP "Matched: \K[0-9]+" || echo "0")
            lines_checked=$(echo "${result}" | grep -oP "Lines: \K[0-9]+" || echo "0")
            
            if [ "${matches}" -gt 0 ]; then
                log_result "    → ${matches} Matches in ${lines_checked} Zeilen"
                
                # Zeige Beispiel-Matches (erste 5)
                echo "${result}" | grep -A 2 "Matched:" | head -10 | while read line; do
                    if echo "${line}" | grep -q "Matched\|^[0-9]"; then
                        echo "      ${line}"
                    fi
                done
            else
                log_info "    → Keine Matches (normal, wenn keine Angriffe im Log)"
            fi
            
            total_matches=$((total_matches + matches))
            total_lines=$((total_lines + lines_checked))
        done
        
        if [ ${total_matches} -gt 0 ]; then
            log_result "  Gesamt: ${total_matches} Matches in ${total_lines} Zeilen"
        else
            log_info "  Gesamt: Keine Matches gefunden"
        fi
        echo ""
    done
fi

# Django/Gunicorn-Filter testen
log_test "=== Django/Gunicorn-Filter Tests ==="
echo ""

DJANGO_FILTERS=(
    "mcc-django-auth"
    "mcc-django-scanner"
    "mcc-django-attack"
    "mcc-django-bruteforce"
    "mcc-gunicorn-error"
)

DJANGO_LOGS=(
    "/data/var/mcc/logs/django.log"
    "/data/var/mcc/logs/gunicorn_access.log"
    "/data/var/mcc/logs/gunicorn_error.log"
    "/data/var/mcc/logs/api.log"
)

# Finde verfügbare Django-Log-Dateien
AVAILABLE_DJANGO_LOGS=()
for log_file in "${DJANGO_LOGS[@]}"; do
    if [ -f "${log_file}" ]; then
        AVAILABLE_DJANGO_LOGS+=("${log_file}")
    fi
done

if [ ${#AVAILABLE_DJANGO_LOGS[@]} -eq 0 ]; then
    log_warn "Keine Django/Gunicorn-Log-Dateien gefunden!"
    log_warn "Erwartete Pfade:"
    for log in "${DJANGO_LOGS[@]}"; do
        echo "  - ${log}"
    done
else
    log_info "Gefundene Django/Gunicorn-Log-Dateien:"
    for log in "${AVAILABLE_DJANGO_LOGS[@]}"; do
        size=$(du -h "${log}" | cut -f1)
        lines=$(wc -l < "${log}")
        log_info "  ✓ ${log} (${size}, ${lines} Zeilen)"
    done
    echo ""
    
    # Teste jeden Filter
    for filter in "${DJANGO_FILTERS[@]}"; do
        filter_path="/etc/fail2ban/filter.d/${filter}.conf"
        
        if [ ! -f "${filter_path}" ]; then
            log_warn "Filter nicht gefunden: ${filter_path}"
            continue
        fi
        
        log_test "Teste Filter: ${filter}"
        
        total_matches=0
        total_lines=0
        
        for log_file in "${AVAILABLE_DJANGO_LOGS[@]}"; do
            # Prüfe ob dieser Filter für diese Log-Datei relevant ist
            case "${filter}" in
                mcc-gunicorn-error)
                    if [[ ! "${log_file}" =~ (gunicorn_error|django) ]]; then
                        continue
                    fi
                    ;;
                mcc-django-*)
                    if [[ "${log_file}" =~ gunicorn_error ]]; then
                        continue
                    fi
                    ;;
            esac
            
            log_info "  Analysiere: $(basename ${log_file})"
            
            # Führe fail2ban-regex aus
            result=$(fail2ban-regex "${log_file}" "${filter_path}" 2>&1)
            
            # Extrahiere Anzahl der Matches
            matches=$(echo "${result}" | grep -oP "Matched: \K[0-9]+" || echo "0")
            lines_checked=$(echo "${result}" | grep -oP "Lines: \K[0-9]+" || echo "0")
            
            if [ "${matches}" -gt 0 ]; then
                log_result "    → ${matches} Matches in ${lines_checked} Zeilen"
                
                # Zeige Beispiel-Matches (erste 5)
                echo "${result}" | grep -A 2 "Matched:" | head -10 | while read line; do
                    if echo "${line}" | grep -q "Matched\|^[0-9]"; then
                        echo "      ${line}"
                    fi
                done
            else
                log_info "    → Keine Matches (normal, wenn keine Angriffe im Log)"
            fi
            
            total_matches=$((total_matches + matches))
            total_lines=$((total_lines + lines_checked))
        done
        
        if [ ${total_matches} -gt 0 ]; then
            log_result "  Gesamt: ${total_matches} Matches in ${total_lines} Zeilen"
        else
            log_info "  Gesamt: Keine Matches gefunden"
        fi
        echo ""
    done
fi

# Zusammenfassung
echo ""
log_info "=== Zusammenfassung ==="
echo ""

log_info "Getestete Filter:"
echo "  Apache-Filter: ${#APACHE_FILTERS[@]}"
echo "  Django-Filter: ${#DJANGO_FILTERS[@]}"
echo ""

log_info "Verwendete Log-Dateien:"
echo "  Apache-Logs: ${#AVAILABLE_APACHE_LOGS[@]}"
echo "  Django-Logs: ${#AVAILABLE_DJANGO_LOGS[@]}"
echo ""

log_info "Nächste Schritte:"
echo "  1. Prüfen Sie die Matches oben"
echo "  2. Wenn Matches gefunden wurden, prüfen Sie ob die IPs gebannt werden sollten"
echo "  3. Überwachen Sie Fail2ban-Logs: sudo tail -f /var/log/fail2ban.log"
echo "  4. Prüfen Sie gebannte IPs: sudo fail2ban-client get <jail-name> banned"
echo ""
