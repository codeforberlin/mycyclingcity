#!/usr/bin/env bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Start Phase A load test: 4 fixed device/cyclist pairs, one process each, interval 10s.
#
# Usage:
#   ./run_lasttest_phase_a.sh
#   ./run_lasttest_phase_a.sh --dry-run
#   MCC_WEB_ROOT=/data/appl/mcc/mcc-web ./run_lasttest_phase_a.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_FILE="${SCRIPT_DIR}/lasttest_4raeder.json"
PID_DIR="${SCRIPT_DIR}/.lasttest_phase_a"
LOG_DIR="${PID_DIR}/logs"
VENV_PYTHON="${MCC_VENV_PYTHON:-/data/appl/mcc/venv/bin/python3}"
WEB_ROOT="${MCC_WEB_ROOT:-/data/appl/mcc/mcc-web}"
INTERVAL="${LASTTEST_INTERVAL:-5}"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "ERROR: Python not found/executable: ${VENV_PYTHON}" >&2
  exit 1
fi

if [[ ! -f "${JSON_FILE}" ]]; then
  echo "ERROR: missing ${JSON_FILE}" >&2
  exit 1
fi

if [[ -d "${PID_DIR}" ]] && compgen -G "${PID_DIR}/*.pid" > /dev/null; then
  echo "ERROR: Phase A already running (PIDs in ${PID_DIR}). Stop with stop_lasttest_phase_a.sh first." >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

# Load API key from Django settings without printing it.
if [[ -z "${MCC_APP_API_KEY:-}" ]]; then
  export MCC_APP_API_KEY
  MCC_APP_API_KEY="$(
    cd "${WEB_ROOT}"
    "${VENV_PYTHON}" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
key = getattr(settings, "MCC_APP_API_KEY", None) or ""
if not key:
    raise SystemExit("MCC_APP_API_KEY empty in Django settings")
print(key, end="")
PY
  )"
fi

mapfile -t PAIRS < <(
  "${VENV_PYTHON}" - <<PY
import json
from pathlib import Path
data = json.loads(Path("${JSON_FILE}").read_text(encoding="utf-8"))
for p in data["pairs"]:
    print(f"{p['device_id']}|{p['id_tag']}|{p['wheel_size']}")
PY
)

echo "=== Phase A start ==="
echo "Target: cfg in ${SCRIPT_DIR}/mcc_api_test.cfg (expect 127.0.0.1:8001)"
echo "Interval: ${INTERVAL}s"
echo "Pairs: ${#PAIRS[@]}"

for pair in "${PAIRS[@]}"; do
  IFS='|' read -r device id_tag wheel <<< "${pair}"
  log_file="${LOG_DIR}/${device}.log"
  pid_file="${PID_DIR}/${device}.pid"
  cmd=(
    "${VENV_PYTHON}" "${SCRIPT_DIR}/mcc_api_test.py"
    --loop
    --interval "${INTERVAL}"
    --device "${device}"
    --id_tag "${id_tag}"
    --wheel-size "${wheel}"
    --config "${SCRIPT_DIR}/mcc_api_test.cfg"
  )
  echo "  ${device} ← ${id_tag} (wheel ${wheel} mm)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '    DRY-RUN:';
    printf '%q ' "${cmd[@]}"
    printf '\n'
    continue
  fi
  (
    cd "${SCRIPT_DIR}"
    # Unbuffered stdout so logs show sends immediately under nohup redirection
    PYTHONUNBUFFERED=1 nohup "${cmd[@]}" >"${log_file}" 2>&1 &
    echo $! >"${pid_file}"
  )
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Dry-run complete (nothing started)."
  exit 0
fi

echo "PIDs/logs: ${PID_DIR}"
echo "Stop with: ${SCRIPT_DIR}/stop_lasttest_phase_a.sh"
echo "Tail: tail -f ${LOG_DIR}/mcc-test-001.log"
