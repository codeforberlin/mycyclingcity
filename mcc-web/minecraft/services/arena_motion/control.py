# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    control.py
# @note    Operator-facing assign / start / stop / reset for arena motion.

from __future__ import annotations

from typing import Any

from minecraft.services.arena_motion.child_speed_guide import (
    child_speed_guide_for_wheel,
    default_sim_rate_mps,
    mps_to_kmh,
)
from minecraft.services.arena_motion.cyclists import resolve_device_motion_params
from minecraft.services.arena_motion.lanes import load_race_config
from minecraft.services.arena_motion.race_modes import (
    MODE_LABELS,
    VALID_RACE_MODES,
    default_race_mode,
    default_target_laps,
    default_time_limit_seconds,
    normalize_race_mode,
    time_limit_minutes_for_ui,
    uses_laps,
    uses_time_limit,
)
from minecraft.services.arena_motion import state as race_state


class ArenaControlError(Exception):
    """Invalid control request."""


def get_status() -> dict[str, Any]:
    config = load_race_config()
    st = race_state.load_state()
    lanes = [
        {
            "id": lane.id,
            "name": lane.name,
            "tag": lane.tag,
            "color": lane.color,
        }
        for lane in config.lanes
    ]
    assign_by_lane = {a.get("lane_id"): a for a in st.get("assignments", []) if a.get("lane_id")}
    lane_cards = []
    for lane in config.lanes:
        assignment = assign_by_lane.get(lane.id) or {}
        live = (st.get("live") or {}).get(lane.id) or {}
        wheel_mm = int(assignment.get("wheel_mm") or 0)
        guide = child_speed_guide_for_wheel(
            wheel_mm, fallback_mps=float(config.reference_mps)
        )
        sim_rate = float(
            assignment.get("sim_rate_mps", guide.default_mps)
        )
        lane_cards.append(
            {
                "id": lane.id,
                "name": lane.name,
                "tag": lane.tag,
                "color": lane.color,
                "cyclist": assignment.get("cyclist", ""),
                "device_name": assignment.get("device_name", ""),
                "device_display": assignment.get("device_display", ""),
                "wheel_mm": assignment.get("wheel_mm"),
                "device_factor": float(assignment.get("device_factor", 1.0)),
                "send_interval_seconds": float(
                    assignment.get("send_interval_seconds", 5.0)
                ),
                "sim_rate_mps": sim_rate,
                "sim_rate_kmh": mps_to_kmh(sim_rate),
                "speed_guide": guide.as_dict(),
                "live": live,
            }
        )
    return {
        "status": st.get("status", race_state.STATUS_IDLE),
        "race_mode": normalize_race_mode(st.get("race_mode")),
        "race_mode_label": MODE_LABELS.get(
            normalize_race_mode(st.get("race_mode")), MODE_LABELS[default_race_mode()]
        ),
        "race_modes": [
            {"id": mode_id, "label": label} for mode_id, label in MODE_LABELS.items()
        ],
        "target_laps": int(st.get("target_laps") or default_target_laps()),
        "time_limit_seconds": int(
            st.get("time_limit_seconds") or default_time_limit_seconds()
        ),
        "time_limit_minutes": time_limit_minutes_for_ui(
            st.get("time_limit_seconds") or default_time_limit_seconds()
        ),
        "uses_laps": uses_laps(st.get("race_mode")),
        "uses_time_limit": uses_time_limit(st.get("race_mode")),
        "continue_after_finish": bool(st.get("continue_after_finish", False)),
        "sim_distance": bool(st.get("sim_distance", False)),
        "api_live_pulse": bool(st.get("api_live_pulse", False)),
        "kill_all_on_reset": bool(st.get("kill_all_on_reset", False)),
        "pending_command": st.get("pending_command"),
        "last_error": st.get("last_error") or "",
        "worker_heartbeat": st.get("worker_heartbeat"),
        "worker_pid": st.get("worker_pid"),
        "config_path": str(config.config_path),
        "config_source": getattr(config, "source", "toml"),
        "reference_mps": float(config.reference_mps),
        "initialized": bool(st.get("initialized", False)),
        "lanes": lanes,
        "lane_cards": lane_cards,
        "assignments": st.get("assignments") or [],
        "result": st.get("result") or {},
    }


def set_assignments(raw_assignments: list[dict[str, Any]]) -> dict[str, Any]:
    config = load_race_config()
    cleaned: list[dict[str, Any]] = []
    used_lanes: set[str] = set()
    used_cyclists: set[str] = set()
    used_devices: set[str] = set()
    for entry in raw_assignments:
        lane_id = str(entry.get("lane_id") or "").strip()
        cyclist = str(entry.get("cyclist") or "").strip()
        device_name = str(entry.get("device_name") or entry.get("device") or "").strip()
        if not lane_id:
            continue
        if not cyclist:
            continue
        if not device_name:
            raise ArenaControlError(
                f"Bahn {lane_id}: IoT-Gerät fehlt (Radgröße/FKM kommen vom Gerät)."
            )
        lane = config.lane_by_key(lane_id)
        if lane is None:
            raise ArenaControlError(f"Unbekannte Bahn: {lane_id}")
        if lane.id.lower() in used_lanes:
            raise ArenaControlError(f"Bahn mehrfach: {lane.id}")
        if cyclist.lower() in used_cyclists:
            raise ArenaControlError(f"Radler mehrfach: {cyclist}")
        if device_name.lower() in used_devices:
            raise ArenaControlError(f"Gerät mehrfach: {device_name}")
        try:
            device_params = resolve_device_motion_params(device_name)
        except ValueError as exc:
            raise ArenaControlError(str(exc)) from exc
        used_lanes.add(lane.id.lower())
        used_cyclists.add(cyclist.lower())
        used_devices.add(device_name.lower())
        wheel_mm = int(device_params["wheel_mm"])
        cleaned.append(
            {
                "lane_id": lane.id,
                "cyclist": cyclist,
                "device_name": device_params["device_name"],
                "device_display": device_params["device_display"],
                "wheel_mm": wheel_mm,
                "device_factor": float(device_params["device_factor"]),
                "send_interval_seconds": float(
                    device_params.get("send_interval_seconds", 5.0)
                ),
                "sim_rate_mps": default_sim_rate_mps(
                    wheel_mm, fallback_mps=float(config.reference_mps)
                ),
            }
        )
    # New roster requires Init again before Start.
    return race_state.update_state(
        assignments=cleaned,
        initialized=False,
        last_error="",
    )


def assert_arena_sim_roster(assignments: list[dict[str, Any]] | None = None) -> None:
    """
    Ensure every assigned cyclist and device is flagged for arena simulation.

    Used by Arena-Simulation (internal/API) so productive riders/devices are not pulsed.
    """
    from api.models import Cyclist
    from iot.models import Device

    rows = list(assignments) if assignments is not None else list(
        (race_state.load_state().get("assignments") or [])
    )
    if not rows:
        raise ArenaControlError(
            "Keine Radler zugewiesen. Bitte zuerst in der Velo-Arena Radler + Gerät speichern."
        )
    for entry in rows:
        cyclist_key = str(entry.get("cyclist") or "").strip()
        device_name = str(entry.get("device_name") or "").strip()
        if not cyclist_key:
            continue
        cyclist = (
            Cyclist.objects.filter(user_id=cyclist_key).first()
            or Cyclist.objects.filter(id_tag=cyclist_key).first()
        )
        if cyclist is None:
            raise ArenaControlError(f"Unbekannter Radler: {cyclist_key}")
        if not cyclist.is_arena_sim_allowed:
            raise ArenaControlError(
                f"Radler „{cyclist.user_id}“ ist nicht für die Arena-Simulation freigegeben "
                f"(Admin: Häkchen „Arena-/API-Simulation erlaubt“)."
            )
        if not device_name:
            raise ArenaControlError(f"Bahn ohne Gerät für Radler „{cyclist.user_id}“.")
        device = Device.objects.filter(name=device_name).first()
        if device is None:
            raise ArenaControlError(f"Unbekanntes Gerät: {device_name}")
        if not device.is_arena_sim_allowed:
            raise ArenaControlError(
                f"Gerät „{device.name}“ ist nicht für die Arena-Simulation freigegeben "
                f"(Admin: Häkchen „Arena-/API-Simulation erlaubt“)."
            )


def set_target_laps(target_laps: int) -> dict[str, Any]:
    """Persist desired lap count (operator field; applied on next Start)."""
    laps = int(target_laps)
    if laps < 1:
        raise ArenaControlError("target_laps muss >= 1 sein")
    return race_state.update_state(target_laps=laps, last_error="")


def set_time_limit_seconds(time_limit_seconds: int) -> dict[str, Any]:
    """Persist Velo-race time limit in seconds (applied on next Start)."""
    seconds = int(time_limit_seconds)
    if seconds < 30:
        raise ArenaControlError("Zeitlimit muss mindestens 30 Sekunden sein")
    if seconds > 3600:
        raise ArenaControlError("Zeitlimit maximal 3600 Sekunden")
    return race_state.update_state(time_limit_seconds=seconds, last_error="")


def set_race_mode(race_mode: str) -> dict[str, Any]:
    """Persist race mode: laps | velos | dual."""
    mode = str(race_mode or "").strip().lower()
    if mode not in VALID_RACE_MODES:
        raise ArenaControlError(
            f"Unbekannter Rennmodus: {race_mode}. Erlaubt: {', '.join(sorted(VALID_RACE_MODES))}"
        )
    return race_state.update_state(race_mode=mode, last_error="")


def set_continue_after_finish(enabled: bool) -> dict[str, Any]:
    """
    When True, finishing (time/laps) still scores the race but does not hard-stop carts
    so riders can keep pedaling until the operator presses Stop.
    """
    return race_state.update_state(
        continue_after_finish=bool(enabled),
        last_error="",
    )


def request_start(
    *,
    target_laps: int | None = None,
    time_limit_seconds: int | None = None,
    race_mode: str | None = None,
    continue_after_finish: bool | None = None,
    sim_distance: bool | None = None,
    api_live_pulse: bool | None = None,
) -> dict[str, Any]:
    st = race_state.load_state()
    if not st.get("assignments"):
        raise ArenaControlError("Zuerst Radler und Gerät zuweisen, dann Init.")
    if not st.get("initialized"):
        raise ArenaControlError("Zuerst Init drücken (Loren auf die Schienen setzen).")
    if st.get("status") == race_state.STATUS_RUNNING:
        raise ArenaControlError("Rennen läuft bereits.")
    updates: dict[str, Any] = {
        "pending_command": "start",
        "last_error": "",
        "result": {},
    }
    if race_mode is not None:
        mode = str(race_mode or "").strip().lower()
        if mode not in VALID_RACE_MODES:
            raise ArenaControlError(f"Unbekannter Rennmodus: {race_mode}")
        updates["race_mode"] = mode
    effective_mode = normalize_race_mode(updates.get("race_mode", st.get("race_mode")))

    if target_laps is not None:
        if int(target_laps) < 1:
            raise ArenaControlError("target_laps muss >= 1 sein")
        updates["target_laps"] = int(target_laps)
    if time_limit_seconds is not None:
        seconds = int(time_limit_seconds)
        if seconds < 30:
            raise ArenaControlError("Zeitlimit muss mindestens 30 Sekunden sein")
        updates["time_limit_seconds"] = seconds
    if continue_after_finish is not None:
        updates["continue_after_finish"] = bool(continue_after_finish)

    if uses_laps(effective_mode) and "target_laps" not in updates:
        updates.setdefault(
            "target_laps", int(st.get("target_laps") or default_target_laps())
        )
    if uses_time_limit(effective_mode) and "time_limit_seconds" not in updates:
        updates.setdefault(
            "time_limit_seconds",
            int(st.get("time_limit_seconds") or default_time_limit_seconds()),
        )

    # XOR: internal sim_distance vs API-Live update-data pulse.
    if api_live_pulse:
        updates["api_live_pulse"] = True
        updates["sim_distance"] = False
    elif sim_distance is not None:
        updates["sim_distance"] = bool(sim_distance)
        if sim_distance:
            updates["api_live_pulse"] = False
        elif "api_live_pulse" not in updates:
            updates["api_live_pulse"] = False

    will_sim = bool(updates["sim_distance"]) if "sim_distance" in updates else bool(
        st.get("sim_distance")
    )
    will_api = bool(updates["api_live_pulse"]) if "api_live_pulse" in updates else bool(
        st.get("api_live_pulse")
    )
    if will_sim and will_api:
        raise ArenaControlError(
            "Interne Simulation und API-Live schließen sich aus."
        )
    assignments = st.get("assignments") or []
    if will_sim or will_api:
        assert_arena_sim_roster(assignments)
        if will_api:
            _assert_api_live_km_collection(assignments)

    # Soft-reset MCC boxes (session-km/Velos → 0), same idea as MCC Game start.
    _reset_arena_device_sessions_for_start(assignments)

    return race_state.update_state(**updates)


def _assert_api_live_km_collection(assignments: list[dict[str, Any]]) -> None:
    """update-data skips when KM collection is disabled — fail early for API-Live."""
    from api.models import Cyclist
    from iot.models import Device

    for entry in assignments:
        cyclist_key = str(entry.get("cyclist") or "").strip()
        device_name = str(entry.get("device_name") or "").strip()
        if not cyclist_key:
            continue
        cyclist = (
            Cyclist.objects.filter(user_id=cyclist_key).first()
            or Cyclist.objects.filter(id_tag=cyclist_key).first()
        )
        if cyclist is not None and not cyclist.is_km_collection_enabled:
            raise ArenaControlError(
                f"Radler „{cyclist.user_id}“: Kilometer-Erfassung ist deaktiviert "
                f"(für API-Live nötig)."
            )
        if device_name:
            device = Device.objects.filter(name=device_name).first()
            if device is not None and not device.is_km_collection_enabled:
                raise ArenaControlError(
                    f"Gerät „{device.name}“: Kilometer-Erfassung ist deaktiviert "
                    f"(für API-Live nötig)."
                )


def _device_assignments_from_arena(
    assignments: list[dict[str, Any]],
) -> dict[str, str]:
    """Map device_name → cyclist user_id (same shape as MCC Game session helpers)."""
    mapping: dict[str, str] = {}
    for entry in assignments:
        device_name = str(entry.get("device_name") or "").strip()
        cyclist = str(entry.get("cyclist") or "").strip()
        if device_name and cyclist:
            mapping[device_name] = cyclist
    return mapping


def _reset_arena_device_sessions_for_start(
    assignments: list[dict[str, Any]],
) -> None:
    """
    Analogous to MCC Game round start: unlock OLED and end device sessions
    so session-km / Velos begin at zero for the next pulses.
    """
    from api.services.device_display import unlock_devices_by_names
    from api.services.device_session import end_game_round_device_sessions
    from minecraft.models import MinecraftArenaMotionSettings

    mapping = _device_assignments_from_arena(assignments)
    if not mapping:
        return

    unlock_devices_by_names(mapping.keys(), reason="arena_race_start")

    settings_obj = MinecraftArenaMotionSettings.get_solo()
    if not settings_obj.end_device_sessions_on_race_start:
        return

    end_game_round_device_sessions(mapping, reason="arena_race_start")


def update_sim_rates(raw_rates: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Update per-lane sim_rate_mps on existing assignments (simulation GUI).

    Does not change cyclist/device bindings — those stay on the main Velo-Arena page.
    """
    config = load_race_config()
    st = race_state.load_state()
    assignments = list(st.get("assignments") or [])
    if not assignments:
        raise ArenaControlError(
            "Keine Radler zugewiesen. Bitte zuerst in der Velo-Arena Radler + Gerät speichern."
        )
    assert_arena_sim_roster(assignments)
    by_lane = {
        str(entry.get("lane_id") or "").strip(): float(entry.get("sim_rate_mps") or 0)
        for entry in raw_rates
        if str(entry.get("lane_id") or "").strip()
    }
    updated: list[dict[str, Any]] = []
    for entry in assignments:
        lane_id = str(entry.get("lane_id") or "").strip()
        row = dict(entry)
        if lane_id in by_lane:
            rate = by_lane[lane_id]
            if rate < 0:
                raise ArenaControlError(f"Bahn {lane_id}: Rate darf nicht negativ sein.")
            row["sim_rate_mps"] = float(rate)
        elif "sim_rate_mps" not in row:
            row["sim_rate_mps"] = default_sim_rate_mps(
                int(row.get("wheel_mm") or 0),
                fallback_mps=float(config.reference_mps),
            )
        updated.append(row)
    # Rates only — mode (internal vs API-Live) is chosen on Start.
    return race_state.update_state(
        assignments=updated,
        last_error="",
    )


def request_stop() -> dict[str, Any]:
    return race_state.update_state(
        pending_command="stop",
        status=race_state.STATUS_STOPPING,
        api_live_pulse=False,
    )


def request_init(*, kill_all: bool = False) -> dict[str, Any]:
    """
    Move existing lane carts to start, or spawn missing ones (after Reset).

    Does not kill carts — seated avatars stay mounted. kill_all is ignored;
    use request_clear_all (Reset) when carts must be removed for new avatars.
    """
    st = race_state.load_state()
    if not st.get("assignments"):
        raise ArenaControlError("Zuerst Radler und Gerät zuweisen, dann Init.")
    if st.get("status") == race_state.STATUS_RUNNING:
        raise ArenaControlError("Rennen läuft — zuerst Stop.")
    return race_state.update_state(
        pending_command="init",
        kill_all_on_reset=False,
        initialized=False,
        last_error="",
    )


def request_clear_all() -> dict[str, Any]:
    """
    Delete all arena minecarts (tags + start chunks). Does not respawn.

    Use before mounting new avatars; then Init to spawn empty carts.
    """
    if race_state.load_state().get("status") == race_state.STATUS_RUNNING:
        raise ArenaControlError("Rennen läuft — zuerst Stop, dann Reset.")
    return race_state.update_state(
        pending_command="clear_all",
        initialized=False,
        last_error="",
    )


def request_reset(*, kill_all: bool = False) -> dict[str, Any]:
    """Backward-compatible alias for Init (reposition/spawn, not clear)."""
    return request_init(kill_all=kill_all)


def request_avatars() -> dict[str, Any]:
    """
    Placeholder: mount dressing-cabin avatars into lane carts.

    Until implemented, existing avatars already in the carts are left as-is.
    """
    st = race_state.load_state()
    if not st.get("assignments"):
        raise ArenaControlError("Zuerst Radler und Gerät zuweisen, dann Init.")
    if not st.get("initialized"):
        raise ArenaControlError("Zuerst Init drücken, danach Avatare.")
    raise ArenaControlError(
        "Avatare aus den Ankleidekabinen kommen später. "
        "Ohne diesen Button bleiben die bisherigen Avatare in den Loren."
    )
