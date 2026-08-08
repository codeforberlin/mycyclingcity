# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    lanes.py
# @note    VeloArena lane geometry: DB (Admin) preferred, TOML fallback.

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings


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
    sign_x: float | None = None
    sign_y: float | None = None
    sign_z: float | None = None

    @property
    def selector(self) -> str:
        return f"@e[type=minecart,tag={self.tag},limit=1]"


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
    cart_label_mode: str
    lanes: tuple[LaneConfig, ...]
    source: str = "toml"  # "database" | "toml"

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


@dataclass(frozen=True)
class LaneAssignment:
    lane: LaneConfig
    cyclist: str
    sim_rate_mps: float = 2.0
    # FKM / pedagogical bonus — Velos only, never cart Motion.
    device_factor: float = 1.0
    # Device.name for API-Live update-data pulses (optional for internal sim).
    device_name: str = ""
    # Station send interval (Device.configuration.send_interval_seconds).
    send_interval_seconds: float = 5.0

    @property
    def motion_mps(self) -> float:
        """Distance rate that drives minecart Motion (no FKM)."""
        return max(0.0, float(self.sim_rate_mps))

    @property
    def effective_mps(self) -> float:
        """Backward-compatible alias for motion_mps (Motion ignores FKM)."""
        return self.motion_mps


def default_config_candidates() -> list[Path]:
    configured = getattr(settings, "MCC_MINECRAFT_ARENA_RACE_CONFIG", "") or ""
    paths: list[Path] = []
    if configured:
        paths.append(Path(configured))
    data_dir = Path(getattr(settings, "DATA_DIR", Path(".")))
    paths.append(data_dir / "velo_arena_race.toml")
    package_dir = Path(__file__).resolve().parents[2] / "config"
    paths.append(package_dir / "velo_arena_race.toml")
    paths.append(package_dir / "velo_arena_race.toml.example")
    test_dir = Path(__file__).resolve().parents[3] / "test" / "velo_arena_race"
    paths.append(test_dir / "velo_arena_race.toml")
    paths.append(test_dir / "velo_arena_race.toml.example")
    return paths


def _default_lock_path() -> Path:
    return Path(
        getattr(
            settings,
            "MCC_MINECRAFT_RCON_LOCK_PATH",
            str(Path(getattr(settings, "DATA_DIR", Path("/tmp"))) / "tmp" / "mcc-minecraft-rcon.lock"),
        )
    )


def _require_float(entry: dict[str, Any], key: str, *, index: int) -> float:
    if key not in entry:
        raise ValueError(f"lanes[{index}] fehlt '{key}'")
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
        if not lane_id or not tag:
            raise ValueError(f"lanes[{index}] braucht 'id' und 'tag'")
        if lane_id.lower() in seen_ids:
            raise ValueError(f"Doppelte Bahn-id: {lane_id!r}")
        seen_ids.add(lane_id.lower())
        for required in ("start_x", "start_y", "start_z"):
            if required not in entry:
                raise ValueError(f"lanes[{index}] fehlt '{required}'")
        sign_x = entry.get("sign_x")
        sign_y = entry.get("sign_y")
        sign_z = entry.get("sign_z")
        has_any = sign_x is not None or sign_y is not None or sign_z is not None
        if has_any and (sign_x is None or sign_y is None or sign_z is None):
            raise ValueError(f"lanes[{index}]: sign_x/y/z müssen zusammen gesetzt sein.")
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
                base_speed=float(entry.get("base_speed", entry.get("speed", 0.4))),
                finish_x_min=_require_float(entry, "finish_x_min", index=index),
                finish_x_max=_require_float(entry, "finish_x_max", index=index),
                finish_z_trigger=_require_float(entry, "finish_z_trigger", index=index),
                impulse_x=float(entry.get("impulse_x", default_ix)),
                impulse_y=float(entry.get("impulse_y", default_iy)),
                impulse_z=float(entry.get("impulse_z", default_iz)),
                sign_x=float(sign_x) if sign_x is not None else None,
                sign_y=float(sign_y) if sign_y is not None else None,
                sign_z=float(sign_z) if sign_z is not None else None,
            )
        )
    return tuple(lanes)


def _load_race_config_from_toml(path: Path) -> RaceConfig:
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    default_ix = float(data.get("default_impulse_x", 0.0))
    default_iy = float(data.get("default_impulse_y", 0.0))
    default_iz = float(data.get("default_impulse_z", 1.0))
    raw_lanes = data.get("lanes")
    if raw_lanes is None and data.get("teams") is not None:
        print("Hinweis: [[teams]] ist veraltet – bitte [[lanes]] nutzen.", file=sys.stderr)
        raw_lanes = data.get("teams")

    from minecraft.services.arena_motion.cart_label_mode import normalize_cart_label_mode

    return RaceConfig(
        config_path=path,
        tick_interval_seconds=float(data.get("tick_interval_seconds", 0.1)),
        motion_min_distance=float(data.get("motion_min_distance", 0.03)),
        lap_cooldown_ticks=int(data.get("lap_cooldown_ticks", 30)),
        actionbar_enabled=bool(data.get("actionbar_enabled", True)),
        rcon_lock_path=Path(str(data.get("rcon_lock_path", _default_lock_path()))),
        rcon_lock_timeout_seconds=float(data.get("rcon_lock_timeout_seconds", 2.0)),
        default_impulse_x=default_ix,
        default_impulse_y=default_iy,
        default_impulse_z=default_iz,
        reference_mps=float(data.get("reference_mps", 2.0)),
        min_motion_speed=float(data.get("min_motion_speed", 0.08)),
        max_motion_speed=float(data.get("max_motion_speed", 0.55)),
        cart_name_visible=bool(data.get("cart_name_visible", True)),
        cart_label_mode=normalize_cart_label_mode(data.get("cart_label_mode")),
        lanes=_parse_lanes(
            raw_lanes, default_ix=default_ix, default_iy=default_iy, default_iz=default_iz
        ),
        source="toml",
    )


def _load_race_config_from_db() -> RaceConfig | None:
    """Return RaceConfig from Admin DB when prefer_database_lanes and lanes exist."""
    try:
        from minecraft.models import MinecraftArenaLane, MinecraftArenaMotionSettings
    except Exception:
        return None

    try:
        settings_obj = MinecraftArenaMotionSettings.get_solo()
    except Exception:
        return None

    if not settings_obj.prefer_database_lanes:
        return None

    rows = list(MinecraftArenaLane.objects.filter(is_active=True).order_by("sort_order", "lane_id"))
    if not rows:
        return None

    lanes = tuple(
        LaneConfig(
            id=row.lane_id,
            name=row.name,
            tag=row.tag,
            color=row.color or "white",
            start_x=float(row.start_x),
            start_y=float(row.start_y),
            start_z=float(row.start_z),
            yaw=float(row.yaw),
            pitch=float(row.pitch),
            base_speed=float(row.base_speed),
            finish_x_min=float(row.finish_x_min),
            finish_x_max=float(row.finish_x_max),
            finish_z_trigger=float(row.finish_z_trigger),
            impulse_x=float(row.impulse_x),
            impulse_y=float(row.impulse_y),
            impulse_z=float(row.impulse_z),
            sign_x=float(row.sign_x) if row.sign_x is not None else None,
            sign_y=float(row.sign_y) if row.sign_y is not None else None,
            sign_z=float(row.sign_z) if row.sign_z is not None else None,
        )
        for row in rows
    )
    from minecraft.services.arena_motion.cart_label_mode import normalize_cart_label_mode

    return RaceConfig(
        config_path=Path("db://minecraft_arena_lane"),
        tick_interval_seconds=float(settings_obj.tick_interval_seconds),
        motion_min_distance=float(settings_obj.motion_min_distance),
        lap_cooldown_ticks=int(settings_obj.lap_cooldown_ticks),
        actionbar_enabled=bool(settings_obj.actionbar_enabled),
        rcon_lock_path=_default_lock_path(),
        rcon_lock_timeout_seconds=float(
            getattr(settings, "MCC_MINECRAFT_RCON_LOCK_TIMEOUT", 2.0)
        ),
        default_impulse_x=float(settings_obj.default_impulse_x),
        default_impulse_y=float(settings_obj.default_impulse_y),
        default_impulse_z=float(settings_obj.default_impulse_z),
        reference_mps=float(settings_obj.reference_mps),
        min_motion_speed=float(settings_obj.min_motion_speed),
        max_motion_speed=float(settings_obj.max_motion_speed),
        cart_name_visible=bool(settings_obj.cart_name_visible),
        cart_label_mode=normalize_cart_label_mode(settings_obj.cart_label_mode),
        lanes=lanes,
        source="database",
    )


def load_race_config(config_path: Path | None = None) -> RaceConfig:
    """
    Load arena config.

    Priority:
    1. Explicit config_path (TOML) if given
    2. Active lanes in Django Admin DB (if prefer_database_lanes)
    3. TOML search paths
    """
    if config_path is not None:
        if not config_path.is_file():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {config_path}")
        return _load_race_config_from_toml(config_path)

    db_config = _load_race_config_from_db()
    if db_config is not None:
        return db_config

    path = None
    for candidate in default_config_candidates():
        if candidate.is_file():
            path = candidate
            break
    if path is None:
        raise FileNotFoundError(
            "Keine Arena-Bahnen in der Datenbank und keine TOML-Config gefunden. "
            "Bitte Bahnen unter Minecraft → Arena-Bahnen anlegen oder "
            "MCC_MINECRAFT_ARENA_RACE_CONFIG setzen."
        )
    return _load_race_config_from_toml(path)


# Minecraft entity Motion is in blocks per game tick (20 TPS).
# Arena rails are built 1 block = 1 meter, so bike m/s maps 1:1 to blocks/s.
MC_TICKS_PER_SECOND = 20.0


def motion_from_mps(mps: float, *, max_motion: float | None = None) -> float:
    """
    Convert real bike speed (m/s) to Minecraft Motion magnitude (blocks/tick).

    With 1 block = 1 m: blocks/s = m/s → Motion = m/s / 20.
    """
    speed = max(0.0, float(mps))
    motion = speed / MC_TICKS_PER_SECOND
    if max_motion is not None and max_motion > 0:
        motion = min(motion, float(max_motion))
    return motion


def motion_speed_for(
    config: RaceConfig,
    assignment: LaneAssignment,
    *,
    use_distance: bool,
) -> float:
    """
    Cart Motion magnitude for this assignment.

    When use_distance is True (sim / API-Live writer): 1:1 bike m/s → blocks/s.
    Otherwise callers should not use this for Motion (device-live waits for pulses).
    """
    if not use_distance:
        return assignment.lane.base_speed
    return motion_from_mps(
        assignment.motion_mps,
        max_motion=config.max_motion_speed,
    )


def import_lanes_from_toml(path: Path | None = None, *, deactivate_missing: bool = False) -> int:
    """Upsert TOML lanes into MinecraftArenaLane. Returns number of lanes written."""
    from minecraft.models import MinecraftArenaLane, MinecraftArenaMotionSettings

    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(f"TOML nicht gefunden: {path}")
        config = _load_race_config_from_toml(path)
    else:
        found = next((p for p in default_config_candidates() if p.is_file()), None)
        if found is None:
            raise FileNotFoundError("Keine TOML zum Importieren gefunden.")
        config = _load_race_config_from_toml(found)

    settings_obj = MinecraftArenaMotionSettings.get_solo()
    settings_obj.tick_interval_seconds = config.tick_interval_seconds
    settings_obj.motion_min_distance = config.motion_min_distance
    settings_obj.lap_cooldown_ticks = config.lap_cooldown_ticks
    settings_obj.actionbar_enabled = config.actionbar_enabled
    settings_obj.cart_name_visible = config.cart_name_visible
    settings_obj.cart_label_mode = config.cart_label_mode
    settings_obj.reference_mps = config.reference_mps
    settings_obj.min_motion_speed = config.min_motion_speed
    settings_obj.max_motion_speed = config.max_motion_speed
    settings_obj.default_impulse_x = config.default_impulse_x
    settings_obj.default_impulse_y = config.default_impulse_y
    settings_obj.default_impulse_z = config.default_impulse_z
    settings_obj.prefer_database_lanes = True
    settings_obj.save()

    seen: set[str] = set()
    for index, lane in enumerate(config.lanes):
        seen.add(lane.id)
        MinecraftArenaLane.objects.update_or_create(
            lane_id=lane.id,
            defaults={
                "name": lane.name,
                "tag": lane.tag,
                "color": lane.color,
                "sort_order": index,
                "is_active": True,
                "start_x": lane.start_x,
                "start_y": lane.start_y,
                "start_z": lane.start_z,
                "yaw": lane.yaw,
                "pitch": lane.pitch,
                "base_speed": lane.base_speed,
                "finish_x_min": lane.finish_x_min,
                "finish_x_max": lane.finish_x_max,
                "finish_z_trigger": lane.finish_z_trigger,
                "impulse_x": lane.impulse_x,
                "impulse_y": lane.impulse_y,
                "impulse_z": lane.impulse_z,
                "sign_x": lane.sign_x,
                "sign_y": lane.sign_y,
                "sign_z": lane.sign_z,
            },
        )
    if deactivate_missing:
        MinecraftArenaLane.objects.exclude(lane_id__in=seen).update(is_active=False)
    return len(config.lanes)
