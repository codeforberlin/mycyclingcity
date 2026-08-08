# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    state.py
# @note    Shared JSON control/live state between Operator-GUI and motion worker.

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from django.conf import settings

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_STOPPING = "stopping"

VALID_STATUSES = frozenset({STATUS_IDLE, STATUS_RUNNING, STATUS_STOPPING})


def state_path() -> Path:
    configured = getattr(settings, "MCC_MINECRAFT_ARENA_STATE_PATH", "") or ""
    if configured:
        return Path(configured)
    data_dir = Path(getattr(settings, "DATA_DIR", Path(".")))
    return data_dir / "tmp" / "arena_race_state.json"


def _lock_path() -> Path:
    path = state_path()
    return path.with_name(path.name + ".lock")


@contextmanager
def _state_lock() -> Iterator[None]:
    """
    Exclusive lock for read-modify-write updates.

    Without this, the motion worker heartbeat can overwrite operator fields
    (e.g. continue_after_finish) that were saved concurrently.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_path()
    with open(lock_file, "a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def default_state() -> dict[str, Any]:
    from minecraft.services.arena_motion.race_modes import (
        default_race_mode,
        default_target_laps,
        default_time_limit_seconds,
    )

    return {
        "status": STATUS_IDLE,
        "race_mode": default_race_mode(),
        "target_laps": default_target_laps(),
        "time_limit_seconds": default_time_limit_seconds(),
        "continue_after_finish": False,
        "sim_distance": False,
        "api_live_pulse": False,
        "kill_all_on_reset": False,
        "initialized": False,
        "assignments": [],
        "pending_command": None,
        "last_error": "",
        "worker_heartbeat": None,
        "worker_pid": None,
        "live": {},
        "result": {},
        "updated_at": time.time(),
    }


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()
    base = default_state()
    base.update(data if isinstance(data, dict) else {})
    if base.get("status") not in VALID_STATUSES:
        base["status"] = STATUS_IDLE
    if not isinstance(base.get("assignments"), list):
        base["assignments"] = []
    if not isinstance(base.get("live"), dict):
        base["live"] = {}
    if not isinstance(base.get("result"), dict):
        base["result"] = {}
    from minecraft.services.arena_motion.race_modes import normalize_race_mode

    base["race_mode"] = normalize_race_mode(base.get("race_mode"))
    base["continue_after_finish"] = bool(base.get("continue_after_finish", False))
    return base


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["updated_at"] = time.time()
    raw = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix="arena_state_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def update_state(**kwargs: Any) -> dict[str, Any]:
    with _state_lock():
        state = load_state()
        state.update(kwargs)
        save_state(state)
        return state
