#!/bin/bash
#
# MyCyclingCity Minecraft World Backup
# Stündliche Sicherung der Welten im laufenden Betrieb via RCON flush + tar.
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/backup_minecraft_world.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_help() {
    cat << EOF
MyCyclingCity Minecraft World Backup

Verwendung:
    $0 [OPTIONEN] [KONFIGURATIONSDATEI]

Optionen:
    -h, --help     Hilfe anzeigen
    --dry-run      Nur anzeigen, was gesichert würde (ohne tar / ohne RCON-Änderung)

Ablauf:
    1. RCON: save-off
    2. RCON: save-all flush
    3. tar.gz der Welt-Ordner
    4. RCON: save-on  (auch bei Fehler via trap)

Beispiele:
    $0
    $0 /path/to/backup_minecraft_world.conf
    $0 --dry-run

EOF
}

CONFIG_FILE=""
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        *)
            if [[ -z "${CONFIG_FILE}" ]]; then
                CONFIG_FILE="$1"
                if [[ ! "${CONFIG_FILE}" =~ ^/ ]]; then
                    CONFIG_FILE="${SCRIPT_DIR}/${CONFIG_FILE}"
                fi
            else
                echo "Unbekannter Parameter: $1" >&2
                exit 1
            fi
            ;;
    esac
    shift
done

if [[ -z "${CONFIG_FILE}" ]]; then
    CONFIG_FILE="${DEFAULT_CONFIG_FILE}"
fi

# Defaults (überschreibbar durch Konfig)
MC_SERVER_DIR="/data/games/minecraft_server"
MC_WORLD_DIRS="world world_nether world_the_end"
BACKUP_LOCAL_DIR="/data/var/mcc/backups/minecraft"
LOG_DIR="/data/var/mcc/logs"
BACKUP_RETENTION_COUNT=48
RCON_HOST="127.0.0.1"
RCON_PORT="25575"
RCON_PASSWORD=""
MCC_ENV_FILE="/data/appl/mcc/mcc-web/.env"
PYTHON_BIN="/data/appl/mcc/venv/bin/python3"
SAVE_FLUSH_WAIT_SECONDS=5
MC_EXTRA_PATHS=""

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo -e "${YELLOW}Hinweis: Konfig nicht gefunden (${CONFIG_FILE}), verwende Defaults.${NC}" >&2
    echo -e "${YELLOW}Tipp: cp ${SCRIPT_DIR}/backup_minecraft_world.conf.example ${SCRIPT_DIR}/backup_minecraft_world.conf${NC}" >&2
else
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
fi

mkdir -p "${BACKUP_LOCAL_DIR}" "${LOG_DIR}" 2>/dev/null || true
LOG_FILE="${LOG_DIR}/minecraft_backup_$(date +%Y%m%d).log"
LOG_TO_FILE=0
if [[ -d "${LOG_DIR}" ]] && [[ -w "${LOG_DIR}" ]]; then
    # Bestehende Logdatei kann von mccweb angelegt sein (dann für mcc nicht schreibbar)
    if [[ -e "${LOG_FILE}" ]] && [[ ! -w "${LOG_FILE}" ]]; then
        LOG_FILE="${LOG_DIR}/minecraft_backup_$(date +%Y%m%d)_$(id -un).log"
    fi
    if [[ ! -e "${LOG_FILE}" ]] || [[ -w "${LOG_FILE}" ]]; then
        if touch "${LOG_FILE}" 2>/dev/null; then
            LOG_TO_FILE=1
        fi
    fi
fi

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    local line="[${timestamp}] [${level}] ${message}"
    if [[ "${LOG_TO_FILE}" -eq 1 ]]; then
        echo "${line}" | tee -a "${LOG_FILE}" >&2
    else
        echo "${line}" >&2
    fi
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }

load_rcon_password_from_env() {
    if [[ -n "${RCON_PASSWORD}" ]]; then
        return 0
    fi
    if [[ -f "${MCC_ENV_FILE}" ]]; then
        local value
        value="$(grep -E '^MCC_MINECRAFT_RCON_PASSWORD=' "${MCC_ENV_FILE}" | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//')"
        if [[ -n "${value}" ]]; then
            RCON_PASSWORD="${value}"
            log_info "RCON-Passwort aus ${MCC_ENV_FILE} geladen"
            return 0
        fi
    fi
    if [[ -f "${MC_SERVER_DIR}/server.properties" ]]; then
        local value
        value="$(grep -E '^rcon\.password=' "${MC_SERVER_DIR}/server.properties" | tail -n1 | cut -d= -f2- | tr -d '\r')"
        if [[ -n "${value}" ]]; then
            RCON_PASSWORD="${value}"
            log_info "RCON-Passwort aus server.properties geladen"
            return 0
        fi
    fi
    return 1
}

rcon_cmd() {
    local command="$1"
    if [[ ! -x "${PYTHON_BIN}" ]]; then
        log_error "Python nicht gefunden/ausführbar: ${PYTHON_BIN}"
        return 1
    fi
    export RCON_COMMAND="${command}"
    RCON_HOST="${RCON_HOST}" RCON_PORT="${RCON_PORT}" RCON_PASSWORD="${RCON_PASSWORD}" \
    RCON_COMMAND="${command}" \
    "${PYTHON_BIN}" - <<'PY'
import os, sys
from mcrcon import MCRcon, MCRconException

host = os.environ["RCON_HOST"]
port = int(os.environ["RCON_PORT"])
password = os.environ["RCON_PASSWORD"]
command = os.environ["RCON_COMMAND"]

try:
    with MCRcon(host, password, port=port) as mcr:
        response = mcr.command(command) or ""
    print(response)
except MCRconException as exc:
    print(f"RCON error: {exc}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"RCON failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
}

rcon() {
    rcon_cmd "$1"
}

SAVES_DISABLED=0

enable_saves() {
    if [[ "${SAVES_DISABLED}" -eq 1 ]]; then
        log_info "RCON: save-on"
        if ! rcon "save-on" >/dev/null; then
            log_error "Konnte save-on nicht setzen – bitte manuell auf dem Server ausführen!"
        else
            SAVES_DISABLED=0
        fi
    fi
}

trap enable_saves EXIT

cleanup_old_backups() {
    local keep="${BACKUP_RETENTION_COUNT}"
    local count
    count="$(find "${BACKUP_LOCAL_DIR}" -maxdepth 1 -type f -name 'mc_world_*.tar.gz' | wc -l | tr -d ' ')"
    if [[ "${count}" -le "${keep}" ]]; then
        log_info "Retention: ${count} Backups vorhanden (Limit ${keep}) – nichts zu löschen"
        return 0
    fi
    local to_delete=$((count - keep))
    log_info "Retention: lösche ${to_delete} alte Backup(s), behalte ${keep}"
    find "${BACKUP_LOCAL_DIR}" -maxdepth 1 -type f -name 'mc_world_*.tar.gz' -printf '%T@ %p\n' \
        | sort -n \
        | head -n "${to_delete}" \
        | awk '{print $2}' \
        | while read -r oldfile; do
            rm -f "${oldfile}"
            log_info "Gelöscht: ${oldfile}"
        done
}

check_world_readable() {
    local world_name="$1"
    local level_dat="${MC_SERVER_DIR}/${world_name}/level.dat"
    if [[ ! -e "${level_dat}" ]]; then
        return 0
    fi
    if [[ -r "${level_dat}" ]]; then
        return 0
    fi
    log_error "Nicht lesbar nach save-all flush: ${level_dat}"
    if command -v getfacl >/dev/null 2>&1; then
        log_error "getfacl:"
        getfacl "${level_dat}" 2>&1 | while read -r line; do log_error "  ${line}"; done || true
    fi
    log_error "Ursache: Minecraft schreibt level.dat neu; Default-ACL fehlt oder greift nicht."
    log_error "Fix 1) Als root/mcc (nicht mccweb):"
    log_error "  ${SCRIPT_DIR}/setup_minecraft_backup_acl.sh ${MC_SERVER_DIR}/${world_name} mccweb"
    log_error "Fix 2) Cron für Welt-Backup als User mcc (mccweb bleibt isoliert, kein sudo):"
    log_error "  crontab -u mcc -e"
    log_error "  5 * * * * ${SCRIPT_DIR}/backup_minecraft_world.sh ${SCRIPT_DIR}/backup_minecraft_world.conf >> /data/var/mcc/logs/minecraft_backup_cron.log 2>&1"
    log_error "  (mcc braucht Schreibrecht auf BACKUP_LOCAL_DIR / LOG_DIR)"
    return 1
}

main() {
    log_info "=== Minecraft World Backup gestartet ==="
    log_info "Server: ${MC_SERVER_DIR}"
    log_info "Ziel:   ${BACKUP_LOCAL_DIR}"
    if [[ "${LOG_TO_FILE}" -eq 0 ]]; then
        log_warn "Logdatei nicht schreibbar (${LOG_DIR}) – nur stderr. Als root: setfacl -m u:$(id -un):rwx ${LOG_DIR}"
    fi
    if [[ ! -w "${BACKUP_LOCAL_DIR}" ]]; then
        log_error "Backup-Ziel nicht schreibbar: ${BACKUP_LOCAL_DIR}"
        log_error "Als root: mkdir -p ${BACKUP_LOCAL_DIR} && setfacl -m u:$(id -un):rwx ${BACKUP_LOCAL_DIR}"
        exit 1
    fi
    if [[ ! -d "${MC_SERVER_DIR}" ]]; then
        log_error "MC_SERVER_DIR existiert nicht: ${MC_SERVER_DIR}"
        exit 1
    fi

    local paths=()
    for name in ${MC_WORLD_DIRS}; do
        if [[ -e "${MC_SERVER_DIR}/${name}" ]]; then
            paths+=("${name}")
        else
            log_warn "Welt-Pfad fehlt, übersprungen: ${MC_SERVER_DIR}/${name}"
        fi
    done
    for name in ${MC_EXTRA_PATHS}; do
        if [[ -e "${MC_SERVER_DIR}/${name}" ]]; then
            paths+=("${name}")
        else
            log_warn "Extra-Pfad fehlt, übersprungen: ${MC_SERVER_DIR}/${name}"
        fi
    done

    if [[ ${#paths[@]} -eq 0 ]]; then
        log_error "Keine zu sichernden Pfade gefunden"
        exit 1
    fi

    local timestamp
    timestamp="$(date +%Y%m%d_%H%M%S)"
    local archive="${BACKUP_LOCAL_DIR}/mc_world_${timestamp}.tar.gz"

    if [[ "${DRY_RUN}" -eq 1 ]]; then
        log_info "DRY-RUN: würde sichern: ${paths[*]} -> ${archive}"
        exit 0
    fi

    if ! load_rcon_password_from_env; then
        log_error "Kein RCON-Passwort (Config / .env / server.properties)"
        exit 1
    fi

    log_info "RCON: save-off"
    rcon "save-off" >/dev/null
    SAVES_DISABLED=1

    log_info "RCON: save-all flush"
    rcon "save-all flush" >/dev/null
    sleep "${SAVE_FLUSH_WAIT_SECONDS}"

    local world
    for world in "${paths[@]}"; do
        check_world_readable "${world}" || exit 1
    done

    log_info "Erstelle Archiv: ${archive}"
    if tar -C "${MC_SERVER_DIR}" -czf "${archive}" "${paths[@]}"; then
        local size
        size="$(du -h "${archive}" | awk '{print $1}')"
        log_info "Backup OK (${size}): ${archive}"
    else
        log_error "tar fehlgeschlagen"
        rm -f "${archive}"
        exit 1
    fi

    enable_saves
    cleanup_old_backups

    log_info "=== Minecraft World Backup fertig ==="
}

main "$@"
