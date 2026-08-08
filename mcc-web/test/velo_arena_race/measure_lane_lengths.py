#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    measure_lane_lengths.py
# @note    Measure real VeloArena lane lengths by driving tagged minecarts via RCON.

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from race_config import EXAMPLE_CONFIG_FILE, LaneAssignment, LaneConfig, load_race_config  # noqa: E402
from race_control import RaceController  # noqa: E402
from rcon_gateway import RconGateway, load_rcon_endpoint  # noqa: E402


@dataclass
class LaneMeasureState:
    lane: LaneConfig
    last_x: float
    last_z: float
    distance_m: float = 0.0
    laps_done: int = 0
    finished: bool = False
    finish_time_s: float | None = None
    missing_ticks: int = 0
    cooldown_ticks: int = 0


def _crossed_finish(state: LaneMeasureState, curr_x: float, curr_z: float) -> bool:
    lane = state.lane
    if not (lane.finish_x_min <= curr_x <= lane.finish_x_max):
        return False
    return state.last_z < lane.finish_z_trigger <= curr_z


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Misst die reale Rundenlänge der Arena-Bahnen per RCON. "
            "Die Loren fahren eine oder mehrere Runden, und das Tool summiert "
            "die echte Weglänge aus den Positionsdaten."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  %(prog)s --laps 1\n"
            "  %(prog)s --lane lane_1 --lane lane_2 --laps 2\n"
            "  %(prog)s --speed-mps 2.0 --kill-all-minecarts\n"
        ),
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Pfad zur TOML-Konfiguration (Default: velo_arena_race.toml).",
    )
    parser.add_argument(
        "--lane",
        action="append",
        dest="lanes",
        metavar="ID",
        help="Nur bestimmte Bahnen messen (mehrfach). Default: alle Bahnen.",
    )
    parser.add_argument(
        "--laps",
        type=int,
        default=1,
        help="Anzahl Messrunden pro Bahn (Default: 1).",
    )
    parser.add_argument(
        "--speed-mps",
        type=float,
        default=2.0,
        help="Messgeschwindigkeit in m/s vor FKM/Handicap (Default: 2.0).",
    )
    parser.add_argument(
        "--kill-all-minecarts",
        action="store_true",
        help="Vorher alle Minecarts im Spiel löschen.",
    )
    parser.add_argument(
        "--status-every",
        type=int,
        default=20,
        help="Konsolenstatus alle N Ticks (0=aus, Default: 20).",
    )
    return parser.parse_args(argv)


def _motion_speed(controller: RaceController, lane: LaneConfig, speed_mps: float) -> float:
    assignment = LaneAssignment(
        lane=lane,
        cyclist="measure",
        sim_rate_mps=float(speed_mps),
        device_factor=1.0,
    )
    # Use the same motion mapping as the arena distance mode.
    from race_config import motion_speed_for

    return motion_speed_for(controller.config, assignment, use_distance=True)


def _measure_lanes(
    controller: RaceController,
    lanes: tuple[LaneConfig, ...],
    *,
    laps: int,
    speed_mps: float,
    status_every: int,
    kill_all_minecarts: bool,
) -> list[LaneMeasureState]:
    if kill_all_minecarts:
        print("Reset: ALLE Minecarts im Spiel löschen …")
        resp = controller.kill_all_minecarts()
        print(f"  kill @e[type=minecart] → {resp or '(ok)'}")
    else:
        print("Reset: Minecarts in Bahn-Start-Chunks löschen …")
        controller.clear_minecarts_in_lane_chunks(lanes)

    print("Reset: Mess-Loren an Startkoordinaten spawnen …")
    for lane in lanes:
        controller.reset_cart(lane, clear_chunk=False, cyclist=None)
        controller.stop_cart(lane)
        print(f"  {lane.id}: start=({lane.start_x}, {lane.start_y}, {lane.start_z})")
    time.sleep(0.3)

    states: list[LaneMeasureState] = []
    for lane in lanes:
        pos = controller.get_position(lane)
        if pos is None:
            raise RuntimeError(f"Mess-Lore auf {lane.id} nicht gefunden.")
        states.append(
            LaneMeasureState(
                lane=lane,
                last_x=pos[0],
                last_z=pos[1],
                cooldown_ticks=controller.config.lap_cooldown_ticks,
            )
        )

    race_start = time.time()
    target_speed_by_lane = {lane.id: _motion_speed(controller, lane, speed_mps) for lane in lanes}
    for lane in lanes:
        controller.apply_impulse(lane, target_speed_by_lane[lane.id])

    step = 0
    while True:
        time.sleep(controller.config.tick_interval_seconds)
        step += 1
        all_done = True

        for state in states:
            if state.finished:
                continue
            all_done = False
            if state.cooldown_ticks > 0:
                state.cooldown_ticks -= 1

            pos = controller.get_position(state.lane)
            if pos is None:
                state.missing_ticks += 1
                if state.missing_ticks >= 20:
                    raise RuntimeError(f"Lore auf {state.lane.id} nicht gefunden.")
                continue

            state.missing_ticks = 0
            curr_x, curr_z = pos
            dx = curr_x - state.last_x
            dz = curr_z - state.last_z
            dist = math.sqrt(dx * dx + dz * dz)
            state.distance_m += dist

            if (
                state.cooldown_ticks == 0
                and step > controller.config.lap_cooldown_ticks
                and _crossed_finish(state, curr_x, curr_z)
            ):
                state.laps_done += 1
                if state.laps_done >= laps:
                    state.finished = True
                    state.finish_time_s = time.time() - race_start
                    controller.stop_cart(state.lane)
                    print(
                        f"🏁 {state.lane.id}: {state.distance_m:.2f} m "
                        f"in {state.finish_time_s:.2f} s"
                    )
                else:
                    print(
                        f"↺ {state.lane.id}: Runde {state.laps_done}/{laps} "
                        f"bei {state.distance_m:.2f} m"
                    )
                    state.cooldown_ticks = controller.config.lap_cooldown_ticks

            if not state.finished and dist > controller.config.motion_min_distance:
                speed = target_speed_by_lane[state.lane.id]
                mx = round((dx / dist) * speed, 3)
                mz = round((dz / dist) * speed, 3)
                controller.set_motion(state.lane, mx, 0.0, mz)

            if status_every > 0 and step % status_every == 0:
                print(
                    f"Step {step:04d} | {state.lane.id:<7} | "
                    f"Dist={state.distance_m:6.2f} m | Pos=({curr_x:7.2f}, {curr_z:7.2f})"
                )
            state.last_x, state.last_z = curr_x, curr_z

        if all_done:
            return states


def _print_summary(states: list[LaneMeasureState]) -> None:
    distances = [s.distance_m for s in states if s.finish_time_s is not None]
    if not distances:
        print("Keine Ergebnisse.")
        return
    mean_m = statistics.mean(distances)
    median_m = statistics.median(distances)
    ref_m = median_m
    print("\nZusammenfassung")
    print("=" * 72)
    print(f"Mittelwert: {mean_m:.2f} m")
    print(f"Median:     {median_m:.2f} m")
    print(f"Referenz:   {ref_m:.2f} m (Median)")
    print("-" * 72)
    for state in sorted(states, key=lambda s: s.lane.id):
        delta = state.distance_m - ref_m
        finish_s = state.finish_time_s if state.finish_time_s is not None else float("nan")
        print(
            f"{state.lane.id:<7}  "
            f"{state.distance_m:7.2f} m  "
            f"Delta {delta:+6.2f} m  "
            f"Zeit {finish_s:6.2f} s"
        )
    print("-" * 72)
    spread = max(distances) - min(distances)
    print(f"Spannweite: {spread:.2f} m")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.laps < 1:
        print("Fehler: --laps muss >= 1 sein.", file=sys.stderr)
        return 2
    if args.speed_mps <= 0:
        print("Fehler: --speed-mps muss > 0 sein.", file=sys.stderr)
        return 2

    config_path = Path(args.config).expanduser().resolve() if args.config else None
    try:
        race_config = load_race_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        print(f"Vorlage: {EXAMPLE_CONFIG_FILE}", file=sys.stderr)
        return 2

    try:
        endpoint = load_rcon_endpoint()
    except RuntimeError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    lanes = race_config.resolve_lanes(args.lanes)
    print(f"Config: {race_config.config_path}")
    print(f"RCON:   {endpoint.host}:{endpoint.port}")
    print(f"Bahnen: {', '.join(l.id for l in lanes)}")
    print(f"Runden: {args.laps}")
    print(f"Messrate: {args.speed_mps:.2f} m/s")
    print("Hinweis: misst reale Loren-Bewegung per RCON, keine DB-/Scoreboard-Schreibzugriffe.")

    try:
        with RconGateway(
            endpoint,
            lock_path=race_config.rcon_lock_path,
            lock_timeout_seconds=race_config.rcon_lock_timeout_seconds,
        ) as gateway:
            print(f"Server list: {gateway.run('list') or '(leer)'}")
            controller = RaceController(gateway, race_config)
            states = _measure_lanes(
                controller,
                lanes,
                laps=args.laps,
                speed_mps=args.speed_mps,
                status_every=args.status_every,
                kill_all_minecarts=args.kill_all_minecarts,
            )
            _print_summary(states)
            return 0
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
