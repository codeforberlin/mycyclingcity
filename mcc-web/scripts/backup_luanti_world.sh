#!/bin/bash
#
# MyCyclingCity Luanti World Backup
# Stündliche Sicherung der Welt (SQLite-konsistent via .backup, optional Server-Stop).
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/backup_luanti_world.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_help() {
    cat << EOF
MyCyclingCity Luanti World Backup

Verwendung:
    $0 [OPTIONEN] [KONFIGURATIONSDATEI]

Optionen:
    -h, --help     Hilfe anzeigen
    --dry-run      Nur anzeigen, was gesichert würde

Ablauf (QUIESCE_MODE=live, Standard):
    1. Staging-Verzeichnis anlegen
    2. Nicht-SQLite-Dateien kopieren
    3. map/players/auth/… per sqlite3 ".backup" sichern
    4. tar.gz nach BACKUP_LOCAL_DIR
    5. Alte Archive nach Retention löschen

Ablauf (QUIESCE_MODE=stop):
    1. Sessions vorbereiten + Luanti stoppen
    2. Welt + optionale Extra-Pfade tarren
    3. Luanti wieder starten

Beispiele:
    $0
    $0 /path/to/backup_luanti_world.conf
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
LUANTI_SERVER_DIR="/data/games/mcc/luanti"
LUANTI_WORLD_NAME="mycyclingcity"
BACKUP_LOCAL_DIR="/data/var/mcc/backups/luanti"
LOG_DIR="/data/var/mcc/logs"
BACKUP_RETENTION_COUNT=48
# live = sqlite .backup im laufenden Betrieb | stop = Server kurz stoppen
QUIESCE_MODE="live"
LUANTI_SERVER_SCRIPT="${SCRIPT_DIR}/luanti_server.sh"
# Relativ zu LUANTI_SERVER_DIR (Leerzeichen-getrennt), z. B. minetest.conf
LUANTI_EXTRA_PATHS="minetest.conf"
SQLITE3_BIN="$(command -v sqlite3 || true)"

if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${CONFIG_FILE}"
else
    echo -e "${YELLOW}Hinweis: Konfig nicht gefunden (${CONFIG_FILE}), verwende Defaults.${NC}" >&2
    echo -e "${YELLOW}Tipp: cp ${SCRIPT_DIR}/backup_luanti_world.conf.example ${SCRIPT_DIR}/backup_luanti_world.conf${NC}" >&2
fi

WORLD_PATH="${LUANTI_SERVER_DIR}/worlds/${LUANTI_WORLD_NAME}"

mkdir -p "${BACKUP_LOCAL_DIR}" "${LOG_DIR}" 2>/dev/null || true
LOG_FILE="${LOG_DIR}/luanti_backup_$(date +%Y%m%d).log"
LOG_TO_FILE=0
if [[ -d "${LOG_DIR}" ]] && [[ -w "${LOG_DIR}" ]]; then
    if [[ -e "${LOG_FILE}" ]] && [[ ! -w "${LOG_FILE}" ]]; then
        LOG_FILE="${LOG_DIR}/luanti_backup_$(date +%Y%m%d)_$(id -un).log"
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

SERVER_WAS_RUNNING=0

restart_server_if_needed() {
    if [[ "${SERVER_WAS_RUNNING}" -eq 1 ]]; then
        log_info "Starte Luanti wieder (QUIESCE_MODE=stop)"
        if ! MCC_LUANTI_WORLD="${LUANTI_WORLD_NAME}" \
            MCC_LUANTI_SERVER_DIR="${LUANTI_SERVER_DIR}" \
            "${LUANTI_SERVER_SCRIPT}" start; then
            log_error "Luanti-Start nach Backup fehlgeschlagen — bitte manuell prüfen!"
        else
            SERVER_WAS_RUNNING=0
        fi
    fi
}

trap restart_server_if_needed EXIT

cleanup_old_backups() {
    local keep="${BACKUP_RETENTION_COUNT}"
    local count
    count="$(find "${BACKUP_LOCAL_DIR}" -maxdepth 1 -type f -name 'luanti_world_*.tar.gz' | wc -l | tr -d ' ')"
    if [[ "${count}" -le "${keep}" ]]; then
        log_info "Retention: ${count} Backups vorhanden (Limit ${keep}) – nichts zu löschen"
        return 0
    fi
    local to_delete=$((count - keep))
    log_info "Retention: lösche ${to_delete} alte Backup(s), behalte ${keep}"
    find "${BACKUP_LOCAL_DIR}" -maxdepth 1 -type f -name 'luanti_world_*.tar.gz' -printf '%T@ %p\n' \
        | sort -n \
        | head -n "${to_delete}" \
        | awk '{print $2}' \
        | while read -r oldfile; do
            rm -f "${oldfile}"
            log_info "Gelöscht: ${oldfile}"
        done
}

stage_world_live() {
    local stage="$1"
    local dest="${stage}/${LUANTI_WORLD_NAME}"
    mkdir -p "${dest}"

    # Copy non-SQLite files first (world.mt, env_meta, …).
    if command -v rsync >/dev/null 2>&1; then
        rsync -a \
            --exclude='*.sqlite' \
            --exclude='*.sqlite-journal' \
            --exclude='*.sqlite-wal' \
            --exclude='*.sqlite-shm' \
            "${WORLD_PATH}/" "${dest}/"
    else
        # Fallback without rsync
        (
            cd "${WORLD_PATH}" && find . -type f \
                ! -name '*.sqlite' \
                ! -name '*.sqlite-journal' \
                ! -name '*.sqlite-wal' \
                ! -name '*.sqlite-shm' \
                -print0
        ) | while IFS= read -r -d '' rel; do
            mkdir -p "${dest}/$(dirname "${rel}")"
            cp -a "${WORLD_PATH}/${rel}" "${dest}/${rel}"
        done
    fi

    local dbname
    shopt -s nullglob
    for dbpath in "${WORLD_PATH}"/*.sqlite; do
        dbname="$(basename "${dbpath}")"
        if [[ -z "${SQLITE3_BIN}" ]]; then
            log_warn "sqlite3 fehlt — kopiere ${dbname} roh (weniger konsistent)"
            cp -a "${dbpath}" "${dest}/${dbname}"
            continue
        fi
        log_info "SQLite-Backup: ${dbname}"
        if ! "${SQLITE3_BIN}" "${dbpath}" ".backup '${dest}/${dbname}'"; then
            log_error "sqlite3 .backup fehlgeschlagen für ${dbpath}"
            return 1
        fi
    done
    shopt -u nullglob
}

copy_extra_into_stage() {
    local stage="$1"
    local name
    for name in ${LUANTI_EXTRA_PATHS}; do
        if [[ -e "${LUANTI_SERVER_DIR}/${name}" ]]; then
            mkdir -p "${stage}/_server"
            cp -a "${LUANTI_SERVER_DIR}/${name}" "${stage}/_server/${name}"
            log_info "Extra: ${name}"
        else
            log_warn "Extra-Pfad fehlt, übersprungen: ${LUANTI_SERVER_DIR}/${name}"
        fi
    done
}

main() {
    log_info "=== Luanti World Backup gestartet ==="
    log_info "Server: ${LUANTI_SERVER_DIR}"
    log_info "Welt:   ${WORLD_PATH}"
    log_info "Modus:  ${QUIESCE_MODE}"
    log_info "Ziel:   ${BACKUP_LOCAL_DIR}"
    if [[ "${LOG_TO_FILE}" -eq 0 ]]; then
        log_warn "Logdatei nicht schreibbar (${LOG_DIR}) – nur stderr."
    fi
    if [[ ! -w "${BACKUP_LOCAL_DIR}" ]]; then
        log_error "Backup-Ziel nicht schreibbar: ${BACKUP_LOCAL_DIR}"
        log_error "Als root: mkdir -p ${BACKUP_LOCAL_DIR} && setfacl -m u:$(id -un):rwx ${BACKUP_LOCAL_DIR}"
        exit 1
    fi
    if [[ ! -d "${LUANTI_SERVER_DIR}" ]]; then
        log_error "LUANTI_SERVER_DIR existiert nicht: ${LUANTI_SERVER_DIR}"
        exit 1
    fi
    if [[ ! -d "${WORLD_PATH}" ]]; then
        log_error "Welt fehlt: ${WORLD_PATH}"
        exit 1
    fi

    local timestamp archive
    timestamp="$(date +%Y%m%d_%H%M%S)"
    archive="${BACKUP_LOCAL_DIR}/luanti_world_${timestamp}.tar.gz"

    if [[ "${DRY_RUN}" -eq 1 ]]; then
        log_info "DRY-RUN: würde sichern: ${WORLD_PATH} (+ ${LUANTI_EXTRA_PATHS}) -> ${archive}"
        exit 0
    fi

    local stage
    stage="$(mktemp -d "${BACKUP_LOCAL_DIR}/.luanti_stage_XXXXXX")"
    # shellcheck disable=SC2064
    trap "rm -rf '${stage}'; restart_server_if_needed" EXIT

    if [[ "${QUIESCE_MODE}" == "stop" ]]; then
        if [[ ! -x "${LUANTI_SERVER_SCRIPT}" ]]; then
            log_error "luanti_server.sh nicht ausführbar: ${LUANTI_SERVER_SCRIPT}"
            exit 1
        fi
        if MCC_LUANTI_WORLD="${LUANTI_WORLD_NAME}" \
            MCC_LUANTI_SERVER_DIR="${LUANTI_SERVER_DIR}" \
            "${LUANTI_SERVER_SCRIPT}" status >/dev/null 2>&1; then
            SERVER_WAS_RUNNING=1
            log_info "Stoppe Luanti für konsistentes Backup…"
            MCC_LUANTI_WORLD="${LUANTI_WORLD_NAME}" \
                MCC_LUANTI_SERVER_DIR="${LUANTI_SERVER_DIR}" \
                "${LUANTI_SERVER_SCRIPT}" stop
        else
            log_info "Luanti lief nicht — Backup ohne Stop"
        fi
        mkdir -p "${stage}/${LUANTI_WORLD_NAME}"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a "${WORLD_PATH}/" "${stage}/${LUANTI_WORLD_NAME}/"
        else
            cp -a "${WORLD_PATH}/." "${stage}/${LUANTI_WORLD_NAME}/"
        fi
    else
        if [[ "${QUIESCE_MODE}" != "live" ]]; then
            log_warn "Unbekannter QUIESCE_MODE=${QUIESCE_MODE} — verwende live"
        fi
        stage_world_live "${stage}"
    fi

    copy_extra_into_stage "${stage}"

    log_info "Erstelle Archiv: ${archive}"
    local tar_args=("${LUANTI_WORLD_NAME}")
    if [[ -d "${stage}/_server" ]]; then
        tar_args+=("_server")
    fi
    if tar -C "${stage}" -czf "${archive}" "${tar_args[@]}"; then
        local size
        size="$(du -h "${archive}" | awk '{print $1}')"
        log_info "Backup OK (${size}): ${archive}"
    else
        log_error "tar fehlgeschlagen"
        rm -f "${archive}"
        exit 1
    fi

    rm -rf "${stage}"
    # Restore primary EXIT trap (restart only)
    trap restart_server_if_needed EXIT
    restart_server_if_needed
    cleanup_old_backups

    log_info "=== Luanti World Backup fertig ==="
}

main "$@"
