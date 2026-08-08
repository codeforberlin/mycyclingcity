# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    controller.py
# @note    Minecart motion + text_display labels (ported from test harness).

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from minecraft.services.arena_motion.cart_label_mode import is_name_only_label_mode
from minecraft.services.arena_motion.arena_bossbar import (
    bossbar_enabled,
    build_bossbar_commands,
    build_clear_bossbar_command,
)
from minecraft.services.arena_motion.locked_rcon import LockedRconGateway
from minecraft.services.sidebar_visibility import arena_audience_selector

if TYPE_CHECKING:
    pass

_POS_RE = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+")

# Floating nameplate height above the cart (same Y for every lane).
_LABEL_Y_BASE = 1.4
_LABEL_SCALE = 2.2


@dataclass(frozen=True)
class LabelDisplaySnapshot:
    """Normalized label fields — skip RCON when unchanged between ticks."""

    name_only: bool = False
    display_name: str = ""
    final: bool = False
    speed_kmh: int | None = None
    place: int | None = None
    velos: int | None = None
    laps_completed: int | None = None
    target_laps: int | None = None
    finish_time_s: float | None = None


@dataclass
class CartState:
    assignment: LaneAssignment
    last_x: float = field(init=False)
    last_z: float = field(init=False)
    current_lap: int = 1
    finished: bool = False
    cooldown_ticks: int = 0
    lap_start_time: float = 0.0
    last_mx: float = 0.0
    last_mz: float = 0.0
    missing_ticks: int = 0
    distance_m: float = 0.0
    live_distance_m: float = 0.0
    last_delta_m: float = 0.0
    target_speed: float = 0.0
    progress_blocks: float = 0.0
    finish_time: float | None = None
    place: int = 1
    last_speed_kmh: float = 0.0
    velos: int = 0
    live_velos: int = 0
    # Sparse IoT update simulation: hold last m/s between station pulses.
    send_interval_seconds: float = 5.0
    held_mps: float = 0.0
    next_pulse_at: float = 0.0
    last_pulse_at: float = 0.0
    # Device-live (normal arena): last seen CyclistDeviceCurrentMileage km.
    last_session_km: float | None = None
    label_snapshot: LabelDisplaySnapshot | None = None

    def __post_init__(self) -> None:
        lane = self.assignment.lane
        self.last_x = lane.start_x
        self.last_z = lane.start_z
        self.send_interval_seconds = float(
            getattr(self.assignment, "send_interval_seconds", 5.0) or 5.0
        )

    def reset_race_progress(self) -> None:
        """Clear ranking/progress from a previous race (Start without Reset)."""
        lane = self.assignment.lane
        self.current_lap = 1
        self.finished = False
        self.cooldown_ticks = 0
        self.lap_start_time = 0.0
        self.last_mx = 0.0
        self.last_mz = 0.0
        self.missing_ticks = 0
        self.distance_m = 0.0
        self.live_distance_m = 0.0
        self.last_delta_m = 0.0
        self.target_speed = 0.0
        self.progress_blocks = 0.0
        self.finish_time = None
        self.place = 1
        self.last_speed_kmh = 0.0
        self.velos = 0
        self.live_velos = 0
        self.held_mps = 0.0
        self.next_pulse_at = 0.0
        self.last_pulse_at = 0.0
        self.last_session_km = None
        self.label_snapshot = None
        self.send_interval_seconds = float(
            getattr(self.assignment, "send_interval_seconds", 5.0) or 5.0
        )
        self.last_x = lane.start_x
        self.last_z = lane.start_z

    def refresh_velos(self) -> int:
        """Velos from ridden km × device FKM (pedagogical bonus); Motion ignores FKM."""
        from api.velos import calculate_velos

        self.velos = calculate_velos(
            self.distance_m / 1000.0,
            max(0.0, float(self.assignment.device_factor)),
        )
        return self.velos

    def refresh_live_velos(self) -> int:
        """
        Velos for ArenaLive / labels.

        Must track the same meters as the cyclist session (device update-data or
        simulated IoT pulses) — not the cart's geometric path length.
        """
        from api.velos import calculate_velos

        self.live_velos = calculate_velos(
            self.live_distance_m / 1000.0,
            max(0.0, float(self.assignment.device_factor)),
        )
        return self.live_velos

    @property
    def lane(self) -> LaneConfig:
        return self.assignment.lane

    @property
    def cyclist(self) -> str:
        return self.assignment.cyclist

    def laps_completed(self, target_laps: int) -> int:
        if self.finished:
            return target_laps
        return max(0, self.current_lap - 1)


def compute_places(states: list[CartState], target_laps: int) -> dict[str, int]:
    def sort_key(state: CartState) -> tuple:
        laps = state.laps_completed(target_laps)
        if state.finished:
            return (-laps, state.finish_time if state.finish_time is not None else 1e18)
        return (-laps, -state.progress_blocks)

    ordered = sorted(states, key=sort_key)
    return {state.lane.id: index + 1 for index, state in enumerate(ordered)}


def compute_places_by_velos(states: list[CartState]) -> dict[str, int]:
    """Rank by earned Velos (descending), then distance as tie-breaker."""

    def sort_key(state: CartState) -> tuple:
        velos = max(int(state.live_velos), int(state.velos))
        return (-velos, -state.live_distance_m, -state.progress_blocks)

    ordered = sorted(states, key=sort_key)
    return {state.lane.id: index + 1 for index, state in enumerate(ordered)}


def apply_places(
    states: list[CartState],
    target_laps: int,
    *,
    by_velos: bool = False,
) -> None:
    places = (
        compute_places_by_velos(states)
        if by_velos
        else compute_places(states, target_laps)
    )
    for state in states:
        state.place = places.get(state.lane.id, 1)


class RaceController:
    """Drive tagged minecarts via Motion updates; no scoreboard commands."""

    def __init__(self, gateway: LockedRconGateway, config: RaceConfig):
        self.gateway = gateway
        self.config = config

    def run(self, command: str) -> str:
        return self.gateway.run(command)

    def get_position(self, lane: LaneConfig) -> tuple[float, float] | None:
        resp = self.run(f"data get entity {lane.selector} Pos")
        numbers = _POS_RE.findall(resp)
        if len(numbers) >= 3:
            return float(numbers[0]), float(numbers[2])
        return None

    @staticmethod
    def chunk_origin(coord: float) -> int:
        return math.floor(coord / 16.0) * 16

    def kill_all_minecarts(self) -> str:
        return self.run("kill @e[type=minecart]")

    def clear_arena_minecarts(self) -> None:
        """Remove all arena lane carts and their floating labels (all configured lanes)."""
        # Labels first (while still findable as passengers / by common tag).
        self.clear_all_arena_labels()
        for lane in self.config.lanes:
            self.run(f"kill @e[type=minecart,tag={lane.tag}]")
        if self.config.lanes:
            self.clear_minecarts_in_lane_chunks(self.config.lanes)

    def clear_all_arena_labels(self) -> None:
        """Remove floating rider nameplates (common tag + per-lane + start chunks)."""
        # Common tag on every nameplate — catches orphans and tag-scheme mismatches.
        self.run('kill @e[type=text_display,tag=velo_label]')
        self.run('kill @e[type=armor_stand,tag=velo_label]')
        self.run('kill @e[type=text_display,tag=velo_podium]')
        for lane in self.config.lanes:
            self.clear_lane_label(lane)
        if self.config.lanes:
            self.clear_labels_in_lane_chunks(self.config.lanes)

    def clear_minecarts_in_lane_chunks(
        self, lanes: list[LaneConfig] | tuple[LaneConfig, ...], *, y_pad: float = 8.0
    ) -> None:
        chunks: dict[tuple[int, int], float] = {}
        for lane in lanes:
            cx = self.chunk_origin(lane.start_x)
            cz = self.chunk_origin(lane.start_z)
            chunks.setdefault((cx, cz), lane.start_y)
        for (cx, cz), y_ref in chunks.items():
            y0 = int(math.floor(y_ref - y_pad))
            dy = int(math.ceil(2 * y_pad))
            self.run(f"kill @e[type=minecart,x={cx},y={y0},z={cz},dx=15,dy={dy},dz=15]")

    def clear_labels_in_lane_chunks(
        self, lanes: list[LaneConfig] | tuple[LaneConfig, ...], *, y_pad: float = 8.0
    ) -> None:
        """Kill nameplates left in start chunks (e.g. after cart despawn mid-race)."""
        chunks: dict[tuple[int, int], float] = {}
        for lane in lanes:
            cx = self.chunk_origin(lane.start_x)
            cz = self.chunk_origin(lane.start_z)
            chunks.setdefault((cx, cz), lane.start_y)
        for (cx, cz), y_ref in chunks.items():
            y0 = int(math.floor(y_ref - y_pad))
            dy = int(math.ceil(2 * y_pad))
            self.run(
                f"kill @e[type=text_display,x={cx},y={y0},z={cz},dx=15,dy={dy},dz=15]"
            )

    def label_tag(self, lane: LaneConfig) -> str:
        return f"velo_label_{lane.tag}"

    def label_y_offset(self, lane: LaneConfig) -> float:
        """Vertical billboard offset above the cart (uniform across lanes)."""
        return _LABEL_Y_BASE

    def clear_lane_label(self, lane: LaneConfig) -> None:
        tag = self.label_tag(lane)
        self.run(f"kill @e[type=text_display,tag={tag}]")
        self.run(f"kill @e[type=armor_stand,tag={tag}]")
        # Legacy harness tagged labels by lane.id (velo_label_lane_1).
        legacy = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in lane.id)
        legacy_tag = f"velo_label_{legacy}"
        if legacy_tag != tag:
            self.run(f"kill @e[type=text_display,tag={legacy_tag}]")
            self.run(f"kill @e[type=armor_stand,tag={legacy_tag}]")

    @staticmethod
    def _sanitize_display_name(name: str) -> str:
        cleaned = re.sub(r'["\\]', "", name)[:32]
        return cleaned or "Rider"

    @staticmethod
    def _mc_color(color: str) -> str:
        allowed = {
            "black", "dark_blue", "dark_green", "dark_aqua", "dark_red", "dark_purple",
            "gold", "gray", "dark_gray", "blue", "green", "aqua", "red", "light_purple",
            "yellow", "white",
        }
        c = (color or "white").lower()
        return c if c in allowed else "white"

    def _format_label_text(
        self,
        name: str,
        color: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
        final: bool = False,
        finish_time_s: float | None = None,
        velos: int | None = None,
        laps_completed: int | None = None,
        target_laps: int | None = None,
    ) -> str:
        if is_name_only_label_mode(self.config.cart_label_mode):
            return f'text:{{text:"{name}",color:"{color}",bold:1b}}'

        title = f"{place}. {name}" if place else name

        def _laps_line(*, bold: bool) -> str | None:
            if laps_completed is None or target_laps is None or int(target_laps) < 1:
                return None
            done = max(0, int(laps_completed))
            total = int(target_laps)
            bold_flag = ",bold:1b" if bold else ""
            return f'{{text:"\\n{done}/{total} Runden",color:"gray"{bold_flag}}}'

        if final:
            time_str = f"{max(0.0, float(finish_time_s)):.1f}s" if finish_time_s is not None else "—"
            parts = [
                f'{{text:"{title}",color:"{color}",bold:1b}}',
                f'{{text:"\\n{time_str}",color:"gold",bold:1b}}',
            ]
            if velos is not None and int(velos) > 0:
                parts.append(f'{{text:"\\n{int(velos)} Velos",color:"aqua",bold:1b}}')
            laps = _laps_line(bold=True)
            if laps:
                parts.append(laps)
            return "text:[" + ",".join(parts) + "]"
        # Hide km/h (and Velos/laps) when stationary — only while moving.
        if speed_kmh is None or float(speed_kmh) <= 0.0:
            return f'text:{{text:"{title}",color:"{color}",bold:1b}}'
        speed_str = f"{float(speed_kmh):.0f} km/h"
        parts = [
            f'{{text:"{title}",color:"{color}",bold:1b}}',
            f'{{text:"\\n{speed_str}",color:"yellow"}}',
        ]
        if velos is not None:
            parts.append(f'{{text:"\\n{max(0, int(velos))} Velos",color:"aqua"}}')
        laps = _laps_line(bold=False)
        if laps:
            parts.append(laps)
        return "text:[" + ",".join(parts) + "]"

    def label_display_snapshot(
        self,
        *,
        cyclist: str,
        speed_kmh: float | None = None,
        place: int | None = None,
        final: bool = False,
        finish_time_s: float | None = None,
        velos: int | None = None,
        laps_completed: int | None = None,
        target_laps: int | None = None,
    ) -> LabelDisplaySnapshot:
        display_name = self._sanitize_display_name(cyclist.strip() or "")
        if is_name_only_label_mode(self.config.cart_label_mode):
            return LabelDisplaySnapshot(name_only=True, display_name=display_name)

        speed_disp: int | None
        if speed_kmh is None or float(speed_kmh) <= 0.0:
            speed_disp = None
        else:
            speed_disp = int(round(float(speed_kmh)))
        finish_disp = (
            round(float(finish_time_s), 1) if finish_time_s is not None else None
        )
        return LabelDisplaySnapshot(
            final=bool(final),
            speed_kmh=speed_disp,
            place=int(place) if place is not None else None,
            velos=int(velos) if velos is not None else None,
            laps_completed=int(laps_completed) if laps_completed is not None else None,
            target_laps=int(target_laps) if target_laps is not None else None,
            finish_time_s=finish_disp,
        )

    def set_cart_rider_name(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
        velos: int | None = None,
        laps_completed: int | None = None,
        target_laps: int | None = None,
    ) -> None:
        if not self.config.cart_name_visible:
            return
        name = self._sanitize_display_name(cyclist.strip() or lane.name)
        color = self._mc_color(lane.color)
        tag = self.label_tag(lane)
        y_off = self.label_y_offset(lane)
        self.clear_lane_label(lane)
        self.run(f"data modify entity {lane.selector} CustomNameVisible set value 0b")
        label_text = self._format_label_text(
            name,
            color,
            speed_kmh=speed_kmh,
            place=place,
            velos=velos,
            laps_completed=laps_completed,
            target_laps=target_laps,
        )
        nbt = (
            "{"
            f'Tags:["velo_label","{tag}"],'
            'billboard:"center",shadow:1b,see_through:0b,background:0,'
            f"transformation:{{translation:[0f,{y_off}f,0f],"
            "left_rotation:[0f,0f,0f,1f],"
            f"scale:[{_LABEL_SCALE}f,{_LABEL_SCALE}f,{_LABEL_SCALE}f],"
            "right_rotation:[0f,0f,0f,1f]},"
            f"{label_text}"
            "}"
        )
        self.run(
            f"summon text_display {lane.start_x} {lane.start_y + 1.0} {lane.start_z} {nbt}"
        )
        self.run(f"ride @e[type=text_display,tag={tag},limit=1] mount {lane.selector}")

    def update_cart_label(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
        final: bool = False,
        finish_time_s: float | None = None,
        velos: int | None = None,
        laps_completed: int | None = None,
        target_laps: int | None = None,
        force: bool = False,
        track: CartState | None = None,
    ) -> bool:
        """
        Update the floating text_display label.

        When ``track`` is set, skip the RCON call if displayed values are unchanged
        (unless ``force``). Returns True if an update was sent.
        """
        if not self.config.cart_name_visible:
            return False
        snapshot = self.label_display_snapshot(
            cyclist=cyclist,
            speed_kmh=speed_kmh,
            place=place,
            final=final,
            finish_time_s=finish_time_s,
            velos=velos,
            laps_completed=laps_completed,
            target_laps=target_laps,
        )
        if track is not None and not force and track.label_snapshot == snapshot:
            return False
        name = self._sanitize_display_name(cyclist.strip() or lane.name)
        color = self._mc_color(lane.color)
        tag = self.label_tag(lane)
        formatted = self._format_label_text(
            name,
            color,
            speed_kmh=speed_kmh,
            place=place,
            final=final,
            finish_time_s=finish_time_s,
            velos=velos,
            laps_completed=laps_completed,
            target_laps=target_laps,
        )
        value = formatted[len("text:") :]
        resp = self.run(
            f"data modify entity @e[type=text_display,tag={tag},limit=1] text set value {value}"
        )
        if "Unable" in (resp or "") or "No entity" in (resp or ""):
            if final:
                self.set_cart_rider_name(
                    lane,
                    cyclist,
                    speed_kmh=None,
                    place=place,
                    velos=velos,
                    laps_completed=laps_completed,
                    target_laps=target_laps,
                )
                formatted_final = self._format_label_text(
                    name,
                    color,
                    place=place,
                    final=True,
                    finish_time_s=finish_time_s,
                    velos=velos,
                    laps_completed=laps_completed,
                    target_laps=target_laps,
                )
                value_final = formatted_final[len("text:") :]
                self.run(
                    f"data modify entity @e[type=text_display,tag={tag},limit=1] "
                    f"text set value {value_final}"
                )
            else:
                self.set_cart_rider_name(
                    lane,
                    cyclist,
                    speed_kmh=speed_kmh,
                    place=place,
                    velos=velos,
                    laps_completed=laps_completed,
                    target_laps=target_laps,
                )
        if track is not None:
            track.label_snapshot = snapshot
        return True

    def apply_rider_labels(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
    ) -> None:
        self.set_cart_rider_name(lane, cyclist, speed_kmh=speed_kmh, place=place)

    def cart_exists(self, lane: LaneConfig) -> bool:
        """True if a tagged minecart for this lane is currently loaded."""
        return self.get_position(lane) is not None

    def ensure_cart_at_start(
        self,
        lane: LaneConfig,
        *,
        cyclist: str | None = None,
        place: int | None = None,
    ) -> bool:
        """
        Put the lane cart on the start rail without ejecting passengers.

        If a tagged cart already exists, teleport it to the start and freeze it
        (avatars stay seated). If none exists (e.g. after Reset), summon a new one.

        Returns True when a new cart was summoned, False when an existing one
        was repositioned.
        """
        spawned = not self.cart_exists(lane)
        if spawned:
            self.run(
                f"summon minecart {lane.start_x} {lane.start_y} {lane.start_z} "
                f'{{Tags:["{lane.tag}"],Motion:[0.0d,0.0d,0.0d]}}'
            )
        self.run(
            f"tp {lane.selector} {lane.start_x} {lane.start_y} {lane.start_z} "
            f"{lane.yaw} {lane.pitch}"
        )
        # Explicit stop: rails/slope must not start the race before Start.
        self.stop_cart(lane)
        if cyclist:
            self.apply_rider_labels(lane, cyclist, speed_kmh=None, place=place)
        return spawned

    def reset_cart(
        self,
        lane: LaneConfig,
        *,
        cyclist: str | None = None,
        place: int | None = None,
    ) -> None:
        """Spawn cart at start and freeze it (no impulse until Start)."""
        self.ensure_cart_at_start(lane, cyclist=cyclist, place=place)

    def stop_cart(self, lane: LaneConfig) -> None:
        self.run(
            f"execute as {lane.selector} run data modify entity @s Motion "
            f"set value [0.0, 0.0, 0.0]"
        )

    def apply_impulse(self, lane: LaneConfig, speed: float) -> None:
        ix, iy, iz = lane.impulse_x, lane.impulse_y, lane.impulse_z
        length = math.sqrt(ix * ix + iy * iy + iz * iz)
        if length <= 1e-9:
            ix, iy, iz, length = 0.0, 0.0, 1.0, 1.0
        mx = round((ix / length) * speed, 3)
        my = round((iy / length) * speed, 3)
        mz = round((iz / length) * speed, 3)
        self.run(
            f"execute as {lane.selector} at @s run data modify entity @s Motion "
            f"set value [{mx}, {my}, {mz}]"
        )

    def set_motion(self, lane: LaneConfig, mx: float, my: float, mz: float) -> None:
        self.run(
            f"execute as {lane.selector} at @s run data modify entity @s Motion "
            f"set value [{mx:.3f}, {my:.3f}, {mz:.3f}]"
        )

    def _actionbar_selector(self) -> str:
        """Arena/reporter accounts only — builders elsewhere are not interrupted."""
        return arena_audience_selector()

    def announce(self, message: str, *, color: str = "green") -> None:
        if not self.config.actionbar_enabled:
            return
        safe = message.replace("\\", "\\\\").replace('"', '\\"')
        selector = self._actionbar_selector()
        self.run(
            f'title {selector} actionbar {{"text":"{safe}","color":"{color}","bold":true}}'
        )

    def update_race_bossbar(
        self,
        *,
        remaining_s: int,
        time_limit_seconds: int,
        create: bool = False,
    ) -> None:
        if not bossbar_enabled():
            return
        for command in build_bossbar_commands(
            remaining_s=remaining_s,
            time_limit_seconds=time_limit_seconds,
            create=create,
        ):
            self.run(command)

    def clear_race_bossbar(self) -> None:
        if not bossbar_enabled():
            return
        try:
            self.run(build_clear_bossbar_command())
        except Exception:
            pass

    def play_lap_sound(self) -> None:
        self.run("playsound minecraft:block.bell.use master @a")

    def play_finish_sound(self) -> None:
        self.run("playsound minecraft:ui.toast.challenge_complete master @a")
