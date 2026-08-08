# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    race_config.py
# @note    Load VeloArena lane geometry from TOML (cyclists assigned at runtime).

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = PACKAGE_DIR / "velo_arena_race.toml"
EXAMPLE_CONFIG_FILE = PACKAGE_DIR / "velo_arena_race.toml.example"


@dataclass(frozen=True)
class LaneConfig:
    """One physical arena lane (geometry + minecart tag)."""

    id: str
    name: str
    tag: str
    color: str
    start_x: float
    start_y: float
    start_z: float
    yaw: float
    pitch: float
    base_speed: float
    finish_x_min: float
    finish_x_max: float
    finish_z_trigger: float
    impulse_x: float
    impulse_y: float
    impulse_z: float
    # Optional world sign block that shows the assigned cyclist name.
    sign_x: float | None = None
    sign_y: float | None = None
    sign_z: float | None = None

    @property
    def selector(self) -> str:
        return f"@e[type=minecart,tag={self.tag},limit=1]"

    @property
    def has_sign(self) -> bool:
        return (
            self.sign_x is not None
            and self.sign_y is not None
            and self.sign_z is not None
        )


@dataclass(frozen=True)
class RaceConfig:
    config_path: Path
    tick_interval_seconds: float
    motion_min_distance: float
    lap_cooldown_ticks: int
    actionbar_enabled: bool
    rcon_lock_path: Path
    rcon_lock_timeout_seconds: float
    default_impulse_x: float
    default_impulse_y: float
    default_impulse_z: float
    reference_mps: float
    min_motion_speed: float
    max_motion_speed: float
    cart_name_visible: bool
    best_times_file: Path
    # Fallback IoT send interval when no per-cyclist --sim-interval is set.
    sim_update_interval_seconds: float
    lanes: tuple[LaneConfig, ...]

    def lane_by_key(self, key: str) -> LaneConfig | None:
        needle = key.strip().lower()
        for lane in self.lanes:
            if lane.id.lower() == needle:
                return lane
            if lane.name.lower() == needle:
                return lane
            if lane.tag.lower() == needle:
                return lane
            if lane.tag.lower().removeprefix("velo_") == needle:
                return lane
            if lane.id.lower().removeprefix("lane_") == needle:
                return lane
        return None

    def resolve_lanes(self, keys: list[str] | None) -> tuple[LaneConfig, ...]:
        if not keys:
            return self.lanes
        resolved: list[LaneConfig] = []
        for key in keys:
            lane = self.lane_by_key(key)
            if lane is None:
                raise ValueError(f"Unbekannte Bahn: {key!r}")
            if lane not in resolved:
                resolved.append(lane)
        return tuple(resolved)


@dataclass(frozen=True)
class LaneAssignment:
    """Runtime binding: cyclist (and optional rates) on a lane."""

    lane: LaneConfig
    cyclist: str
    sim_rate_mps: float = 2.0
    device_factor: float = 1.0
    send_interval_seconds: float = 5.0

    @property
    def effective_mps(self) -> float:
        return max(0.0, self.sim_rate_mps) * max(0.0, self.device_factor)

    @property
    def motion_mps(self) -> float:
        """Distance rate used for IoT pulse size (same as effective in this harness)."""
        return self.effective_mps


def _require_float(entry: dict[str, Any], key: str, *, index: int, section: str) -> float:
    if key not in entry:
        raise ValueError(f"{section}[{index}] fehlt '{key}'")
    return float(entry[key])


def _parse_lanes(
    raw_lanes: Any,
    *,
    default_ix: float,
    default_iy: float,
    default_iz: float,
) -> tuple[LaneConfig, ...]:
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise ValueError("Mindestens eine Bahn unter [[lanes]] erforderlich.")
    lanes: list[LaneConfig] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw_lanes):
        if not isinstance(entry, dict):
            raise ValueError(f"lanes[{index}] muss ein Objekt sein.")
        lane_id = str(entry.get("id") or entry.get("name") or "").strip()
        tag = str(entry.get("tag") or "").strip()
        if not lane_id:
            raise ValueError(f"lanes[{index}] fehlt 'id'")
        if not tag:
            raise ValueError(f"lanes[{index}] fehlt 'tag'")
        if lane_id.lower() in seen_ids:
            raise ValueError(f"Doppelte Bahn-id: {lane_id!r}")
        seen_ids.add(lane_id.lower())
        for required in ("start_x", "start_y", "start_z"):
            if required not in entry:
                raise ValueError(f"lanes[{index}] fehlt '{required}'")
        base_speed = float(entry.get("base_speed", entry.get("speed", 0.4)))
        sign_x = entry.get("sign_x")
        sign_y = entry.get("sign_y")
        sign_z = entry.get("sign_z")
        has_any_sign = sign_x is not None or sign_y is not None or sign_z is not None
        if has_any_sign and (
            sign_x is None or sign_y is None or sign_z is None
        ):
            raise ValueError(
                f"lanes[{index}]: sign_x, sign_y und sign_z müssen zusammen gesetzt sein."
            )
        lanes.append(
            LaneConfig(
                id=lane_id,
                name=str(entry.get("name", lane_id)),
                tag=tag,
                color=str(entry.get("color", "white")),
                start_x=float(entry["start_x"]),
                start_y=float(entry["start_y"]),
                start_z=float(entry["start_z"]),
                yaw=float(entry.get("yaw", 0.0)),
                pitch=float(entry.get("pitch", 0.0)),
                base_speed=base_speed,
                finish_x_min=_require_float(
                    entry, "finish_x_min", index=index, section="lanes"
                ),
                finish_x_max=_require_float(
                    entry, "finish_x_max", index=index, section="lanes"
                ),
                finish_z_trigger=_require_float(
                    entry, "finish_z_trigger", index=index, section="lanes"
                ),
                impulse_x=float(entry.get("impulse_x", default_ix)),
                impulse_y=float(entry.get("impulse_y", default_iy)),
                impulse_z=float(entry.get("impulse_z", default_iz)),
                sign_x=float(sign_x) if sign_x is not None else None,
                sign_y=float(sign_y) if sign_y is not None else None,
                sign_z=float(sign_z) if sign_z is not None else None,
            )
        )
    return tuple(lanes)


def load_race_config(config_path: Path | None = None) -> RaceConfig:
    path = config_path or DEFAULT_CONFIG_FILE
    if not path.is_file():
        if config_path is None and EXAMPLE_CONFIG_FILE.is_file():
            print(
                f"Hinweis: {DEFAULT_CONFIG_FILE.name} nicht gefunden, "
                f"verwende {EXAMPLE_CONFIG_FILE.name}.",
                file=sys.stderr,
            )
            path = EXAMPLE_CONFIG_FILE
        else:
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    default_ix = float(data.get("default_impulse_x", 0.0))
    default_iy = float(data.get("default_impulse_y", 0.0))
    default_iz = float(data.get("default_impulse_z", 1.0))

    raw_lanes = data.get("lanes")
    if raw_lanes is None and data.get("teams") is not None:
        # Soft migration from older [[teams]] configs.
        print(
            "Hinweis: [[teams]] ist veraltet – bitte auf [[lanes]] umstellen.",
            file=sys.stderr,
        )
        raw_lanes = data.get("teams")

    best_times_name = str(data.get("best_times_file", "arena_best_times.json"))
    best_times_path = Path(best_times_name)
    if not best_times_path.is_absolute():
        best_times_path = path.parent / best_times_path

    return RaceConfig(
        config_path=path,
        tick_interval_seconds=float(data.get("tick_interval_seconds", 0.1)),
        motion_min_distance=float(data.get("motion_min_distance", 0.03)),
        lap_cooldown_ticks=int(data.get("lap_cooldown_ticks", 30)),
        actionbar_enabled=bool(data.get("actionbar_enabled", True)),
        rcon_lock_path=Path(
            str(data.get("rcon_lock_path", "/data/var/mcc/tmp/mcc-minecraft-rcon.lock"))
        ),
        rcon_lock_timeout_seconds=float(data.get("rcon_lock_timeout_seconds", 2.0)),
        default_impulse_x=default_ix,
        default_impulse_y=default_iy,
        default_impulse_z=default_iz,
        reference_mps=float(data.get("reference_mps", 2.0)),
        min_motion_speed=float(data.get("min_motion_speed", 0.08)),
        max_motion_speed=float(data.get("max_motion_speed", 0.55)),
        cart_name_visible=bool(data.get("cart_name_visible", True)),
        best_times_file=best_times_path,
        sim_update_interval_seconds=float(
            data.get("sim_update_interval_seconds", 5.0)
        ),
        lanes=_parse_lanes(
            raw_lanes,
            default_ix=default_ix,
            default_iy=default_iy,
            default_iz=default_iz,
        ),
    )


def parse_assign_token(token: str) -> tuple[str, str]:
    """Parse 'lane_1:anna' or 'lane_1=anna' into (lane_key, cyclist)."""
    raw = token.strip()
    if ":" in raw:
        lane_key, _, cyclist = raw.partition(":")
    elif "=" in raw:
        lane_key, _, cyclist = raw.partition("=")
    else:
        raise ValueError(
            f"Ungültiges --assign {token!r} (erwartet lane:cyclist)."
        )
    lane_key = lane_key.strip()
    cyclist = cyclist.strip()
    if not lane_key or not cyclist:
        raise ValueError(f"Ungültiges --assign {token!r} (erwartet lane:cyclist).")
    return lane_key, cyclist


def parse_rate_token(token: str) -> tuple[str, float]:
    """Parse 'anna=2.0' into (cyclist, value)."""
    raw = token.strip()
    if "=" in raw:
        name, _, value = raw.partition("=")
    elif ":" in raw:
        name, _, value = raw.partition(":")
    else:
        raise ValueError(f"Ungültiges Rate-Token {token!r} (erwartet name=wert).")
    name = name.strip()
    if not name:
        raise ValueError(f"Ungültiges Rate-Token {token!r}.")
    try:
        return name, float(value.strip())
    except ValueError as exc:
        raise ValueError(f"Ungültiger Zahlenwert in {token!r}.") from exc


def build_assignments(
    config: RaceConfig,
    assign_tokens: list[str],
    *,
    sim_rates: dict[str, float] | None = None,
    device_factors: dict[str, float] | None = None,
    sim_intervals: dict[str, float] | None = None,
    default_rate_mps: float = 2.0,
    spread_default_rates: bool = False,
) -> tuple[LaneAssignment, ...]:
    """Build lane↔cyclist assignments from CLI tokens."""
    if not assign_tokens:
        raise ValueError("Mindestens eine Zuweisung --assign lane:cyclist erforderlich.")

    rates = {k.lower(): v for k, v in (sim_rates or {}).items()}
    factors = {k.lower(): v for k, v in (device_factors or {}).items()}
    intervals = {k.lower(): v for k, v in (sim_intervals or {}).items()}
    default_interval = float(config.sim_update_interval_seconds)
    assignments: list[LaneAssignment] = []
    used_lanes: set[str] = set()
    used_cyclists: set[str] = set()

    for index, token in enumerate(assign_tokens):
        lane_key, cyclist = parse_assign_token(token)
        lane = config.lane_by_key(lane_key)
        if lane is None:
            raise ValueError(f"Unbekannte Bahn in --assign: {lane_key!r}")
        if lane.id.lower() in used_lanes:
            raise ValueError(f"Bahn mehrfach zugewiesen: {lane.id}")
        cyclist_key = cyclist.lower()
        if cyclist_key in used_cyclists:
            raise ValueError(f"Radler mehrfach zugewiesen: {cyclist}")
        used_lanes.add(lane.id.lower())
        used_cyclists.add(cyclist_key)

        if cyclist_key in rates:
            rate = rates[cyclist_key]
        elif spread_default_rates:
            rate = default_rate_mps * (0.6 + 0.3 * index)
        else:
            rate = default_rate_mps
        factor = factors.get(cyclist_key, 1.0)
        interval = intervals.get(cyclist_key, default_interval)
        assignments.append(
            LaneAssignment(
                lane=lane,
                cyclist=cyclist,
                sim_rate_mps=rate,
                device_factor=factor,
                send_interval_seconds=max(1.0, float(interval)),
            )
        )
    return tuple(assignments)


def motion_speed_for(
    config: RaceConfig,
    assignment: LaneAssignment,
    *,
    use_distance: bool,
) -> float:
    """Compute Motion magnitude for a lane/cyclist."""
    if not use_distance:
        return assignment.lane.base_speed
    ref = max(1e-6, config.reference_mps)
    scaled = assignment.lane.base_speed * (assignment.effective_mps / ref)
    return max(config.min_motion_speed, min(config.max_motion_speed, scaled))
