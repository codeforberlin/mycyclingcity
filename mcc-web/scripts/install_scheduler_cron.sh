#!/bin/bash
#
# Installiert den MCC Scheduler-Cron (einziger OS-Tick für alle ScheduledJob-Einträge).
# Optional: entfernt alte Einzel-Cron-Einträge für mcc_worker / backup_*.sh
#
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Production defaults; override via env
VENV_PYTHON="${VENV_PYTHON:-/data/appl/mcc/venv/bin/python}"
LOG_FILE="${LOG_FILE:-/data/var/mcc/logs/mcc_scheduler.log}"
REMOVE_LEGACY="${REMOVE_LEGACY:-1}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    # Fallback: project-local venv
    if [[ -x "${PROJECT_DIR}/venv/bin/python" ]]; then
        VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"
    else
        echo "Fehler: Python nicht gefunden (${VENV_PYTHON})"
        exit 1
    fi
fi

mkdir -p "$(dirname "${LOG_FILE}")"

CRON_ENTRY="* * * * * cd ${PROJECT_DIR} && ${VENV_PYTHON} manage.py run_scheduler >> ${LOG_FILE} 2>&1"

CURRENT="$(crontab -l 2>/dev/null || true)"

if [[ "${REMOVE_LEGACY}" == "1" ]]; then
    CURRENT="$(printf '%s\n' "${CURRENT}" \
        | grep -vF 'manage.py mcc_worker' \
        | grep -vF 'backup_mcc.sh' \
        | grep -vF 'backup_minecraft_world.sh' \
        | grep -vF 'manage.py run_scheduler' \
        || true)"
else
    CURRENT="$(printf '%s\n' "${CURRENT}" | grep -vF 'manage.py run_scheduler' || true)"
fi

{
    printf '%s\n' "${CURRENT}"
    echo "${CRON_ENTRY}"
} | sed '/^$/d' | crontab -

echo "Scheduler-Cron installiert:"
echo "  ${CRON_ENTRY}"
echo ""
echo "Jobs werden in Django Admin unter „Geplante Jobs“ verwaltet."
echo "Legacy-Einträge entfernt: REMOVE_LEGACY=${REMOVE_LEGACY}"
echo ""
echo "Aktuelle crontab (Auszug):"
crontab -l | grep -E 'run_scheduler|mcc_worker|backup_' || crontab -l
