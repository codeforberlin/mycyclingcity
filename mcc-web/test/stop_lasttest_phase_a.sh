#!/usr/bin/env bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Stop Phase A load test processes started by run_lasttest_phase_a.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="${SCRIPT_DIR}/.lasttest_phase_a"

if [[ ! -d "${PID_DIR}" ]]; then
  echo "No Phase A PID dir (${PID_DIR}). Nothing to stop."
  exit 0
fi

stopped=0
for pid_file in "${PID_DIR}"/*.pid; do
  [[ -e "${pid_file}" ]] || continue
  pid="$(cat "${pid_file}")"
  name="$(basename "${pid_file}" .pid)"
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    # Allow graceful exit; force if needed
    for _ in 1 2 3 4 5; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.4
    done
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
    echo "Stopped ${name} (pid ${pid})"
    stopped=$((stopped + 1))
  else
    echo "Already dead: ${name} (pid ${pid})"
  fi
  rm -f "${pid_file}"
done

echo "Stopped ${stopped} process(es)."
