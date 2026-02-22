#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_fail2ban.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Test-Skript für Fail2ban-Konfiguration
# 
# Verwendung:
#   sudo bash /data/appl/mcc/mcc-web/scripts/test_fail2ban.sh

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Prüfe ob als root ausgeführt
if [ "$EUID" -ne 0 ]; then 
    log_error "Dieses Skript muss als root ausgeführt werden (sudo)"
    exit 1
fi

# Prüfe ob Fail2ban installiert ist
if ! command -v fail2ban-client &> /dev/null; then
    log_error "Fail2ban ist nicht installiert!"
    exit 1
fi

echo ""
log_info "=== Fail2ban Test-Suite ==="
echo ""

# Test 1: Fail2ban Status
log_test "Test 1: Fail2ban Service Status"
if systemctl is-active --quiet fail2ban; then
    log_info "✓ Fail2ban Service läuft"
else
    log_error "✗ Fail2ban Service läuft NICHT"
    exit 1
fi
echo ""

# Test 2: Alle Jails auflisten
log_test "Test 2: Verfügbare Jails"
echo "Status aller Jails:"
fail2ban-client status
echo ""

# Test 3: MCC-spezifische Jails prüfen
log_test "Test 3: MCC-spezifische Jails"
MCC_JAILS_APACHE=(
    "mcc-apache-auth"
    "mcc-apache-scanner"
    "mcc-apache-attack"
    "mcc-apache-bruteforce"
    "mcc-apache-badbots"
    "mcc-apache-noscript"
)

MCC_JAILS_DJANGO=(
    "mcc-django-auth"
    "mcc-django-scanner"
    "mcc-django-attack"
    "mcc-django-bruteforce"
    "mcc-gunicorn-error"
)

ALL_JAILS=("${MCC_JAILS_APACHE[@]}" "${MCC_JAILS_DJANGO[@]}")

for jail in "${ALL_JAILS[@]}"; do
    if fail2ban-client status "${jail}" &>/dev/null; then
        log_info "✓ ${jail} - aktiv"
        # Zeige Details
        banned_count=$(fail2ban-client get "${jail}" banned 2>/dev/null | wc -l)
        if [ "${banned_count}" -gt 0 ]; then
            log_info "  → Gebannte IPs: ${banned_count}"
            fail2ban-client get "${jail}" banned | head -5 | while read ip; do
                log_info "    - ${ip}"
            done
        fi
    else
        log_warn "✗ ${jail} - nicht aktiv"
    fi
done
echo ""

# Test 4: Filter testen
log_test "Test 4: Filter-Validierung"
log_info "Teste Apache-Filter..."

# Prüfe ob Apache-Logs existieren
APACHE_LOGS=(
    "/var/log/apache2/MCC_ssl_access_log.$(date +%Y%m%d)"
    "/var/log/apache2/MCC_access_log.$(date +%Y%m%d)"
)

for log_file in "${APACHE_LOGS[@]}"; do
    if [ -f "${log_file}" ]; then
        log_info "✓ Log-Datei gefunden: ${log_file}"
        
        # Teste Filter
        for filter in mcc-apache-auth mcc-apache-scanner mcc-apache-attack; do
            if [ -f "/etc/fail2ban/filter.d/${filter}.conf" ]; then
                log_info "  Teste Filter: ${filter}"
                if fail2ban-regex "${log_file}" "/etc/fail2ban/filter.d/${filter}.conf" 2>&1 | grep -q "Matched"; then
                    log_info "    ✓ Filter funktioniert"
                else
                    log_warn "    ⚠ Keine Matches gefunden (kann normal sein, wenn keine Angriffe im Log)"
                fi
            fi
        done
    fi
done
echo ""

# Test 5: Log-Pfade prüfen
log_test "Test 5: Log-Pfade prüfen"
for jail in "${MCC_JAILS_APACHE[@]}"; do
    if fail2ban-client status "${jail}" &>/dev/null; then
        log_info "Jail: ${jail}"
        logpath=$(fail2ban-client get "${jail}" logpath 2>/dev/null || echo "N/A")
        log_info "  Log-Pfad: ${logpath}"
        
        # Prüfe ob Log-Dateien existieren
        if echo "${logpath}" | grep -q "MCC.*log"; then
            # Extrahiere Log-Pfad (ohne Wildcard)
            base_path=$(echo "${logpath}" | awk '{print $1}' | sed 's/\*.*//')
            if ls ${base_path}* 1> /dev/null 2>&1; then
                log_info "  ✓ Log-Dateien gefunden"
            else
                log_warn "  ✗ Log-Dateien nicht gefunden: ${base_path}*"
            fi
        fi
    fi
done
echo ""

# Test 6: Manueller Bann-Test (optional)
log_test "Test 6: Manueller Bann-Test (optional)"
read -p "Möchten Sie eine Test-IP bannen? (j/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[JjYy]$ ]]; then
    read -p "Geben Sie eine Test-IP ein (z.B. 192.168.1.100): " test_ip
    if [[ $test_ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        log_info "Banne Test-IP: ${test_ip}"
        fail2ban-client set mcc-apache-auth banip "${test_ip}" 2>/dev/null || \
        fail2ban-client set mcc-django-auth banip "${test_ip}" 2>/dev/null || \
        log_warn "Konnte IP nicht bannen (kein aktiver Jail gefunden)"
        
        sleep 1
        
        # Prüfe ob gebannt
        if fail2ban-client get mcc-apache-auth banned 2>/dev/null | grep -q "${test_ip}" || \
           fail2ban-client get mcc-django-auth banned 2>/dev/null | grep -q "${test_ip}"; then
            log_info "✓ IP ${test_ip} wurde erfolgreich gebannt"
            
            read -p "Möchten Sie die Test-IP wieder entbannen? (j/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[JjYy]$ ]]; then
                fail2ban-client set mcc-apache-auth unbanip "${test_ip}" 2>/dev/null || \
                fail2ban-client set mcc-django-auth unbanip "${test_ip}" 2>/dev/null || true
                log_info "✓ IP ${test_ip} wurde entbannt"
            fi
        else
            log_warn "✗ IP wurde nicht gebannt"
        fi
    else
        log_error "Ungültige IP-Adresse"
    fi
fi
echo ""

# Test 7: Fail2ban-Log prüfen
log_test "Test 7: Fail2ban-Log prüfen"
if [ -f "/var/log/fail2ban.log" ]; then
    log_info "Letzte 10 Zeilen aus /var/log/fail2ban.log:"
    tail -10 /var/log/fail2ban.log | while read line; do
        if echo "${line}" | grep -q "ERROR"; then
            log_error "  ${line}"
        elif echo "${line}" | grep -q "WARNING"; then
            log_warn "  ${line}"
        else
            log_info "  ${line}"
        fi
    done
else
    log_warn "Fail2ban-Log nicht gefunden: /var/log/fail2ban.log"
fi
echo ""

# Test 8: Konfiguration validieren
log_test "Test 8: Konfiguration validieren"
if fail2ban-client -t 2>&1 | grep -q "error\|ERROR"; then
    log_error "✗ Konfiguration hat Fehler:"
    fail2ban-client -t 2>&1 | grep -i "error" | head -5
else
    log_info "✓ Konfiguration ist gültig"
fi
echo ""

# Zusammenfassung
log_info "=== Test-Zusammenfassung ==="
log_info "Aktive Jails:"
for jail in "${ALL_JAILS[@]}"; do
    if fail2ban-client status "${jail}" &>/dev/null; then
        echo "  ✓ ${jail}"
    fi
done
echo ""

log_info "Nützliche Befehle:"
echo "  sudo fail2ban-client status <jail-name>"
echo "  sudo fail2ban-client get <jail-name> banned"
echo "  sudo fail2ban-client set <jail-name> banip <IP>"
echo "  sudo fail2ban-client set <jail-name> unbanip <IP>"
echo "  sudo tail -f /var/log/fail2ban.log"
echo "  sudo fail2ban-regex <log-file> <filter-file>"
echo ""
