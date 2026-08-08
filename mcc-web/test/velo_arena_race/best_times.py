# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    best_times.py
# @note    Local TOP-3 finish times for VeloArena (JSON file, no Django DB).

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BestTimeEntry:
    """One recorded finish time (total race time in seconds)."""

    cyclist: str
    time_s: float
    laps: int
    recorded_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BestTimeEntry":
        return cls(
            cyclist=str(data.get("cyclist") or "?"),
            time_s=float(data.get("time_s") or 0.0),
            laps=int(data.get("laps") or 0),
            recorded_at=str(data.get("recorded_at") or ""),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_best_times(path: Path) -> list[BestTimeEntry]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries_raw = raw.get("top") if isinstance(raw, dict) else raw
    if not isinstance(entries_raw, list):
        return []
    entries = [BestTimeEntry.from_dict(item) for item in entries_raw if isinstance(item, dict)]
    return sorted(entries, key=lambda e: e.time_s)[:3]


def save_best_times(path: Path, entries: list[BestTimeEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "top": [e.to_dict() for e in sorted(entries, key=lambda e: e.time_s)[:3]],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_race_results(
    existing: list[BestTimeEntry],
    *,
    results: list[tuple[str, float, int]],
    keep: int = 3,
) -> tuple[list[BestTimeEntry], list[BestTimeEntry]]:
    """
    Merge new race finish times into the TOP list (lowest time wins).

    results: list of (cyclist, time_s, laps)
    Returns (new_top, newly_entered_or_improved).
    """
    combined = list(existing)
    improved: list[BestTimeEntry] = []
    for cyclist, time_s, laps in results:
        if time_s <= 0:
            continue
        name = (cyclist or "?").strip() or "?"
        entry = BestTimeEntry(
            cyclist=name,
            time_s=float(time_s),
            laps=int(laps),
            recorded_at=_now_iso(),
        )
        # Keep best time per cyclist name (case-insensitive), then global top N.
        others = [e for e in combined if e.cyclist.lower() != name.lower()]
        prev = next((e for e in combined if e.cyclist.lower() == name.lower()), None)
        if prev is None or entry.time_s < prev.time_s:
            combined = others + [entry]
            improved.append(entry)
        else:
            combined = others + [prev]

    top = sorted(combined, key=lambda e: e.time_s)[:keep]
    # Only report improvements that made the final top board.
    top_names = {e.cyclist.lower() for e in top}
    newly_on_board = [e for e in improved if e.cyclist.lower() in top_names]
    return top, newly_on_board
