#!/bin/bash
#
# MyCyclingCity Backup Script
# Sichert Datenbank und wichtige Daten (ohne Logfiles) via rsync über SSH
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# Farben für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Konfiguration laden
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONFIG_FILE="${SCRIPT_DIR}/backup_mcc.conf"

# Hilfe anzeigen (muss vor Parameter-Verarbeitung definiert sein)
show_help() {
    cat << EOF
MyCyclingCity Backup Script

Verwendung:
    $0 [OPTIONEN] [KONFIGURATIONSDATEI]

Optionen:
    -h, --help          Zeigt diese Hilfe an
    KONFIGURATIONSDATEI Optional: Pfad zur Konfigurationsdatei
                        (Standard: ${DEFAULT_CONFIG_FILE})

Beispiele:
    # Standard-Konfiguration verwenden
    $0

    # Eigene Konfigurationsdatei angeben (absoluter Pfad)
    $0 /path/to/backup_mcc.conf

    # Eigene Konfigurationsdatei angeben (relativ zum Script-Verzeichnis)
    $0 custom_backup.conf

Hinweis:
    Die Konfigurationsdatei muss die folgenden Variablen enthalten:
    - SSH_HOST          Hostname oder IP des Backup-Servers
    - SSH_USER          Benutzername für SSH-Verbindung
    - REMOTE_BACKUP_DIR Zielverzeichnis auf dem Remote-Server
    - SSH_PORT          Optional: SSH-Port (Standard: 22)
    - SSH_KEY           Optional: Pfad zu SSH-Private-Key

EOF
}

# Parameter verarbeiten
CONFIG_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            if [[ -z "${CONFIG_FILE}" ]]; then
                CONFIG_FILE="$1"
                # Prüfe ob absoluter oder relativer Pfad
                if [[ ! "${CONFIG_FILE}" =~ ^/ ]]; then
                    # Relativer Pfad - mache absolut relativ zum Script-Verzeichnis
                    CONFIG_FILE="${SCRIPT_DIR}/${CONFIG_FILE}"
                fi
            else
                echo "Fehler: Unbekannter Parameter: $1" >&2
                echo "Verwenden Sie -h oder --help für Hilfe" >&2
                exit 1
            fi
            ;;
    esac
    shift
done

# Standard-Konfiguration verwenden, wenn keine angegeben
if [[ -z "${CONFIG_FILE}" ]]; then
    CONFIG_FILE="${DEFAULT_CONFIG_FILE}"
fi

# Produktionsumgebung erkennen
# In Produktion: Anwendung in /data/appl/mcc/mcc-web, Daten in /data/var/mcc
if [[ "${SCRIPT_DIR}" == *"/data/appl/mcc/mcc-web"* ]] || [[ -d "/data/appl/mcc/mcc-web" ]]; then
    # Produktionsumgebung
    BACKUP_SOURCE_BASE="/data/var/mcc"
else
    # Entwicklungsumgebung (Fallback)
    BACKUP_SOURCE_BASE="/data/var/mcc"
fi

# Standard-Konfiguration
BACKUP_DB_PATH="${BACKUP_SOURCE_BASE}/db/db.sqlite3"
BACKUP_MEDIA_PATH="${BACKUP_SOURCE_BASE}/media"
BACKUP_LOCAL_DIR="${BACKUP_SOURCE_BASE}/backups"
BACKUP_RETENTION_DAYS=30

# SSH-Konfiguration (wird aus Config-Datei geladen)
SSH_HOST=""
SSH_USER=""
SSH_PORT="22"
REMOTE_BACKUP_DIR=""
SSH_KEY=""

# Logging
LOG_DIR="${BACKUP_SOURCE_BASE}/logs"
LOG_FILE="${LOG_DIR}/backup_$(date +%Y%m%d).log"
MAX_LOG_AGE_DAYS=90

# Funktionen
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_line="[${timestamp}] [${level}] ${message}"
    # Schreibe in Log-Datei
    echo "${log_line}" >> "${LOG_FILE}"
    # Schreibe auf stderr (nicht stdout, damit es nicht in Variablen übernommen wird)
    echo "${log_line}" >&2
}

log_info() {
    log "INFO" "$@"
    echo -e "${GREEN}[INFO]${NC} $*" >&2
}

log_warn() {
    log "WARN" "$@"
    echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Konfigurationsdatei laden
load_config() {
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        log_error "Konfigurationsdatei nicht gefunden: ${CONFIG_FILE}"
        log_error "Bitte erstellen Sie die Datei basierend auf backup_mcc.conf.example"
        log_error "Oder geben Sie eine gültige Konfigurationsdatei als Parameter an:"
        log_error "  $0 /path/to/backup_mcc.conf"
        log_error "Verwenden Sie -h oder --help für weitere Informationen"
        exit 1
    fi
    
    log_info "Verwende Konfigurationsdatei: ${CONFIG_FILE}"

    # Konfiguration einlesen
    source "${CONFIG_FILE}"

    # Pflichtfelder prüfen
    if [[ -z "${SSH_HOST:-}" ]]; then
        log_error "SSH_HOST nicht in Konfiguration definiert"
        exit 1
    fi
    if [[ -z "${SSH_USER:-}" ]]; then
        log_error "SSH_USER nicht in Konfiguration definiert"
        exit 1
    fi
    if [[ -z "${REMOTE_BACKUP_DIR:-}" ]]; then
        log_error "REMOTE_BACKUP_DIR nicht in Konfiguration definiert"
        exit 1
    fi

    log_info "Konfiguration geladen: ${SSH_USER}@${SSH_HOST}:${SSH_PORT} -> ${REMOTE_BACKUP_DIR}"
}

# Verzeichnisse erstellen
setup_directories() {
    mkdir -p "${LOG_DIR}"
    mkdir -p "${BACKUP_LOCAL_DIR}"
}

# Alte Logs aufräumen
cleanup_old_logs() {
    if [[ -d "${LOG_DIR}" ]]; then
        find "${LOG_DIR}" -name "backup_*.log" -type f -mtime +${MAX_LOG_AGE_DAYS} -delete 2>/dev/null || true
    fi
}

# Datenbank-Backup erstellen
backup_database() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_filename="db_backup_${timestamp}.sqlite3"
    local backup_path="${BACKUP_LOCAL_DIR}/${backup_filename}"

    log_info "Starte Datenbank-Backup..."

    if [[ ! -f "${BACKUP_DB_PATH}" ]]; then
        log_warn "Datenbankdatei nicht gefunden: ${BACKUP_DB_PATH}"
        return 1
    fi

    # Datenbank kopieren
    if cp "${BACKUP_DB_PATH}" "${backup_path}"; then
        log_info "Datenbank-Backup erstellt: ${backup_path}"
        
        # WAL und SHM Dateien auch kopieren falls vorhanden
        local wal_path="${BACKUP_DB_PATH}-wal"
        local shm_path="${BACKUP_DB_PATH}-shm"
        
        if [[ -f "${wal_path}" ]]; then
            cp "${wal_path}" "${backup_path}-wal"
            log_info "WAL-Datei kopiert: ${backup_path}-wal"
        fi
        
        if [[ -f "${shm_path}" ]]; then
            cp "${shm_path}" "${backup_path}-shm"
            log_info "SHM-Datei kopiert: ${backup_path}-shm"
        fi
        
        # Nur den Pfad auf stdout ausgeben (ohne Zeilenumbrüche)
        printf "%s" "${backup_path}"
        return 0
    else
        log_error "Fehler beim Erstellen des Datenbank-Backups"
        return 1
    fi
}

# Alte lokale Backups aufräumen
cleanup_old_backups() {
    log_info "Räume alte Backups auf (älter als ${BACKUP_RETENTION_DAYS} Tage)..."
    
    if [[ -d "${BACKUP_LOCAL_DIR}" ]]; then
        local deleted_count=$(find "${BACKUP_LOCAL_DIR}" -name "db_backup_*.sqlite3*" -type f -mtime +${BACKUP_RETENTION_DAYS} -delete -print 2>/dev/null | wc -l)
        if [[ ${deleted_count} -gt 0 ]]; then
            log_info "${deleted_count} alte Backup-Dateien gelöscht"
        fi
    fi
}

# rsync über SSH ausführen
sync_to_remote() {
    local source_path="$1"
    local remote_path="$2"
    local description="$3"
    
    log_info "Synchronisiere ${description}..."

    # SSH-Verbindung testen
    local ssh_cmd="ssh -p ${SSH_PORT} ${SSH_KEY:+-i ${SSH_KEY}} -o StrictHostKeyChecking=no -o ConnectTimeout=10"
    local remote_dir=$(dirname "${remote_path}")
    
    # Remote-Verzeichnis erstellen falls nicht vorhanden
    if ! ${ssh_cmd} "${SSH_USER}@${SSH_HOST}" "mkdir -p ${remote_dir}" 2>/dev/null; then
        log_error "SSH-Verbindung fehlgeschlagen oder Zielverzeichnis konnte nicht erstellt werden"
        return 1
    fi

    # rsync Optionen (ohne --delete für einzelne Dateien)
    local rsync_opts=(
        -avz
        --progress
        -e "ssh -p ${SSH_PORT} ${SSH_KEY:+-i ${SSH_KEY}} -o StrictHostKeyChecking=no"
    )

    # rsync ausführen
    if rsync "${rsync_opts[@]}" "${source_path}" "${SSH_USER}@${SSH_HOST}:${remote_path}"; then
        log_info "${description} erfolgreich synchronisiert"
        return 0
    else
        log_error "Fehler beim Synchronisieren von ${description}"
        return 1
    fi
}

# Media-Verzeichnis synchronisieren (ohne Logfiles)
sync_media() {
    if [[ ! -d "${BACKUP_MEDIA_PATH}" ]]; then
        log_warn "Media-Verzeichnis nicht gefunden: ${BACKUP_MEDIA_PATH}"
        return 1
    fi

    local remote_media_path="${REMOTE_BACKUP_DIR}/media"
    
    # rsync mit Excludes für Logfiles und Log-Verzeichnisse
    # WICHTIG: Logs werden nicht gesichert, da eine Log-Rotation konfiguriert ist
    local rsync_opts=(
        -avz
        --delete
        --progress
        --exclude='*.log'
        --exclude='*.log.*'
        --exclude='*.log.[0-9]*'
        --exclude='logs/'
        --exclude='**/logs/'
        --exclude='**/logs/**'
        --exclude='*.tmp'
        --exclude='*.temp'
        -e "ssh -p ${SSH_PORT} ${SSH_KEY:+-i ${SSH_KEY}} -o StrictHostKeyChecking=no"
    )

    log_info "Synchronisiere Media-Verzeichnis (ohne Logfiles - Log-Rotation ist konfiguriert)..."

    if rsync "${rsync_opts[@]}" "${BACKUP_MEDIA_PATH}/" "${SSH_USER}@${SSH_HOST}:${remote_media_path}/"; then
        log_info "Media-Verzeichnis erfolgreich synchronisiert"
        return 0
    else
        log_error "Fehler beim Synchronisieren des Media-Verzeichnisses"
        return 1
    fi
}

# Hauptfunktion
main() {
    local start_time=$(date +%s)
    log_info "=== MyCyclingCity Backup gestartet ==="
    log_info "HINWEIS: Log-Verzeichnis (/data/var/mcc/logs) wird NICHT gesichert - Log-Rotation ist konfiguriert"
    
    # Konfiguration laden
    load_config
    
    # Verzeichnisse erstellen
    setup_directories
    
    # Alte Logs aufräumen
    # HINWEIS: Das gesamte logs-Verzeichnis (/data/var/mcc/logs) wird NICHT gesichert,
    # da eine Log-Rotation (logrotate) konfiguriert ist
    cleanup_old_logs
    
    # Datenbank-Backup erstellen
    local db_backup_path
    # backup_database() gibt nur den Pfad auf stdout aus, Logs gehen auf stderr
    if db_backup_path=$(backup_database); then
        # Entferne eventuelle Leerzeichen/Zeilenumbrüche am Ende
        db_backup_path=$(echo "${db_backup_path}" | tr -d '\n\r' | xargs)
        
        # Datenbank-Backup zum Remote-Server kopieren
        local remote_db_backup_path="${REMOTE_BACKUP_DIR}/backups/$(basename "${db_backup_path}")"
        sync_to_remote "${db_backup_path}" "${remote_db_backup_path}" "Datenbank-Backup"
        
        # WAL und SHM Dateien auch kopieren falls vorhanden
        for ext in "-wal" "-shm"; do
            local local_file="${db_backup_path}${ext}"
            if [[ -f "${local_file}" ]]; then
                sync_to_remote "${local_file}" "${remote_db_backup_path}${ext}" "Datenbank-Backup${ext}"
            fi
        done
    else
        log_warn "Datenbank-Backup übersprungen"
    fi
    
    # Media-Verzeichnis synchronisieren
    sync_media
    
    # Alte lokale Backups aufräumen
    cleanup_old_backups
    
    # Zusammenfassung
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log_info "=== Backup abgeschlossen (Dauer: ${duration}s) ==="
}

# Script ausführen
main "$@"
