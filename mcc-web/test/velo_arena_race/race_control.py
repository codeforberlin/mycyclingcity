# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    race_control.py
# @note    Motion-only VeloArena race controller (RCON). No scoreboard/DB writes.

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field

from race_config import (
    LaneAssignment,
    LaneConfig,
    RaceConfig,
    motion_speed_for,
)
from best_times import (
    BestTimeEntry,
    load_best_times,
    merge_race_results,
    save_best_times,
)
from iot_update_sim import (
    clamp_send_interval,
    mps_from_pulse_meters,
    pulse_timed_out,
    simulate_iot_pulse_meters,
)
from rcon_gateway import RconGateway

_POS_RE = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+")


@dataclass
class CartState:
    assignment: LaneAssignment
    last_x: float = field(init=False)
    last_z: float = field(init=False)
    current_lap: int = 1
    finished: bool = False
    cooldown_ticks: int = 0
    lap_start_time: float = field(default_factory=time.time)
    last_mx: float = 0.0
    last_mz: float = 0.0
    missing_ticks: int = 0
    distance_m: float = 0.0
    last_delta_m: float = 0.0
    target_speed: float = 0.0
    progress_blocks: float = 0.0
    finish_time: float | None = None
    place: int = 1
    last_speed_kmh: float = 0.0
    send_interval_seconds: float = 5.0
    held_mps: float = 0.0
    next_pulse_at: float = 0.0
    last_pulse_at: float = 0.0

    def __post_init__(self) -> None:
        lane = self.assignment.lane
        self.last_x = lane.start_x
        self.last_z = lane.start_z

    @property
    def lane(self) -> LaneConfig:
        return self.assignment.lane

    @property
    def cyclist(self) -> str:
        return self.assignment.cyclist

    @property
    def label(self) -> str:
        return f"{self.cyclist}@{self.lane.id}"

    def laps_completed(self, target_laps: int) -> int:
        if self.finished:
            return target_laps
        return max(0, self.current_lap - 1)


def compute_places(states: list[CartState], target_laps: int) -> dict[str, int]:
    """
    Rank carts: more completed laps first; then track progress; finishers by time.
    Returns mapping lane.id -> place (1 = leader).
    """
    def sort_key(state: CartState) -> tuple:
        laps = state.laps_completed(target_laps)
        if state.finished:
            # Earlier finish = better among equal lap counts.
            return (-laps, state.finish_time if state.finish_time is not None else 1e18)
        return (-laps, -state.progress_blocks)

    ordered = sorted(states, key=sort_key)
    return {state.lane.id: index + 1 for index, state in enumerate(ordered)}


def apply_places(states: list[CartState], target_laps: int) -> None:
    places = compute_places(states, target_laps)
    for state in states:
        state.place = places.get(state.lane.id, 1)


class RaceController:
    """Drive tagged minecarts via Motion updates; count laps locally."""

    def __init__(self, gateway: RconGateway, config: RaceConfig):
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
        """Minecraft chunk origin (multiples of 16) for a block/entity coordinate."""
        return math.floor(coord / 16.0) * 16

    def kill_all_minecarts(self) -> str:
        """Kill every minecart entity on the server (all worlds loaded for @e)."""
        resp = self.run("kill @e[type=minecart]")
        # Also remove arena name labels (text displays / legacy armor stands).
        self.run("kill @e[type=text_display,tag=velo_label]")
        self.run("kill @e[type=armor_stand,tag=velo_label]")
        # Remove leftover TOP-3 holograms from older test runs (feature removed).
        self.run("kill @e[type=text_display,tag=velo_podium]")
        time.sleep(0.25)
        return resp or ""

    @staticmethod
    def label_tag(lane: LaneConfig) -> str:
        """Stable tag for the floating name entity of a lane."""
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in lane.id)
        return f"velo_label_{safe}"

    @staticmethod
    def _mc_color(color: str) -> str:
        allowed = {
            "black",
            "dark_blue",
            "dark_green",
            "dark_aqua",
            "dark_red",
            "dark_purple",
            "gold",
            "gray",
            "dark_gray",
            "blue",
            "green",
            "aqua",
            "red",
            "light_purple",
            "yellow",
            "white",
        }
        key = (color or "white").strip().lower()
        # German aliases used in older configs
        aliases = {
            "blau": "blue",
            "grün": "green",
            "gruen": "green",
            "gelb": "yellow",
            "rot": "red",
            "weiss": "white",
            "weiß": "white",
        }
        key = aliases.get(key, key)
        return key if key in allowed else "white"

    @staticmethod
    def _sanitize_display_name(value: str, *, max_len: int = 16) -> str:
        """Short plain rider name for in-world display (no JSON noise)."""
        cleaned = "".join(
            ch for ch in (value or "").strip() if ch.isprintable() and ch not in "'\"\\\n\r"
        )
        if not cleaned:
            cleaned = "?"
        return cleaned[:max_len]

    def clear_lane_label(self, lane: LaneConfig) -> None:
        tag = self.label_tag(lane)
        self.run(f"kill @e[type=text_display,tag={tag}]")
        self.run(f"kill @e[type=armor_stand,tag={tag}]")

    @staticmethod
    def _format_label_text(
        name: str,
        color: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
        final: bool = False,
        finish_time_s: float | None = None,
    ) -> str:
        """SNBT `text:` field: place + name, optional speed / final time."""
        if place is not None and place > 0:
            title = f"{place}. {name}"
        else:
            title = name
        if final:
            if finish_time_s is not None:
                time_str = f"{max(0.0, float(finish_time_s)):.1f}s"
            else:
                time_str = "—"
            return (
                "text:["
                f'{{text:"{title}",color:"{color}",bold:1b}},'
                f'{{text:"\\n{time_str}",color:"gold",bold:1b}}'
                "]"
            )
        if speed_kmh is None:
            return f'text:{{text:"{title}",color:"{color}",bold:1b}}'
        speed_str = f"{max(0.0, float(speed_kmh)):.0f} km/h"
        return (
            "text:["
            f'{{text:"{title}",color:"{color}",bold:1b}},'
            f'{{text:"\\n{speed_str}",color:"yellow"}}'
            "]"
        )

    def set_cart_rider_name(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
    ) -> None:
        """
        Attach a short floating name above the minecart.

        Uses a text_display passenger (Paper 1.19.4+) so only the rider name is
        shown – CustomName on the minecart itself often renders as raw JSON.
        """
        if not self.config.cart_name_visible:
            return

        name = self._sanitize_display_name(cyclist.strip() or lane.name)
        color = self._mc_color(lane.color)
        tag = self.label_tag(lane)
        self.clear_lane_label(lane)

        self.run(
            f"data modify entity {lane.selector} CustomNameVisible set value 0b"
        )

        label_text = self._format_label_text(
            name, color, speed_kmh=speed_kmh, place=place
        )
        nbt = (
            "{"
            f'Tags:["velo_label","{tag}"],'
            'billboard:"center",'
            "shadow:1b,"
            "see_through:0b,"
            "background:0,"
            "transformation:{"
            "translation:[0f,1.4f,0f],"
            "left_rotation:[0f,0f,0f,1f],"
            "scale:[2.2f,2.2f,2.2f],"
            "right_rotation:[0f,0f,0f,1f]"
            "},"
            f"{label_text}"
            "}"
        )
        self.run(
            f"summon text_display {lane.start_x} {lane.start_y + 1.0} {lane.start_z} {nbt}"
        )
        ride = self.run(
            f"ride @e[type=text_display,tag={tag},limit=1] mount {lane.selector}"
        )
        print(f"  Label {lane.id}: „{name}“ → {ride or '(ok)'}")

    def update_cart_label(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = None,
        place: int | None = None,
        final: bool = False,
        finish_time_s: float | None = None,
    ) -> None:
        """Refresh floating label (place, name, speed/time) without re-summoning."""
        if not self.config.cart_name_visible:
            return
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
        )
        value = formatted[len("text:") :]
        self.run(
            f"data modify entity @e[type=text_display,tag={tag},limit=1] "
            f"text set value {value}"
        )

    def update_cart_label_speed(
        self,
        lane: LaneConfig,
        cyclist: str,
        speed_kmh: float,
        *,
        place: int | None = None,
    ) -> None:
        """Compatibility wrapper: update name + speed (+ optional place)."""
        self.update_cart_label(
            lane, cyclist, speed_kmh=speed_kmh, place=place, final=False
        )

    def set_lane_sign(self, lane: LaneConfig, cyclist: str) -> None:
        """Write short cyclist name onto the lane's world sign (1.20+ front_text)."""
        if not lane.has_sign:
            return
        assert lane.sign_x is not None and lane.sign_y is not None and lane.sign_z is not None
        color = self._mc_color(lane.color)
        name = self._sanitize_display_name(cyclist.strip() or lane.name)
        sx = int(math.floor(lane.sign_x))
        sy = int(math.floor(lane.sign_y))
        sz = int(math.floor(lane.sign_z))
        # Compound-style messages where possible; string JSON as fallback only.
        cmd = (
            f"data merge block {sx} {sy} {sz} "
            f"{{front_text:{{messages:["
            f'{{text:"{name}",color:"{color}",bold:1b}},'
            f'{{text:""}},{{text:""}},{{text:""}}'
            f"]}}}}"
        )
        resp = self.run(cmd)
        print(
            f"  Schild {lane.id} @ ({sx},{sy},{sz}) ← {name} "
            f"→ {resp or '(ok)'}"
        )

    def apply_rider_labels(
        self,
        lane: LaneConfig,
        cyclist: str,
        *,
        speed_kmh: float | None = 0.0,
        place: int | None = None,
    ) -> None:
        """Floating place+name+speed on cart + optional world sign."""
        self.set_cart_rider_name(
            lane, cyclist, speed_kmh=speed_kmh, place=place
        )
        self.set_lane_sign(lane, cyclist)

    def update_best_times_from_race(
        self,
        states: list[CartState],
        *,
        race_start: float,
        target_laps: int,
    ) -> list[BestTimeEntry]:
        """Merge this race into local TOP-3 JSON (console only, no holograms)."""
        results: list[tuple[str, float, int]] = []
        for state in states:
            if state.finish_time is None:
                continue
            results.append(
                (
                    state.cyclist,
                    float(state.finish_time - race_start),
                    target_laps,
                )
            )
        path = self.config.best_times_file
        existing = load_best_times(path)
        top, improved = merge_race_results(existing, results=results, keep=3)
        save_best_times(path, top)
        print(f"TOP-3 gespeichert: {path}")
        for entry in top:
            print(f"  {entry.time_s:6.1f}s  {entry.cyclist}")
        if improved:
            names = ", ".join(e.cyclist for e in improved)
            print(f"  Neu/verbessert in TOP 3: {names}")
            self.announce(f"TOP 3: {names}", color="gold")
        return top

    def clear_minecarts_in_lane_chunks(
        self,
        lanes: tuple[LaneConfig, ...] | list[LaneConfig],
        *,
        y_pad: float = 32.0,
    ) -> list[tuple[int, int, int]]:
        """
        Kill ALL minecarts in each unique chunk that contains a lane start.

        Uses the start coordinates from the lane config (same chunk as defined
        in TOML). Does not touch minecarts outside those chunks.
        """
        chunks: dict[tuple[int, int], tuple[float, float]] = {}
        for lane in lanes:
            cx = self.chunk_origin(lane.start_x)
            cz = self.chunk_origin(lane.start_z)
            # Keep a representative Y from the first lane in this chunk.
            chunks.setdefault((cx, cz), (lane.start_y, lane.start_y))

        cleared: list[tuple[int, int, int]] = []
        for (cx, cz), (y_ref, _) in chunks.items():
            y0 = int(math.floor(y_ref - y_pad))
            dy = int(math.ceil(2 * y_pad))
            # Selector covers the full 16×16 chunk in X/Z around the start chunk.
            cmd = (
                f"kill @e[type=minecart,x={cx},y={y0},z={cz},dx=15,dy={dy},dz=15]"
            )
            resp = self.run(cmd)
            print(
                f"  Chunk ({cx}, {cz}): alle Minecarts gelöscht "
                f"→ {resp or '(ok)'}"
            )
            cleared.append((cx, y0, cz))
        if cleared:
            time.sleep(0.2)
        return cleared

    def reset_cart(
        self,
        lane: LaneConfig,
        *,
        clear_chunk: bool = False,
        cyclist: str | None = None,
        place: int | None = None,
    ) -> None:
        """Summon a fresh tagged cart at the lane start (optionally clear chunk first)."""
        if clear_chunk:
            self.clear_minecarts_in_lane_chunks([lane])
        # Summon with Tags only – keep NBT minimal so Motion physics stay reliable.
        self.run(
            f"summon minecart {lane.start_x} {lane.start_y} {lane.start_z} "
            f'{{Tags:["{lane.tag}"]}}'
        )
        self.run(
            f"tp {lane.selector} {lane.start_x} {lane.start_y} {lane.start_z} "
            f"{lane.yaw} {lane.pitch}"
        )
        if cyclist:
            self.apply_rider_labels(
                lane, cyclist, speed_kmh=0.0, place=place
            )

    def stop_cart(self, lane: LaneConfig) -> None:
        self.run(
            f"execute as {lane.selector} run data modify entity @s Motion "
            f"set value [0.0, 0.0, 0.0]"
        )

    def apply_impulse(self, lane: LaneConfig, speed: float) -> None:
        ix, iy, iz = lane.impulse_x, lane.impulse_y, lane.impulse_z
        length = math.sqrt(ix * ix + iy * iy + iz * iz)
        if length <= 1e-9:
            ix, iy, iz = 0.0, 0.0, 1.0
            length = 1.0
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

    def announce(self, message: str, *, color: str = "green") -> None:
        if not self.config.actionbar_enabled:
            return
        safe = message.replace("\\", "\\\\").replace('"', '\\"')
        self.run(
            f'title @a actionbar {{"text":"{safe}","color":"{color}","bold":true}}'
        )

    def play_lap_sound(self) -> None:
        self.run("playsound minecraft:block.bell.use master @a")

    def play_finish_sound(self) -> None:
        self.run("playsound minecraft:ui.toast.challenge_complete master @a")


def apply_iot_distance_tick(
    state: CartState,
    *,
    now: float,
    config: RaceConfig,
) -> None:
    """Sparse IoT pulse + hold last m/s for continuous RCON Motion."""
    interval = clamp_send_interval(state.send_interval_seconds)
    state.send_interval_seconds = interval
    if now >= state.next_pulse_at:
        meters = simulate_iot_pulse_meters(
            motion_mps=state.assignment.motion_mps,
            interval_s=interval,
        )
        state.last_delta_m = meters
        state.distance_m += meters
        state.held_mps = mps_from_pulse_meters(meters, interval)
        state.last_pulse_at = now
        state.next_pulse_at = now + interval
    elif pulse_timed_out(
        now=now,
        last_pulse_at=state.last_pulse_at,
        interval_s=interval,
    ):
        state.held_mps = 0.0
        state.last_delta_m = 0.0

    if state.held_mps > 0:
        # Same mapping as arena_motion: Motion = m/s / 20 (1 block = 1 m).
        motion = state.held_mps / 20.0
        state.target_speed = max(
            config.min_motion_speed,
            min(config.max_motion_speed, motion),
        )
        state.last_speed_kmh = state.held_mps * 3.6
    else:
        state.target_speed = 0.0
        state.last_speed_kmh = 0.0


def _crossed_finish(state: CartState, curr_x: float, curr_z: float) -> bool:
    lane = state.lane
    if not (lane.finish_x_min <= curr_x <= lane.finish_x_max):
        return False
    return state.last_z < lane.finish_z_trigger <= curr_z


def run_race(
    controller: RaceController,
    assignments: tuple[LaneAssignment, ...],
    *,
    target_laps: int,
    reset_before_start: bool = True,
    status_every_ticks: int = 10,
    sim_distance: bool = False,
    kill_all_minecarts: bool = False,
) -> int:
    """
    Run a multi-lane, multi-lap motion race with optional distance simulation.

    Returns process exit code (0 = all finished, 1 = cart lost / error).
    """
    config = controller.config
    if target_laps < 1:
        raise ValueError("target_laps muss >= 1 sein")
    if not assignments:
        raise ValueError("Keine Bahn-Zuweisungen")

    states = [CartState(assignment=a) for a in assignments]

    if reset_before_start:
        lanes = tuple(state.lane for state in states)
        if kill_all_minecarts:
            print("Reset: ALLE Minecarts im Spiel löschen …")
            resp = controller.kill_all_minecarts()
            print(f"  kill @e[type=minecart] → {resp or '(ok)'}")
        else:
            print("Reset: alle Minecarts in Bahn-Start-Chunks löschen …")
            controller.clear_minecarts_in_lane_chunks(lanes)
        print("Reset: Arena-Loren an Startkoordinaten spawnen …")
        apply_places(states, target_laps)
        for state in states:
            controller.reset_cart(
                state.lane,
                clear_chunk=False,
                cyclist=state.cyclist,
                place=state.place,
            )
            print(
                f"  [{state.lane.color}] {state.lane.id} ({state.lane.name}) "
                f"← {state.cyclist}  tag={state.lane.tag} @ "
                f"({state.lane.start_x}, {state.lane.start_y}, {state.lane.start_z})"
            )
        time.sleep(0.3)

    mode = "Distanz-Simulation" if sim_distance else "feste Bahn-Geschwindigkeit"
    print(
        f"Startimpuls für {len(states)} Lore(n), Ziel={target_laps} Runde(n), "
        f"Modus={mode}"
    )
    if sim_distance:
        for state in states:
            a = state.assignment
            print(
                f"  {state.cyclist}: rate={a.sim_rate_mps:.2f} m/s × "
                f"device={a.device_factor:.2f} → {a.effective_mps:.2f} m/s, "
                f"IoT-Intervall={a.send_interval_seconds:.0f}s"
            )

    race_start = time.time()
    for state in states:
        speed = motion_speed_for(
            config, state.assignment, use_distance=sim_distance
        )
        state.target_speed = speed
        controller.apply_impulse(state.lane, speed)
        state.lap_start_time = race_start
        state.cooldown_ticks = config.lap_cooldown_ticks
        if sim_distance:
            interval = clamp_send_interval(state.assignment.send_interval_seconds)
            state.send_interval_seconds = interval
            state.held_mps = state.assignment.motion_mps
            state.last_pulse_at = race_start
            state.next_pulse_at = race_start + interval
            state.last_speed_kmh = state.held_mps * 3.6
        pos = controller.get_position(state.lane)
        if pos is not None:
            state.last_x, state.last_z = pos
        state.last_mx = state.lane.impulse_x
        state.last_mz = state.lane.impulse_z

    step = 0
    while True:
        time.sleep(config.tick_interval_seconds)
        step += 1
        all_done = True
        now = time.time()

        for state in states:
            if state.finished:
                continue
            all_done = False

            if state.cooldown_ticks > 0:
                state.cooldown_ticks -= 1

            # Sparse IoT update-data simulation; RCON Motion holds last rate.
            if sim_distance:
                apply_iot_distance_tick(state, now=now, config=config)
            else:
                state.target_speed = state.lane.base_speed

            pos = controller.get_position(state.lane)
            if pos is None:
                state.missing_ticks += 1
                if state.missing_ticks >= 20:
                    print(
                        f"FEHLER: Lore '{state.label}' "
                        f"(tag={state.lane.tag}) nicht gefunden."
                    )
                    return 1
                continue
            state.missing_ticks = 0
            curr_x, curr_z = pos

            dx = curr_x - state.last_x
            dz = curr_z - state.last_z
            dist = math.sqrt(dx * dx + dz * dz)

            if (
                state.cooldown_ticks == 0
                and step > config.lap_cooldown_ticks
                and _crossed_finish(state, curr_x, curr_z)
            ):
                lap_time = round(time.time() - state.lap_start_time, 2)
                print(
                    f"🏁 {state.label}: Runde {state.current_lap}/{target_laps} "
                    f"in {lap_time}s  Pos=({curr_x:.2f}, {curr_z:.2f})  "
                    f"Dist={state.distance_m:.1f}m"
                )
                controller.play_lap_sound()
                controller.announce(
                    f"{state.cyclist}: Runde {state.current_lap}/{target_laps} "
                    f"({lap_time}s)"
                )
                if state.current_lap >= target_laps:
                    state.finished = True
                    state.finish_time = time.time()
                    controller.stop_cart(state.lane)
                    apply_places(states, target_laps)
                    finish_s = state.finish_time - race_start
                    controller.update_cart_label(
                        state.lane,
                        state.cyclist,
                        place=state.place,
                        final=True,
                        finish_time_s=finish_s,
                    )
                    print(
                        f"✔ {state.label}: Ziel erreicht "
                        f"(Platz {state.place}, {finish_s:.1f}s), Lore gestoppt."
                    )
                else:
                    state.current_lap += 1
                    state.lap_start_time = time.time()
                    state.cooldown_ticks = config.lap_cooldown_ticks

            # Motion: direction from real movement; magnitude from distance/fixed speed.
            # Never force +Z when nearly still (that caused jitter).
            if (
                not state.finished
                and state.target_speed > 0
                and dist > config.motion_min_distance
            ):
                mx = round((dx / dist) * state.target_speed, 3)
                mz = round((dz / dist) * state.target_speed, 3)
                controller.set_motion(state.lane, mx, 0.0, mz)
                state.last_mx, state.last_mz = mx, mz

            state.progress_blocks += dist
            if not sim_distance:
                state.last_speed_kmh = dist / config.tick_interval_seconds * 3.6

            if status_every_ticks > 0 and step % status_every_ticks == 0:
                extra = ""
                if sim_distance:
                    extra = (
                        f" | IoT={state.send_interval_seconds:.0f}s "
                        f"Σ={state.distance_m:.1f}m "
                        f"held={state.held_mps:.2f}m/s"
                    )
                print(
                    f"Step {step:04d} | P{state.place} | "
                    f"{state.cyclist:<10}@{state.lane.id:<7} | "
                    f"R{state.current_lap}/{target_laps} | "
                    f"Pos ({curr_x:7.2f}, {curr_z:7.2f}) | "
                    f"v≈{state.target_speed:.3f} | ~{state.last_speed_kmh:4.1f} km/h"
                    f"{extra}"
                )

            state.last_x, state.last_z = curr_x, curr_z

        label_every = status_every_ticks if status_every_ticks > 0 else 5
        if step % label_every == 0:
            apply_places(states, target_laps)
            for state in states:
                if state.finished:
                    finish_s = (
                        (state.finish_time - race_start)
                        if state.finish_time is not None
                        else None
                    )
                    controller.update_cart_label(
                        state.lane,
                        state.cyclist,
                        place=state.place,
                        final=True,
                        finish_time_s=finish_s,
                    )
                else:
                    controller.update_cart_label(
                        state.lane,
                        state.cyclist,
                        speed_kmh=state.last_speed_kmh,
                        place=state.place,
                    )

        if all_done:
            total = round(time.time() - race_start, 2)
            apply_places(states, target_laps)
            print(f"\n🏆 Alle Bahnen fertig. Gesamtzeit ≈ {total}s")
            print("Finale Platzierung:")
            for state in sorted(states, key=lambda s: s.place):
                finish_s = (
                    round(state.finish_time - race_start, 2)
                    if state.finish_time is not None
                    else None
                )
                print(
                    f"  {state.place}. {state.cyclist} "
                    f"({state.lane.name}) — "
                    f"{finish_s if finish_s is not None else '?'}s"
                )
                controller.update_cart_label(
                    state.lane,
                    state.cyclist,
                    place=state.place,
                    final=True,
                    finish_time_s=finish_s,
                )
            try:
                controller.update_best_times_from_race(
                    states,
                    race_start=race_start,
                    target_laps=target_laps,
                )
            except OSError as exc:
                print(f"Warnung: TOP-3 konnte nicht gespeichert werden: {exc}")
            if sim_distance:
                print("Distanzbilanz:")
                for state in states:
                    print(
                        f"  {state.cyclist}: {state.distance_m:.1f} m "
                        f"(rate={state.assignment.sim_rate_mps:.2f} × "
                        f"device={state.assignment.device_factor:.2f})"
                    )
            controller.play_finish_sound()
            leader = min(states, key=lambda s: s.place)
            controller.announce(
                f"Sieg: {leader.cyclist} (Platz 1) — {total}s",
                color="gold",
            )
            gw = controller.gateway
            if gw.lock_wait_count:
                print(
                    f"RCON-Lock: {gw.lock_wait_count}× gewartet, "
                    f"Summe {gw.lock_wait_ms_total:.0f} ms | "
                    f"Befehle={gw.command_count}"
                )
            else:
                print(f"RCON-Befehle={gw.command_count}, Lock ohne Wartezeit")
            return 0
