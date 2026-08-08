# VeloArena Race Motion Test

Standalone RCON test for minecart movement on the VeloArena
(Minecraft under `/data/games/mcc/mc-srv`, RCON via `/data/appl/mcc/.env`).

**Scope (strict):**

- Allowed: spawn/reset/tp tagged minecarts, read `Pos`, set `Motion`, optional actionbar/sound
- Forbidden: scoreboard writes, Django DB / Outbox / team registration changes

## Separation of concerns

| Source | Content |
|---|---|
| `velo_arena_race.toml` | Physical **lanes** only (coordinates, tags, finish line) |
| CLI `--assign` | Active **cyclists** bound to lanes at runtime |
| CLI `--sim-distance` | Simulated IoT distance updates (unequal rates) |

Later production: cyclists assigned in Minecraft/Game GUI; optional checkbox couples
Game Start with Arena Start. Devices need not be selected separately for arena motion —
distance updates already carry `device_id` + cyclist; wheel size/`device_factor` comes
from the sending device.

## Setup

```bash
cd mcc-web/test/velo_arena_race
cp velo_arena_race.toml.example velo_arena_race.toml
# Edit lane coordinates / tags in velo_arena_race.toml
pip install mcrcon   # if needed
```

RCON from environment or `mcc-web/.env`:

- `MCC_MINECRAFT_RCON_HOST` / `PORT` / `PASSWORD`

Keep your local `velo_arena_race.toml` when updating Python files.

**Note:** Minecart tags default to `velo_lane_1` … `velo_lane_4`. If your world still
uses `velo_speiche` etc., set `tag` in the TOML accordingly.

## Usage

```bash
# Fixed lane speed (no distance simulation)
python run_race_test.py \
  --assign lane_1:anna --assign lane_2:ben \
  --assign lane_3:clara --assign lane_4:dana \
  --laps 5

# Simulate unequal distance updates (+ optional wheel/FKM factors)
python run_race_test.py --sim-distance --laps 5 \
  --assign lane_1:anna --assign lane_2:ben \
  --assign lane_3:clara --assign lane_4:dana \
  --sim-rate anna=3.0 --sim-rate ben=1.2 \
  --sim-rate clara=2.0 --sim-rate dana=2.5 \
  --device-factor ben=1.3

# Without --sim-rate, --sim-distance spreads default rates automatically

# Reset / stop lanes only
python run_race_test.py --reset-only --lane lane_1 --lane lane_2
python run_race_test.py --stop-only --lane lane_1

# Measure real lane lengths via RCON
python measure_lane_lengths.py --laps 1
python measure_lane_lengths.py --lane lane_1 --lane lane_2 --speed-mps 2.0
```

`measure_lane_lengths.py` drives one or more lanes and sums the real cart path from
RCON positions. The summary prints meters per lane plus deviation from the median,
which is useful for detecting build errors or geometry drift.

## Start cleanup

- `--kill-all-minecarts` — deletes **every** minecart on the server
  (`kill @e[type=minecart]`). Use alone or together with a race / `--reset-only`.
- Without that flag, reset only clears minecarts in lane-start chunks (may miss carts).

```bash
python run_race_test.py --kill-all-minecarts
python run_race_test.py --kill-all-minecarts --assign lane_1:anna --laps 1
```

## Rider labels

Each assigned cyclist gets a short floating **text_display** on the minecart:

```text
1. Anna
12 km/h
```

Live place is ranked by completed laps, then track progress; finishers by finish
time. At race end the cart label shows place + finish time (`42.3s`).

### TOP-3 best times (no holograms)

After each race, finish times are merged into local `arena_best_times.json`
(fastest total times) and printed to the console. No floating podium
`text_display` entities are spawned in the arena.

**Production scoreboard modes** (Bau = Velos, Spectator/Race = TOP 3 sidebar)
and **production motion port (Prio 1)**:  
see [`docs/de/guides/velo_arena_scoreboard_modes.md`](../../docs/de/guides/velo_arena_scoreboard_modes.md)
and [`docs/de/guides/velo_arena_implementation.md`](../../docs/de/guides/velo_arena_implementation.md).

Optional world signs: `sign_x` / `sign_y` / `sign_z` per lane.

## Distance → Motion

```text
IoT pulse every send_interval (device or sim_update_interval_seconds)
  Δmeters = rate × interval (±jitter)
  held_mps = Δmeters / interval
Motion loop (~0.1 s): target_speed = clamp(held_mps / 20, min, max)
Direction from real cart movement (dist > motion_min_distance)
```

Between pulses the last rate is held so RCON Motion stays continuous.

## Coexistence with MCC scoreboard worker

File lock around each RCON command (`rcon_lock_path`). This harness never sends
`scoreboard …` commands.
