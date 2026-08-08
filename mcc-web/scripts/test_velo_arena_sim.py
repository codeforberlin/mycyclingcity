#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_velo_arena_sim.py
# @note    Standalone RCON simulation: drive 4 VeloArena minecarts from simulated velos.
#
# Usage examples:
#   cp scripts/velo_arena_sim.toml.example scripts/velo_arena_sim.toml
#   python scripts/test_velo_arena_sim.py --reset
#   python scripts/test_velo_arena_sim.py --rounds 3 --interval 0.5
#   python scripts/test_velo_arena_sim.py --config /path/to/velo_arena_sim.toml
#   MCC_MINECRAFT_RCON_HOST=127.0.0.1 python scripts/test_velo_arena_sim.py
#
"""Simulate trampling velos and teleport tagged minecarts along the VeloArena track.

Track layout and teams are configured in velo_arena_sim.toml (see .toml.example).

Lap counting (Runden):
  Place a detector rail on the start/finish line of each lane. Chain an impulse
  command block (needs redstone from the powered detector rail) with:

    scoreboard players add #Kette Runden 1
    tag @e[type=minecart,tag=team_kette,distance=..3,limit=1] add lap_counted
    scoreboard players reset #Kette lap_cd
    scoreboard players set #Kette lap_cd 20

  Use a repeating command block (always active) with cooldown debounce:

    execute if score #Kette lap_cd matches 1.. run scoreboard players remove #Kette lap_cd 1
    execute if score #Kette lap_cd matches 0 unless entity @e[type=minecart,tag=team_kette,tag=lap_counted,distance=..4] \
      run tag @e[type=minecart,tag=team_kette,distance=..4,limit=1] remove lap_counted

  Repeat for Kurbel / Speiche / Dynamo (#Kurbel, team_kurbel, …).

  This script reads `Runden` via RCON each tick. For pure simulation without
  physical rails, use --lap-source waypoint (increments scoreboard when the
  cart crosses the start/finish waypoint).
"""

from __future__ import annotations

import argparse
import math
import os
import random
import re
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = SCRIPT_DIR / "velo_arena_sim.toml"
EXAMPLE_CONFIG_FILE = SCRIPT_DIR / "velo_arena_sim.toml.example"

# ---------------------------------------------------------------------------
# Optional: load mcc-web/.env without requiring Django
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from nearby .env files if python-dotenv is absent."""
    candidates = [
        SCRIPT_DIR.parent / ".env",  # mcc-web/.env
        SCRIPT_DIR / ".env",
        Path.cwd() / ".env",
        Path.cwd() / "mcc-web" / ".env",
    ]
    try:
        from decouple import Config, RepositoryEnv  # type: ignore

        for path in candidates:
            if path.is_file():
                config = Config(RepositoryEnv(str(path)))
                for key in (
                    "MCC_MINECRAFT_RCON_HOST",
                    "MCC_MINECRAFT_RCON_PORT",
                    "MCC_MINECRAFT_RCON_PASSWORD",
                    "RCON_HOST",
                    "RCON_PORT",
                    "RCON_PASSWORD",
                ):
                    try:
                        value = config(key)
                    except Exception:
                        continue
                    if value is not None and key not in os.environ:
                        os.environ[key] = str(value)
                return
    except Exception:
        pass

    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
        break


_load_dotenv()

_SCOREBOARD_VALUE_RE = re.compile(r"has\s+(-?\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class TeamTrack:
    """One arena lane / minecart."""

    name: str
    color: str
    tag: str
    start_x: float
    start_y: float
    start_z: float
    minecart_type: str
    yaw: float = 0.0
    pitch: float = 0.0

    @property
    def selector(self) -> str:
        return f"@e[type={self.minecart_type},tag={self.tag},limit=1]"


@dataclass(frozen=True)
class ArenaConfig:
    """VeloArena track layout loaded from velo_arena_sim.toml."""

    config_path: Path
    velos_per_block: float
    minecart_type: str
    scoreboard_objective: str
    laps_scoreboard_objective: str
    lap_cooldown_objective: str
    figure8_waypoints: tuple[tuple[float, float, float], ...]
    teams: tuple[TeamTrack, ...]


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Konfiguration '{key}' fehlt oder ist kein Abschnitt.")
    return value


def _parse_waypoints(raw_waypoints: Any) -> tuple[tuple[float, float, float], ...]:
    if not isinstance(raw_waypoints, list) or len(raw_waypoints) < 2:
        raise ValueError("Mindestens zwei figure8_waypoints erforderlich.")
    waypoints: list[tuple[float, float, float]] = []
    for index, entry in enumerate(raw_waypoints):
        if not isinstance(entry, dict):
            raise ValueError(f"figure8_waypoints[{index}] muss ein Objekt sein.")
        try:
            waypoints.append(
                (float(entry["x"]), float(entry["y"]), float(entry["z"]))
            )
        except KeyError as exc:
            raise ValueError(
                f"figure8_waypoints[{index}] benötigt x, y und z."
            ) from exc
    return tuple(waypoints)


def _parse_teams(raw_teams: Any, minecart_type: str) -> tuple[TeamTrack, ...]:
    if not isinstance(raw_teams, list) or not raw_teams:
        raise ValueError("Mindestens ein Team unter [[teams]] erforderlich.")
    teams: list[TeamTrack] = []
    for index, entry in enumerate(raw_teams):
        if not isinstance(entry, dict):
            raise ValueError(f"teams[{index}] muss ein Objekt sein.")
        required = ("name", "color", "tag", "start_x", "start_y", "start_z")
        missing = [key for key in required if key not in entry]
        if missing:
            raise ValueError(
                f"teams[{index}] fehlt: {', '.join(missing)}"
            )
        teams.append(
            TeamTrack(
                name=str(entry["name"]),
                color=str(entry["color"]),
                tag=str(entry["tag"]),
                start_x=float(entry["start_x"]),
                start_y=float(entry["start_y"]),
                start_z=float(entry["start_z"]),
                minecart_type=str(entry.get("minecart_type", minecart_type)),
                yaw=float(entry.get("yaw", 0.0)),
                pitch=float(entry.get("pitch", 0.0)),
            )
        )
    return tuple(teams)


def load_arena_config(config_path: Path | None = None) -> ArenaConfig:
    """Load VeloArena layout from TOML configuration file."""
    path = config_path or DEFAULT_CONFIG_FILE
    if not path.is_file():
        if config_path is None and EXAMPLE_CONFIG_FILE.is_file():
            print(
                f"Hinweis: {DEFAULT_CONFIG_FILE.name} nicht gefunden, "
                f"verwende {EXAMPLE_CONFIG_FILE.name}. "
                f"Kopieren Sie die Datei für lokale Anpassungen.",
                file=sys.stderr,
            )
            path = EXAMPLE_CONFIG_FILE
        else:
            raise FileNotFoundError(
                f"Konfigurationsdatei nicht gefunden: {path}"
            )

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    scoreboard = _require_mapping(data, "scoreboard")
    minecart_type = str(data.get("minecart_type", "minecart"))
    return ArenaConfig(
        config_path=path,
        velos_per_block=float(data.get("velos_per_block", 2.0)),
        minecart_type=minecart_type,
        scoreboard_objective=str(scoreboard.get("velos", "Velos")),
        laps_scoreboard_objective=str(scoreboard.get("laps", "Runden")),
        lap_cooldown_objective=str(scoreboard.get("lap_cooldown", "lap_cd")),
        figure8_waypoints=_parse_waypoints(data.get("figure8_waypoints")),
        teams=_parse_teams(data.get("teams"), minecart_type),
    )


def resolve_config_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    return Path(raw_path).expanduser().resolve()


# ---------------------------------------------------------------------------
# RCON helpers
# ---------------------------------------------------------------------------


def _env_str(*keys: str, default: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _env_int(*keys: str, default: int) -> int:
    raw = _env_str(*keys, default=str(default))
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class RconConfig:
    host: str
    port: int
    password: str


def load_rcon_config() -> RconConfig:
    """Read RCON settings using mcc-web names first, then generic fallbacks."""
    return RconConfig(
        host=_env_str("MCC_MINECRAFT_RCON_HOST", "RCON_HOST", default="localhost"),
        port=_env_int("MCC_MINECRAFT_RCON_PORT", "RCON_PORT", default=25575),
        password=_env_str(
            "MCC_MINECRAFT_RCON_PASSWORD",
            "RCON_PASSWORD",
            default="mcc_rcon_password",
        ),
    )


class RconClient:
    """Thin wrapper around mcrcon with a clear connection error surface."""

    def __init__(self, config: RconConfig):
        self.config = config
        self._mcr = None
        self._command: Callable[[str], str] | None = None

    def connect(self) -> None:
        try:
            from mcrcon import MCRcon  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Paket 'mcrcon' fehlt. Installieren mit: pip install mcrcon"
            ) from exc

        mcr = MCRcon(self.config.host, self.config.password, port=self.config.port)
        try:
            mcr.connect()
        except Exception as exc:
            raise ConnectionError(
                f"RCON-Verbindung fehlgeschlagen ({self.config.host}:{self.config.port}): {exc}"
            ) from exc
        self._mcr = mcr
        self._command = mcr.command

    def close(self) -> None:
        if self._mcr is not None:
            try:
                self._mcr.disconnect()
            except Exception:
                pass
        self._mcr = None
        self._command = None

    def __enter__(self) -> "RconClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(self, command: str) -> str:
        if self._command is None:
            raise RuntimeError("RCON nicht verbunden")
        response = self._command(command)
        return response or ""


# ---------------------------------------------------------------------------
# Figure-8 path helpers
# ---------------------------------------------------------------------------


def _segment_lengths(waypoints: Sequence[tuple[float, float, float]]) -> list[float]:
    lengths: list[float] = []
    for index in range(len(waypoints) - 1):
        x0, y0, z0 = waypoints[index]
        x1, y1, z1 = waypoints[index + 1]
        lengths.append(math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2))
    return lengths


def path_total_length(waypoints: Sequence[tuple[float, float, float]]) -> float:
    return sum(_segment_lengths(waypoints))


def absolute_waypoints(
    team: TeamTrack,
    figure8_waypoints: Sequence[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    return [
        (team.start_x + dx, team.start_y + dy, team.start_z + dz)
        for dx, dy, dz in figure8_waypoints
    ]


def position_on_path(
    waypoints: Sequence[tuple[float, float, float]],
    distance: float,
) -> tuple[float, float, float, float]:
    """Return x, y, z and yaw (degrees) at `distance` blocks along the closed path."""
    if len(waypoints) < 2:
        x, y, z = waypoints[0]
        return x, y, z, 0.0

    segment_lengths = _segment_lengths(waypoints)
    total = sum(segment_lengths)
    if total <= 0:
        x, y, z = waypoints[0]
        return x, y, z, 0.0

    remaining = distance % total
    for index, seg_len in enumerate(segment_lengths):
        if remaining <= seg_len or index == len(segment_lengths) - 1:
            x0, y0, z0 = waypoints[index]
            x1, y1, z1 = waypoints[index + 1]
            if seg_len <= 0:
                t = 0.0
            else:
                t = remaining / seg_len
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            z = z0 + (z1 - z0) * t
            yaw = math.degrees(math.atan2(-(x1 - x0), z1 - z0))
            return x, y, z, yaw
        remaining -= seg_len

    x, y, z = waypoints[-1]
    return x, y, z, 0.0


# ---------------------------------------------------------------------------
# Simulation state
# ---------------------------------------------------------------------------


@dataclass
class TeamState:
    track: TeamTrack
    arena: ArenaConfig
    velos: float = 0.0
    path_distance: float = 0.0
    laps: int = 0
    x: float = field(init=False)
    y: float = field(init=False)
    z: float = field(init=False)
    yaw: float = field(init=False)

    def __post_init__(self) -> None:
        self._sync_position_from_distance()

    def _track_waypoints(self) -> list[tuple[float, float, float]]:
        return absolute_waypoints(self.track, self.arena.figure8_waypoints)

    def _sync_position_from_distance(self) -> None:
        self.x, self.y, self.z, self.yaw = position_on_path(
            self._track_waypoints(),
            self.path_distance,
        )

    def apply_velos(self, gained: float) -> None:
        self.velos += max(0.0, gained)
        self.path_distance = self.velos / self.arena.velos_per_block
        self._sync_position_from_distance()

    def tp_command(self) -> str:
        t = self.track
        return (
            f"tp {t.selector} {self.x:.3f} {self.y:.3f} {self.z:.3f} "
            f"{self.yaw:.1f} {t.pitch:.1f}"
        )

    def scoreboard_name(self) -> str:
        # Fake player with # prefix avoids colliding with real logins.
        return f"#{self.track.name}"

    def laps_from_path(self, lap_length: float) -> int:
        if lap_length <= 0:
            return 0
        return int(self.path_distance // lap_length)


def parse_scoreboard_value(response: str) -> int | None:
    match = _SCOREBOARD_VALUE_RE.search(response)
    if not match:
        return None
    return int(match.group(1))


def read_lap_score(rcon: RconClient, state: TeamState) -> int:
    objective = state.arena.laps_scoreboard_objective
    response = rcon.run(
        f"scoreboard players get {state.scoreboard_name()} {objective}"
    )
    value = parse_scoreboard_value(response)
    if value is None:
        return state.laps
    return max(0, value)


def ensure_scoreboards(rcon: RconClient, arena: ArenaConfig) -> None:
    rcon.run(
        f'scoreboard objectives add {arena.scoreboard_objective} dummy "Velos"'
    )
    rcon.run(
        f'scoreboard objectives add {arena.laps_scoreboard_objective} dummy "Runden"'
    )
    rcon.run(
        f'scoreboard objectives add {arena.lap_cooldown_objective} dummy "Lap CD"'
    )
    rcon.run(
        f"scoreboard objectives setdisplay sidebar {arena.laps_scoreboard_objective}"
    )


def reset_carts(
    rcon: RconClient,
    states: list[TeamState],
    *,
    reset_laps: bool,
) -> None:
    print("Reset: Minecarts → Startboxen")
    for state in states:
        arena = state.arena
        state.velos = 0.0
        state.path_distance = 0.0
        state.laps = 0
        state._sync_position_from_distance()
        cmd = state.tp_command()
        resp = rcon.run(cmd)
        rcon.run(
            f"scoreboard players set {state.scoreboard_name()} "
            f"{arena.scoreboard_objective} 0"
        )
        if reset_laps:
            rcon.run(
                f"scoreboard players set {state.scoreboard_name()} "
                f"{arena.laps_scoreboard_objective} 0"
            )
            rcon.run(
                f"scoreboard players set {state.scoreboard_name()} "
                f"{arena.lap_cooldown_objective} 0"
            )
            rcon.run(f"tag {state.track.selector} remove lap_counted")
        print(f"  [{state.track.color}] {state.track.name}: {cmd} → {resp or '(ok)'}")


def increment_lap_scoreboard(rcon: RconClient, state: TeamState) -> None:
    objective = state.arena.laps_scoreboard_objective
    rcon.run(
        f"scoreboard players add {state.scoreboard_name()} {objective} 1"
    )


def sync_laps_from_scoreboard(rcon: RconClient, state: TeamState) -> int:
    previous = state.laps
    state.laps = read_lap_score(rcon, state)
    if state.laps > previous:
        print(
            f"  ↻ {state.track.name}: Runde {state.laps} "
            f"(Detector/Scoreboard)"
        )
    return state.laps


def sync_laps_from_waypoint(
    rcon: RconClient,
    state: TeamState,
    *,
    lap_length: float,
    update_scoreboard: bool,
) -> None:
    computed = state.laps_from_path(lap_length)
    while state.laps < computed:
        state.laps += 1
        if update_scoreboard:
            increment_lap_scoreboard(rcon, state)
        print(
            f"  ↻ {state.track.name}: Runde {state.laps} "
            f"(Wegpunkt-Simulation)"
        )


def bar(value: float, maximum: float, width: int = 20) -> str:
    if maximum <= 0:
        return "[" + ("-" * width) + "]"
    filled = int(round(min(1.0, value / maximum) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def print_table(
    states: list[TeamState],
    *,
    target_laps: int,
    lap_length: float,
    step: int,
) -> None:
    velos_per_block = states[0].arena.velos_per_block if states else 0.0
    print(
        f"\n── Tick {step} ──  {velos_per_block} Velos/Block  "
        f"Bahn={lap_length:.0f}m  Ziel={target_laps} Runden"
    )
    print(
        f"{'Team':<10} {'Farbe':<8} {'Velos':>8} {'Runden':>7} "
        f"{'Strecke':>8} {'Pos':>24} Fortschritt"
    )
    for state in states:
        pos = f"{state.x:.1f} {state.y:.1f} {state.z:.1f}"
        lap_progress = (state.path_distance % lap_length) / lap_length if lap_length else 0.0
        print(
            f"{state.track.name:<10} {state.track.color:<8} "
            f"{state.velos:8.1f} {state.laps:7d} "
            f"{state.path_distance % lap_length:8.1f} {pos:>24} "
            f"{bar(lap_progress, 1.0)}"
        )


def simulate_gain() -> float:
    """Random trampling progress for one interval (1–5 velos)."""
    return float(random.randint(1, 5))


def race_finished(states: list[TeamState], *, target_laps: int, win_mode: str) -> bool:
    if win_mode == "all":
        return all(state.laps >= target_laps for state in states)
    return any(state.laps >= target_laps for state in states)


def winning_teams(states: list[TeamState], *, target_laps: int, win_mode: str) -> list[TeamState]:
    if win_mode == "all":
        if all(state.laps >= target_laps for state in states):
            return list(states)
        return []
    return [state for state in states if state.laps >= target_laps]


def run_race(
    rcon: RconClient,
    states: list[TeamState],
    *,
    interval: float,
    target_laps: int,
    win_mode: str,
    max_velos: float | None,
    update_scoreboard: bool,
    lap_source: str,
) -> None:
    arena = states[0].arena
    ensure_scoreboards(rcon, arena)
    lap_length = path_total_length(arena.figure8_waypoints)
    step = 0
    win_desc = "alle Teams" if win_mode == "all" else "erstes Team"
    print(
        f"Rennen gestartet (Ziel={target_laps} Runden, {win_desc}, "
        f"Intervall={interval}s, Rundenquelle={lap_source}). "
        "Strg+C zum Abbrechen."
    )
    while True:
        step += 1
        for state in states:
            gained = simulate_gain()
            state.apply_velos(gained)
            resp = rcon.run(state.tp_command())
            if update_scoreboard:
                rcon.run(
                    f"scoreboard players set {state.scoreboard_name()} "
                    f"{arena.scoreboard_objective} {int(state.velos)}"
                )
            if resp and "No entity" in resp:
                print(
                    f"  WARN {state.track.name}: Minecart nicht gefunden "
                    f"(tag={state.track.tag}). Antwort: {resp}"
                )

            if lap_source == "scoreboard":
                sync_laps_from_scoreboard(rcon, state)
            else:
                sync_laps_from_waypoint(
                    rcon,
                    state,
                    lap_length=lap_length,
                    update_scoreboard=update_scoreboard,
                )

        print_table(
            states,
            target_laps=target_laps,
            lap_length=lap_length,
            step=step,
        )

        winners = winning_teams(states, target_laps=target_laps, win_mode=win_mode)
        if winners:
            names = ", ".join(f"{s.track.name} ({s.track.color})" for s in winners)
            print(
                f"\nZiel erreicht nach {step} Ticks: {names} "
                f"mit {target_laps} Runde(n)."
            )
            break

        if max_velos is not None:
            leader = max(states, key=lambda s: s.velos)
            if leader.velos >= max_velos and not race_finished(
                states, target_laps=target_laps, win_mode=win_mode
            ):
                print(
                    f"\nAbbruch: max-velos={max_velos:.0f} erreicht, "
                    f"aber noch nicht genug Runden gezählt. "
                    f"Detector-Schienen / Scoreboard prüfen."
                )
                break

        time.sleep(interval)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simuliert erstrampelte Velos und teleportiert die 4 VeloArena-Minecarts "
            "per RCON entlang einer Achter-Rundenstrecke. Runden werden über "
            "Detector-Schienen (Scoreboard) oder optional Wegpunkte gezählt."
        )
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help=(
            f"Pfad zur TOML-Konfiguration "
            f"(Default: {DEFAULT_CONFIG_FILE.name} oder .example)."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Minecarts auf Start setzen; Velos und Runden-Scoreboard auf 0.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Pause zwischen Ticks in Sekunden (Default: 0.5).",
    )
    parser.add_argument(
        "--rounds",
        "--target-laps",
        dest="target_laps",
        type=int,
        default=3,
        help="Anzahl Runden bis zum Sieg (Default: 3).",
    )
    parser.add_argument(
        "--win-mode",
        choices=("first", "all"),
        default="first",
        help="first = Sieg bei erstem Team mit N Runden; all = alle Teams (Default: first).",
    )
    parser.add_argument(
        "--max-velos",
        type=float,
        default=None,
        help="Optional: Abbruch wenn Velos-Obergrenze erreicht, Runden aber fehlen.",
    )
    parser.add_argument(
        "--lap-source",
        choices=("scoreboard", "waypoint"),
        default="scoreboard",
        help=(
            "scoreboard = Runden aus Minecraft-Scoreboard (Detector-Schienen); "
            "waypoint = Runden beim Überqueren der Start/Ziel-Linie simulieren."
        ),
    )
    parser.add_argument(
        "--no-scoreboard",
        action="store_true",
        help="Kein Scoreboard-Update per RCON.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optionaler Zufalls-Seed für reproduzierbare Läufe.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.seed is not None:
        random.seed(args.seed)
    if args.interval <= 0:
        print("Fehler: --interval muss > 0 sein.", file=sys.stderr)
        return 2
    if args.target_laps <= 0:
        print("Fehler: --rounds muss > 0 sein.", file=sys.stderr)
        return 2
    if args.max_velos is not None and args.max_velos <= 0:
        print("Fehler: --max-velos muss > 0 sein.", file=sys.stderr)
        return 2

    try:
        arena = load_arena_config(resolve_config_path(args.config))
    except (FileNotFoundError, ValueError) as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    rcon_config = load_rcon_config()
    states = [TeamState(track=team, arena=arena) for team in arena.teams]
    lap_length = path_total_length(arena.figure8_waypoints)

    print(f"Konfiguration: {arena.config_path}")
    print(
        f"RCON Ziel: {rcon_config.host}:{rcon_config.port} "
        f"(Passwort {'gesetzt' if rcon_config.password else 'LEER'})"
    )
    print("Teams:", ", ".join(f"{t.name}/{t.tag}" for t in arena.teams))
    print(
        f"Skalierung: {arena.velos_per_block} Velos = 1 Block  |  "
        f"Bahnlänge ≈ {lap_length:.0f} m  |  Ziel: {args.target_laps} Runden"
    )
    print(f"Rundenquelle: {args.lap_source}")

    try:
        with RconClient(rcon_config) as rcon:
            print("RCON-Verbindung: OK")
            listing = rcon.run("list")
            print(f"Server list: {listing or '(leer)'}")

            if not args.no_scoreboard:
                ensure_scoreboards(rcon, arena)

            if args.reset:
                reset_carts(rcon, states, reset_laps=True)
                print("Reset abgeschlossen.")
                return 0

            reset_carts(rcon, states, reset_laps=True)
            run_race(
                rcon,
                states,
                interval=args.interval,
                target_laps=args.target_laps,
                win_mode=args.win_mode,
                max_velos=args.max_velos,
                update_scoreboard=not args.no_scoreboard,
                lap_source=args.lap_source,
            )
    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer (KeyboardInterrupt).")
        return 130
    except ConnectionError as exc:
        print(f"Verbindungsfehler: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unerwarteter Fehler: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
