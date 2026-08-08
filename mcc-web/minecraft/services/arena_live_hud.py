# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    arena_live_hud.py
# @note    ArenaLive sidebar for spectators (Bridge-Worker, reads arena JSON state).

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from config.logger_utils import get_logger
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services import rcon_client
from minecraft.services.arena_motion import state as race_state
from minecraft.services.arena_motion.race_modes import (
    MODE_VELOS,
    live_hud_show_velos,
    normalize_race_mode,
    uses_laps,
    uses_time_limit,
)
from minecraft.services.sidebar_visibility import (
    arena_live_sidebar_slot,
    clear_arena_live_display,
    ensure_sidebar_routing_teams,
)

logger = get_logger("minecraft")

_SCORE_HEADER = 1100
_SCORE_LINE_BASE = 1000
_SCORE_LINE_STEP = 100

# Fixed-width columns; NBSP in scoreboard names (RCON breaks on ASCII spaces).
_NAME_COL_WIDTH = 10
_COL_VELOS_WIDTH = 5
_COL_SPEED_WIDTH = 8
_COL_LAPS_WIDTH = 5
_COL_TIME_WIDTH = 7
_SCOREBOARD_NAME_MAX = 40

_last_snapshot: LiveHudSnapshot | None = None
_last_applied_at: float = 0.0
_display_active: bool = False


def live_hud_enabled() -> bool:
    if not bool(getattr(settings, "MCC_MINECRAFT_ARENA_LIVE_HUD_ENABLED", True)):
        return False
    try:
        return bool(MinecraftIntegrationConfig.get_config().sidebar_enabled)
    except Exception:
        return True


def live_objective_name() -> str:
    return (
        getattr(settings, "MCC_MINECRAFT_ARENA_LIVE_OBJECTIVE", None) or "ArenaLive"
    ).strip() or "ArenaLive"


def live_hud_min_interval_seconds() -> float:
    return max(0.25, float(getattr(settings, "MCC_MINECRAFT_ARENA_LIVE_HUD_INTERVAL_S", 1.0)))


def live_hud_poll_seconds() -> float:
    return max(0.1, float(getattr(settings, "MCC_MINECRAFT_ARENA_LIVE_HUD_POLL_S", 0.5)))


def _mode_letter(race_mode: str) -> str:
    """R = Runden/Doppel, V = Velo-Rennen (sidebar header)."""
    return "V" if normalize_race_mode(race_mode) == MODE_VELOS else "R"


def _format_remaining_mmss(remaining_s: int) -> str:
    remaining = max(0, int(remaining_s))
    minutes, seconds = divmod(remaining, 60)
    return f"{minutes}:{seconds:02d}"


def live_hud_header(
    race_mode: str,
    *,
    frozen: bool,
    remaining_s: int | None = None,
) -> str:
    letter = _mode_letter(race_mode)
    if frozen:
        return f"- {letter} ERGEBNIS -"
    if normalize_race_mode(race_mode) == MODE_VELOS:
        if remaining_s is not None:
            return f"- {letter} {_format_remaining_mmss(remaining_s)} -"
        return f"- {letter} VELOS -"
    return f"- {letter} LIVE -"


@dataclass(frozen=True)
class LiveHudSnapshot:
    """Normalized sidebar rows — skip RCON when unchanged."""

    header: str
    rows: tuple[tuple[str, int], ...]
    signature: tuple[Any, ...]


def _lane_slot_map(assignments: list[dict[str, Any]]) -> dict[str, int]:
    ordered = sorted(
        (a for a in assignments if a.get("lane_id")),
        key=lambda item: str(item.get("lane_id")),
    )
    return {str(item["lane_id"]): index + 1 for index, item in enumerate(ordered)}


def _scoreboard_holder(text: str) -> str:
    """Fake-player name: spaces → NBSP so RCON sends one token."""
    normalized = (text or "").replace("\u00a0", " ")
    safe = normalized.replace(" ", "\u00a0").replace('"', "").replace("\\", "")
    return safe[:_SCOREBOARD_NAME_MAX]


def _pad_left(text: str, width: int) -> str:
    """Right-align text in a fixed-width column."""
    clipped = (text or "")[:width]
    return (" " * max(0, width - len(clipped))) + clipped


def _format_name_column(place: int, cyclist: str) -> str:
    name = f"{place}. {cyclist}"
    clipped = name[:_NAME_COL_WIDTH]
    return clipped + (" " * max(0, _NAME_COL_WIDTH - len(clipped)))


def _laps_display(entry: dict[str, Any], *, target_laps: int) -> str | None:
    if target_laps < 1:
        return None
    if entry.get("finished"):
        done = target_laps
    else:
        lap = max(1, int(entry.get("lap") or 1))
        done = max(0, lap - 1)
    return f"{done}/{target_laps}"


def _append_time_and_velos_cols(
    metric_cols: list[str],
    *,
    race_mode: str,
    entry: dict[str, Any],
    frozen: bool,
    finish_s: float,
) -> None:
    """Laps/dual: time then Velos; velos mode: Velos then time."""
    time_col = _pad_left(f"{max(0.0, float(finish_s)):.1f}s", _COL_TIME_WIDTH)
    if live_hud_show_velos(race_mode, entry=entry, frozen=frozen):
        velos_col = _pad_left(f"{int(entry['velos'])}V", _COL_VELOS_WIDTH)
        if uses_time_limit(race_mode):
            metric_cols.extend([velos_col, time_col])
        else:
            metric_cols.extend([time_col, velos_col])
    else:
        metric_cols.append(time_col)


def _format_sidebar_line(
    entry: dict[str, Any],
    *,
    race_mode: str,
    target_laps: int,
    lane_slot: int,
    frozen: bool,
) -> str:
    """Sidebar row: name (left), metrics in right-aligned fixed-width columns."""
    del lane_slot  # lane id kept in state/signature only — not shown in HUD
    place = max(1, int(entry.get("place") or 1))
    cyclist = str(entry.get("cyclist") or "?").strip() or "?"
    name_col = _format_name_column(place, cyclist)

    finish_s = entry.get("finish_time_s")
    if entry.get("finished") and finish_s is not None:
        metric_cols: list[str] = []
        _append_time_and_velos_cols(
            metric_cols,
            race_mode=race_mode,
            entry=entry,
            frozen=frozen,
            finish_s=float(finish_s),
        )
        return name_col + "".join(metric_cols)

    metric_cols = []
    if live_hud_show_velos(race_mode, entry=entry, frozen=frozen):
        metric_cols.append(_pad_left(f"{int(entry['velos'])}V", _COL_VELOS_WIDTH))
    speed = entry.get("speed_kmh")
    if speed is not None and float(speed) > 0.0:
        metric_cols.append(
            _pad_left(f"{int(round(float(speed)))} km/h", _COL_SPEED_WIDTH)
        )
    if uses_laps(race_mode):
        laps = _laps_display(entry, target_laps=target_laps)
        if laps:
            metric_cols.append(_pad_left(laps, _COL_LAPS_WIDTH))

    if not metric_cols:
        return name_col.rstrip()
    return name_col + "".join(metric_cols)


def _entry_signature(
    entry: dict[str, Any],
    *,
    race_mode: str,
    target_laps: int,
    lane_slot: int,
    frozen: bool,
) -> tuple[Any, ...]:
    finish_s = entry.get("finish_time_s")
    finish_disp = round(float(finish_s), 1) if finish_s is not None else None
    velos = int(entry["velos"]) if live_hud_show_velos(race_mode, entry=entry, frozen=frozen) else None
    laps = _laps_display(entry, target_laps=target_laps) if uses_laps(race_mode) else None
    speed = entry.get("speed_kmh")
    speed_disp = int(round(float(speed))) if speed is not None else None
    distance_disp = int(entry["distance_m"]) if entry.get("distance_m") is not None else None
    return (
        str(entry.get("lane_id") or lane_slot),
        int(entry.get("place") or 1),
        bool(entry.get("finished")),
        finish_disp,
        laps,
        velos,
        speed_disp,
        distance_disp,
        lane_slot,
    )


def _velos_sort_key(entry: dict[str, Any]) -> tuple[int, int, int]:
    return (
        -int(entry.get("velos") or 0),
        -int(entry.get("distance_m") or 0),
        int(entry.get("place") or 99),
    )


def build_live_hud_snapshot(state: dict[str, Any]) -> LiveHudSnapshot | None:
    live = state.get("live") or {}
    if not isinstance(live, dict) or not live:
        return None

    race_mode = normalize_race_mode(state.get("race_mode"))
    target_laps = max(1, int(state.get("target_laps") or 1))
    frozen = state.get("status") != race_state.STATUS_RUNNING
    remaining_s: int | None = None
    if not frozen and uses_time_limit(race_mode):
        # Prefer per-lane remaining from publish; fall back to state top-level.
        for entry in live.values():
            if isinstance(entry, dict) and entry.get("remaining_s") is not None:
                remaining_s = max(0, int(entry["remaining_s"]))
                break
        if remaining_s is None and state.get("remaining_s") is not None:
            remaining_s = max(0, int(state["remaining_s"]))
    header = live_hud_header(race_mode, frozen=frozen, remaining_s=remaining_s)

    slots = _lane_slot_map(state.get("assignments") or [])
    items: list[tuple[dict[str, Any], int, tuple[Any, ...]]] = []
    for lane_id, entry in live.items():
        if not isinstance(entry, dict):
            continue
        slot = slots.get(str(lane_id), 0)
        if slot <= 0:
            continue
        entry_with_lane = dict(entry)
        entry_with_lane["lane_id"] = str(lane_id)
        items.append(
            (
                entry_with_lane,
                slot,
                _entry_signature(
                    entry_with_lane,
                    race_mode=race_mode,
                    target_laps=target_laps,
                    lane_slot=slot,
                    frozen=frozen,
                ),
            )
        )

    if not items:
        return None

    if race_mode == MODE_VELOS:
        items.sort(key=lambda item: _velos_sort_key(item[0]))
    else:
        items.sort(key=lambda item: int(item[0].get("place") or 99))

    rows: list[tuple[str, int, int]] = []
    signatures: list[tuple[Any, ...]] = []
    for display_rank, (entry_with_lane, slot, signature) in enumerate(items, start=1):
        entry_for_line = dict(entry_with_lane)
        if race_mode == MODE_VELOS:
            entry_for_line["place"] = display_rank
        line = _format_sidebar_line(
            entry_for_line,
            race_mode=race_mode,
            target_laps=target_laps,
            lane_slot=slot,
            frozen=frozen,
        )
        sort_place = (
            display_rank
            if race_mode == MODE_VELOS
            else max(1, int(entry_with_lane.get("place") or 1))
        )
        rows.append((line, sort_place, slot))
        signatures.append(signature)

    scored = tuple(
        (line, _SCORE_LINE_BASE - (index * _SCORE_LINE_STEP))
        for index, (line, _place, _slot) in enumerate(rows)
    )
    return LiveHudSnapshot(
        header=header,
        rows=scored,
        signature=(header, tuple(signatures)),
    )


def _should_throttle(
    previous: LiveHudSnapshot | None,
    current: LiveHudSnapshot,
    *,
    elapsed: float,
) -> bool:
    if previous is None:
        return False
    if previous.signature != current.signature:
        return False
    return elapsed < live_hud_min_interval_seconds()


def build_live_hud_commands(snapshot: LiveHudSnapshot) -> list[str]:
    objective = live_objective_name()
    header = snapshot.header.replace('"', '\\"')
    commands = [
        f"scoreboard players reset * {objective}",
        f'scoreboard objectives modify {objective} displayname "{header}"',
        f"scoreboard objectives modify {objective} numberformat blank",
    ]
    for index, (line_text, score) in enumerate(snapshot.rows):
        commands.append(
            f"scoreboard players set {_scoreboard_holder(line_text)} {objective} {int(score)}"
        )
    slot = arena_live_sidebar_slot()
    commands.append(f"scoreboard objectives setdisplay {slot} {objective}")
    return commands


def clear_live_hud_commands() -> list[str]:
    objective = live_objective_name()
    return [
        f"scoreboard players reset * {objective}",
        f"scoreboard objectives setdisplay {arena_live_sidebar_slot()}",
    ]


def should_clear_live_hud(state: dict[str, Any]) -> bool:
    live = state.get("live") or {}
    return not bool(live)


def bridge_poll_interval_seconds(default_timeout: float) -> float:
    """Shorter bridge wait while a race is running (faster sidebar refresh)."""
    if not live_hud_enabled():
        return default_timeout
    try:
        state = race_state.load_state()
    except Exception:
        return default_timeout
    if state.get("status") == race_state.STATUS_RUNNING:
        return min(default_timeout, live_hud_poll_seconds())
    return default_timeout


def sync_arena_live_hud(*, force: bool = False) -> bool:
    """
    Push ArenaLive sidebar from arena JSON state.

    Returns True when RCON commands were sent (apply or clear).
    """
    global _last_snapshot, _last_applied_at, _display_active

    if not live_hud_enabled():
        return False

    state = race_state.load_state()

    if should_clear_live_hud(state):
        if not _display_active and _last_snapshot is None:
            return False
        try:
            ensure_sidebar_routing_teams()
            clear_arena_live_display(live_objective_name())
            _last_snapshot = None
            _display_active = False
            _last_applied_at = time.monotonic()
            logger.info("[arena_live_hud] cleared sidebar objective=%s", live_objective_name())
            return True
        except Exception as exc:
            logger.warning("[arena_live_hud] clear failed: %s", exc)
            return False

    snapshot = build_live_hud_snapshot(state)
    if snapshot is None:
        return False

    now = time.monotonic()
    if not force and snapshot == _last_snapshot:
        return False
    if not force and _should_throttle(_last_snapshot, snapshot, elapsed=now - _last_applied_at):
        return False

    try:
        ensure_sidebar_routing_teams()
        rcon_client.ensure_objective(live_objective_name(), snapshot.header)
        ok, log = rcon_client.run_commands(build_live_hud_commands(snapshot), stop_on_error=True)
        if not ok:
            logger.warning("[arena_live_hud] apply failed:\n%s", log)
            return False
        _last_snapshot = snapshot
        _display_active = True
        _last_applied_at = now
        logger.debug(
            "[arena_live_hud] updated rows=%s frozen=%s",
            len(snapshot.rows),
            state.get("status") != race_state.STATUS_RUNNING,
        )
        return True
    except Exception as exc:
        logger.warning("[arena_live_hud] sync failed: %s", exc)
        return False


def reset_live_hud_cache() -> None:
    """Test helper — drop throttling/snapshot between cases."""
    global _last_snapshot, _last_applied_at, _display_active
    _last_snapshot = None
    _last_applied_at = 0.0
    _display_active = False
