#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    run_race_test.py
# @note    CLI for VeloArena minecart motion tests (no scoreboard/DB writes).
#
# Usage:
#   cp velo_arena_race.toml.example velo_arena_race.toml
#   python run_race_test.py --assign lane_1:anna --assign lane_2:ben --laps 1
#   python run_race_test.py --sim-distance \
#       --assign lane_1:anna --assign lane_2:ben \
#       --sim-rate anna=2.5 --sim-rate ben=1.2 \
#       --device-factor anna=1.0 --device-factor ben=1.3 --laps 3
#   python run_race_test.py --reset-only --lane lane_1 --lane lane_2

"""Motion-only VeloArena race test: lanes from TOML, cyclists from CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from race_config import (  # noqa: E402
    EXAMPLE_CONFIG_FILE,
    build_assignments,
    load_race_config,
    parse_rate_token,
)
from race_control import RaceController, run_race  # noqa: E402
from rcon_gateway import RconGateway, load_rcon_endpoint  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Testet die RCON-Bewegungssteuerung der VeloArena-Loren. "
            "Bahnen kommen aus der TOML-Config; aktive Radler per --assign. "
            "Schreibt keine Scoreboards und keine Django-Datenbankeinträge."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  %(prog)s --assign lane_1:anna --assign lane_2:ben --laps 1\n"
            "  %(prog)s --sim-distance --assign lane_1:anna --assign lane_2:ben "
            "--sim-rate anna=3 --sim-rate ben=1.2 --laps 5\n"
            "  %(prog)s --reset-only --lane lane_1 --lane lane_2\n"
            "  %(prog)s --kill-all-minecarts\n"
            "  %(prog)s --kill-all-minecarts --assign lane_1:anna --laps 1\n"
        ),
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Pfad zur TOML-Konfiguration (Default: velo_arena_race.toml).",
    )
    parser.add_argument(
        "--assign",
        action="append",
        dest="assigns",
        metavar="LANE:CYCLIST",
        help="Radler einer Bahn zuweisen (mehrfach). Format: lane_1:anna",
    )
    parser.add_argument(
        "--lane",
        action="append",
        dest="lanes",
        metavar="ID",
        help=(
            "Bahn für --reset-only/--stop-only (ohne Radler). "
            "Beim Rennen bitte --assign verwenden."
        ),
    )
    parser.add_argument(
        "--laps",
        type=int,
        default=1,
        help="Anzahl Runden pro Bahn (Default: 1).",
    )
    parser.add_argument(
        "--sim-distance",
        action="store_true",
        help=(
            "Distanz-Updates der Radler simulieren (ungleiche Raten möglich). "
            "Motion-Betrag folgt effective_mps = rate × device_factor."
        ),
    )
    parser.add_argument(
        "--sim-rate",
        action="append",
        dest="sim_rates",
        metavar="CYCLIST=MPS",
        help="Simulierte Distanzrate in m/s für einen Radler (mehrfach).",
    )
    parser.add_argument(
        "--device-factor",
        action="append",
        dest="device_factors",
        metavar="CYCLIST=FACTOR",
        help=(
            "Faktor für Radgröße/FKM-Unterschiede (Default 1.0). "
            "Wirkt nur mit --sim-distance."
        ),
    )
    parser.add_argument(
        "--sim-interval",
        action="append",
        dest="sim_intervals",
        metavar="CYCLIST=SECONDS",
        help=(
            "IoT-Sendeintervall in Sekunden für einen Radler (Default aus TOML "
            "sim_update_interval_seconds, meist 5). Wirkt nur mit --sim-distance."
        ),
    )
    parser.add_argument(
        "--kill-all-minecarts",
        action="store_true",
        help=(
            "Alle Minecarts im Spiel löschen (kill @e[type=minecart]). "
            "Allein nutzbar oder vor Rennen/--reset-only."
        ),
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Vor dem Start keine Loren neu spawnen.",
    )
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="Nur getaggte Loren auf Start setzen, kein Rennen.",
    )
    parser.add_argument(
        "--stop-only",
        action="store_true",
        help="Nur Motion der gewählten Loren auf 0 setzen.",
    )
    parser.add_argument(
        "--status-every",
        type=int,
        default=10,
        help="Konsolenstatus alle N Ticks (0=aus, Default: 10).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Zufalls-Seed für Distanz-Jitter.",
    )
    return parser.parse_args(argv)


def _parse_rate_map(tokens: list[str] | None) -> dict[str, float]:
    result: dict[str, float] = {}
    for token in tokens or []:
        name, value = parse_rate_token(token)
        result[name] = value
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.seed is not None:
        import random

        random.seed(args.seed)

    if args.laps < 1 and not (
        args.reset_only or args.stop_only or args.kill_all_minecarts
    ):
        print("Fehler: --laps muss >= 1 sein.", file=sys.stderr)
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

    print(f"Config: {race_config.config_path}")
    print(f"RCON:   {endpoint.host}:{endpoint.port}")
    print(
        "Bahnen: "
        + ", ".join(f"{lane.id}/{lane.tag}" for lane in race_config.lanes)
    )
    print(
        "Hinweis: keine Scoreboard-/DB-Schreibzugriffe; "
        "nur Minecart Motion/Position."
    )

    try:
        with RconGateway(
            endpoint,
            lock_path=race_config.rcon_lock_path,
            lock_timeout_seconds=race_config.rcon_lock_timeout_seconds,
        ) as gateway:
            listing = gateway.run("list")
            print(f"Server list: {listing or '(leer)'}")
            controller = RaceController(gateway, race_config)

            # Standalone: only wipe all minecarts on the server.
            if args.kill_all_minecarts and not (
                args.reset_only or args.stop_only or args.assigns
            ):
                print("Lösche ALLE Minecarts im Spiel …")
                resp = controller.kill_all_minecarts()
                print(f"  kill @e[type=minecart] → {resp or '(ok)'}")
                return 0

            if args.stop_only or args.reset_only:
                lanes = race_config.resolve_lanes(args.lanes)
                assign_by_lane: dict[str, str] = {}
                if args.assigns:
                    # Allow --assign as lane source for convenience.
                    assignments = build_assignments(
                        race_config,
                        args.assigns,
                        sim_rates={},
                        device_factors={},
                    )
                    lanes = tuple(a.lane for a in assignments)
                    assign_by_lane = {a.lane.id: a.cyclist for a in assignments}
                if not lanes:
                    print(
                        "Fehler: --lane oder --assign für Reset/Stop angeben.",
                        file=sys.stderr,
                    )
                    return 2
                if args.stop_only:
                    for lane in lanes:
                        controller.stop_cart(lane)
                        print(f"Gestoppt: {lane.id} ({lane.name})")
                    return 0
                if args.kill_all_minecarts:
                    print("Reset: ALLE Minecarts im Spiel löschen …")
                    resp = controller.kill_all_minecarts()
                    print(f"  kill @e[type=minecart] → {resp or '(ok)'}")
                else:
                    print("Reset: alle Minecarts in Bahn-Start-Chunks löschen …")
                    controller.clear_minecarts_in_lane_chunks(lanes)
                for lane in lanes:
                    cyclist_name = assign_by_lane.get(lane.id)
                    controller.reset_cart(
                        lane, clear_chunk=False, cyclist=cyclist_name
                    )
                    print(
                        f"Reset: {lane.id} → "
                        f"({lane.start_x}, {lane.start_y}, {lane.start_z})"
                        + (f" ← {cyclist_name}" if cyclist_name else "")
                    )
                return 0

            if not args.assigns:
                print(
                    "Fehler: Rennen benötigt --assign lane:cyclist "
                    "(Bahnen aus Config, Radler zur Laufzeit).",
                    file=sys.stderr,
                )
                return 2

            assignments = build_assignments(
                race_config,
                args.assigns,
                sim_rates=_parse_rate_map(args.sim_rates),
                device_factors=_parse_rate_map(args.device_factors),
                sim_intervals=_parse_rate_map(args.sim_intervals),
                spread_default_rates=args.sim_distance and not args.sim_rates,
            )
            print(
                "Zuweisung: "
                + ", ".join(
                    f"{a.lane.id}←{a.cyclist}" for a in assignments
                )
            )

            return run_race(
                controller,
                assignments,
                target_laps=args.laps,
                reset_before_start=not args.no_reset,
                status_every_ticks=max(0, args.status_every),
                sim_distance=args.sim_distance,
                kill_all_minecarts=args.kill_all_minecarts,
            )
    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer.")
        return 130
    except (TimeoutError, ConnectionError, RuntimeError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unerwarteter Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
