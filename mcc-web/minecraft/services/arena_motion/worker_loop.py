# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    worker_loop.py
# @note    Arena motion worker loop driven by shared JSON control state.

from __future__ import annotations

import math
import os
import time
from typing import Any

from config.logger_utils import get_logger
from minecraft.services.arena_motion.controller import (
    CartState,
    RaceController,
    apply_places,
)
from minecraft.services.arena_motion.iot_update_sim import (
    DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
    clamp_send_interval,
    mps_from_pulse_meters,
    pulse_timed_out,
    simulate_iot_pulse_meters,
)
from minecraft.services.arena_motion.lanes import (
    LaneAssignment,
    load_race_config,
    motion_from_mps,
    motion_speed_for,
)
from minecraft.services.arena_motion.locked_rcon import LockedRconGateway
from minecraft.services.arena_motion.race_modes import (
    MODE_DUAL,
    MODE_LAPS,
    announce_dual_winners,
    default_race_mode,
    default_target_laps,
    default_time_limit_seconds,
    normalize_race_mode,
    ranks_by_velos,
    show_velos_live,
    show_velos_on_finish,
    uses_laps,
    uses_time_limit,
)
from minecraft.services.arena_motion import state as race_state

logger = get_logger("minecraft")


def _crossed_finish(state: CartState, curr_x: float, curr_z: float) -> bool:
    lane = state.lane
    if not (lane.finish_x_min <= curr_x <= lane.finish_x_max):
        return False
    return state.last_z < lane.finish_z_trigger <= curr_z


def _assignments_from_state(config, raw: list[dict[str, Any]]) -> tuple[LaneAssignment, ...]:
    from minecraft.services.arena_motion.cyclists import resolve_device_motion_params

    result: list[LaneAssignment] = []
    for entry in raw:
        lane = config.lane_by_key(str(entry.get("lane_id") or ""))
        cyclist = str(entry.get("cyclist") or "").strip()
        if lane is None or not cyclist:
            continue
        device_name = str(entry.get("device_name") or "").strip()
        device_factor = float(entry.get("device_factor", 1.0))
        send_interval = clamp_send_interval(
            entry.get("send_interval_seconds"),
            default=DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
        )
        if device_name:
            try:
                params = resolve_device_motion_params(device_name)
                device_factor = float(params["device_factor"])
                send_interval = clamp_send_interval(
                    params.get("send_interval_seconds"),
                    default=send_interval,
                )
            except ValueError:
                pass
        sim_rate = float(entry.get("sim_rate_mps", config.reference_mps))
        result.append(
            LaneAssignment(
                lane=lane,
                cyclist=cyclist,
                sim_rate_mps=sim_rate,
                device_factor=device_factor,
                device_name=device_name,
                send_interval_seconds=send_interval,
            )
        )
    return tuple(result)


def _publish_live(
    states: list[CartState],
    *,
    race_start: float | None,
    race_mode: str = MODE_LAPS,
    target_laps: int | None = None,
    time_limit_seconds: int | None = None,
    remaining_s: float | None = None,
) -> None:
    live: dict[str, Any] = {}
    show_live_velos = show_velos_live(race_mode)
    show_finish_velos = show_velos_on_finish(race_mode)
    track_laps = uses_laps(race_mode)
    laps_target = max(1, int(target_laps or 1)) if track_laps else None
    for state in states:
        finish_s = None
        if state.finished and state.finish_time is not None and race_start is not None:
            finish_s = round(state.finish_time - race_start, 2)
        velos = _display_velos(state)
        laps_done = (
            state.laps_completed(laps_target)
            if laps_target is not None
            else max(0, int(state.current_lap) - 1)
        )
        entry: dict[str, Any] = {
            "cyclist": state.cyclist,
            "place": state.place,
            "lap": state.current_lap,
            "laps_completed": laps_done,
            "finished": state.finished,
            "speed_kmh": round(state.last_speed_kmh, 1),
            "distance_m": int(round(state.distance_m)),
            "finish_time_s": finish_s,
        }
        if laps_target is not None:
            entry["target_laps"] = laps_target
        if show_live_velos or show_finish_velos:
            entry["velos"] = velos
        if remaining_s is not None:
            entry["remaining_s"] = max(0, int(round(remaining_s)))
        live[state.lane.id] = entry
    updates: dict[str, Any] = {
        "live": live,
        "worker_heartbeat": time.time(),
        "worker_pid": os.getpid(),
    }
    if time_limit_seconds is not None:
        updates["time_limit_seconds"] = int(time_limit_seconds)
    race_state.update_state(**updates)


def _display_velos(state: CartState) -> int:
    """Prefer session/pulse Velos; live_velos is kept in sync with the same meters."""
    return int(state.velos) if state.velos else int(state.live_velos)


class ArenaMotionWorker:
    """Poll control state; run motion race when started."""

    def __init__(self) -> None:
        self.config = load_race_config()
        self.gateway = LockedRconGateway(
            lock_path=self.config.rcon_lock_path,
            lock_timeout_seconds=self.config.rcon_lock_timeout_seconds,
            forbid_scoreboard=True,
        )
        self.controller = RaceController(self.gateway, self.config)
        self.states: list[CartState] = []
        self.race_start: float | None = None
        self.race_mode = default_race_mode()
        self.target_laps = default_target_laps()
        self.time_limit_seconds = default_time_limit_seconds()
        self.continue_after_finish = False
        self.official_ended = False
        self.sim_distance = False
        self.api_live_pulse = False
        self.pulse_by_lane: dict[str, Any] = {}
        self.official_finish_distance_m: int | None = None
        self.step = 0
        self._bossbar_remaining: int | None = None
        self._bossbar_updated_at: float = 0.0

    def connect(self) -> None:
        self.gateway.connect()

    def connect_with_retry(
        self,
        *,
        delay_seconds: float = 2.0,
        max_delay_seconds: float = 15.0,
    ) -> None:
        """
        Wait until Paper RCON accepts connections.

        A single ConnectionRefused during Paper restart must not kill the worker —
        Admin would then see a dead PID / stale \"already running\" until manual restart.
        """
        delay = max(0.5, float(delay_seconds))
        attempt = 0
        while True:
            attempt += 1
            try:
                self.gateway.connect()
                if attempt > 1:
                    logger.info("[arena_motion] RCON connected after %s attempt(s)", attempt)
                return
            except (ConnectionRefusedError, ConnectionError, OSError, TimeoutError) as exc:
                logger.warning(
                    "[arena_motion] waiting for Paper RCON (%s) attempt=%s sleep=%.1fs",
                    exc,
                    attempt,
                    delay,
                )
                race_state.update_state(
                    worker_heartbeat=time.time(),
                    worker_pid=os.getpid(),
                    last_error=f"Warte auf Paper-RCON: {exc}",
                )
                time.sleep(delay)
                delay = min(max_delay_seconds, delay * 1.5)

    def close(self) -> None:
        self.gateway.close()

    def _do_init(self, *, kill_all: bool = False) -> None:
        """
        Place assigned carts on the start rails.

        Existing tagged carts are teleported (passengers stay seated). Missing
        carts (e.g. after Reset) are summoned. kill_all is ignored — use Reset
        (clear_all) to remove carts when new avatars should be mounted later.
        """
        _ = kill_all  # legacy; Reset (clear_all) clears carts deliberately
        st = race_state.load_state()
        assignments = _assignments_from_state(self.config, st.get("assignments") or [])
        if not assignments:
            raise RuntimeError("Init ohne Zuweisungen nicht möglich")
        self.states = [CartState(assignment=a) for a in assignments]
        spawned = 0
        reused = 0
        for state in self.states:
            # No place ranking on the start line — only name until the race progresses.
            if self.controller.ensure_cart_at_start(
                state.lane,
                cyclist=state.cyclist,
                place=None,
            ):
                spawned += 1
            else:
                reused += 1
            # Double-stop: carts must wait for Start impulse.
            self.controller.stop_cart(state.lane)
        self.race_start = None
        self.step = 0
        self.official_finish_distance_m = None
        self.official_ended = False
        race_state.update_state(
            status=race_state.STATUS_IDLE,
            pending_command=None,
            initialized=True,
            live={},
            result={},
            last_error="",
        )
        self._clear_bossbar()
        self.controller.announce("Arena bereit (Init)")
        logger.info(
            "[arena_motion] init complete lanes=%s reused=%s spawned=%s",
            len(self.states),
            reused,
            spawned,
        )

    def _do_reset(self, *, kill_all: bool = False) -> None:
        """Legacy alias: Init (reposition/spawn), not clear_all."""
        self._do_init(kill_all=kill_all)

    def _do_clear_all(self) -> None:
        """Remove all arena minecarts; leave rails empty until Init."""
        for state in self.states:
            try:
                self.controller.stop_cart(state.lane)
            except Exception:
                pass
        self.controller.clear_arena_minecarts()
        self.states = []
        self.race_start = None
        self.step = 0
        race_state.update_state(
            status=race_state.STATUS_IDLE,
            pending_command=None,
            initialized=False,
            live={},
            last_error="",
        )
        self._clear_bossbar()
        self.controller.announce("Arena-Loren entfernt (Reset)", color="yellow")
        logger.info("[arena_motion] clear_all complete")

    def _do_start(self) -> None:
        """Start race motion on already-initialized carts (avatars stay mounted)."""
        st = race_state.load_state()
        assignments = _assignments_from_state(self.config, st.get("assignments") or [])
        if not assignments:
            raise RuntimeError("Start ohne Zuweisungen")
        if not st.get("initialized"):
            raise RuntimeError("Zuerst Init (Loren auf die Schienen)")
        self.race_mode = normalize_race_mode(st.get("race_mode"))
        self.target_laps = max(1, int(st.get("target_laps") or default_target_laps()))
        self.time_limit_seconds = max(
            30, int(st.get("time_limit_seconds") or default_time_limit_seconds())
        )
        self.continue_after_finish = bool(st.get("continue_after_finish", False))
        self.official_ended = False
        self.sim_distance = bool(st.get("sim_distance", False))
        self.api_live_pulse = bool(st.get("api_live_pulse", False))
        if self.sim_distance and self.api_live_pulse:
            raise RuntimeError("sim_distance und api_live_pulse gleichzeitig aktiv")
        self.pulse_by_lane = {}
        if self.api_live_pulse:
            from minecraft.services.arena_motion.api_pulse import resolve_pulse_targets

            for target in resolve_pulse_targets(st.get("assignments") or []):
                self.pulse_by_lane[target.lane_id] = target

        # Reuse carts from Init — do not kill/respawn (keeps cabin avatars seated).
        if not self.states or len(self.states) != len(assignments):
            self.states = [CartState(assignment=a) for a in assignments]
        else:
            # Refresh assignment metadata (cyclist/device) without respawning.
            by_lane = {a.lane.id: a for a in assignments}
            for state in self.states:
                refreshed = by_lane.get(state.lane.id)
                if refreshed is not None:
                    state.assignment = refreshed

        self._apply_places()
        for state in self.states:
            state.reset_race_progress()
            pos = self.controller.get_position(state.lane)
            if pos is None:
                raise RuntimeError(
                    f"Lore fehlt: {state.cyclist}@{state.lane.id} — bitte Init erneut."
                )
            state.last_x, state.last_z = pos
            # Clear previous race placement on the nameplate (name only until live ranking).
            try:
                self.controller.update_cart_label(
                    state.lane,
                    state.cyclist,
                    speed_kmh=None,
                    place=None,
                    force=True,
                    track=state,
                )
            except Exception as exc:
                logger.warning("[arena_motion] start label refresh failed: %s", exc)

        self.race_start = time.time()
        self.step = 0
        self.official_finish_distance_m = None
        for state in self.states:
            interval = clamp_send_interval(
                state.assignment.send_interval_seconds,
                default=DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
            )
            state.send_interval_seconds = interval
            if self.sim_distance or self.api_live_pulse:
                # Sim / API-Live writer: start with configured rate immediately.
                state.held_mps = state.assignment.motion_mps
                state.last_pulse_at = self.race_start
                state.next_pulse_at = self.race_start + interval
                speed = motion_speed_for(
                    self.config,
                    state.assignment,
                    use_distance=True,
                )
                state.target_speed = speed
                self.controller.apply_impulse(state.lane, speed)
            else:
                # Normal Velo-Arena: wait for real ESP32 /api/update-data pulses.
                state.held_mps = 0.0
                state.last_pulse_at = 0.0
                state.next_pulse_at = 0.0
                state.last_session_km = None
                state.target_speed = 0.0
                self.controller.stop_cart(state.lane)
            state.lap_start_time = self.race_start
            state.cooldown_ticks = self.config.lap_cooldown_ticks
            state.last_mx = state.lane.impulse_x if state.target_speed > 0 else 0.0
            state.last_mz = state.lane.impulse_z if state.target_speed > 0 else 0.0
            pos = self.controller.get_position(state.lane)
            if pos is not None:
                state.last_x, state.last_z = pos

        race_state.update_state(
            status=race_state.STATUS_RUNNING,
            pending_command=None,
            last_error="",
            result={},
            race_mode=self.race_mode,
            target_laps=self.target_laps,
            time_limit_seconds=self.time_limit_seconds,
        )
        self._publish()
        if uses_time_limit(self.race_mode):
            self._sync_bossbar(time.time(), force=True)
        intervals = ", ".join(
            f"{s.cyclist}={s.send_interval_seconds:.0f}s" for s in self.states
        )
        if uses_time_limit(self.race_mode):
            start_msg = f"Velo-Rennen gestartet ({self.time_limit_seconds}s)"
        elif self.race_mode == MODE_DUAL:
            start_msg = f"Doppel-Sieg gestartet ({self.target_laps} Runden)"
        else:
            start_msg = f"Rundenrennen gestartet ({self.target_laps} Runden)"
        self.controller.announce(start_msg)
        logger.info(
            "[arena_motion] race started mode=%s lanes=%s laps=%s limit=%ss sim=%s api_live=%s intervals=%s",
            self.race_mode,
            len(self.states),
            self.target_laps,
            self.time_limit_seconds,
            self.sim_distance,
            self.api_live_pulse,
            intervals,
        )

    def _emit_api_pulse(self, state: CartState, meters: float) -> None:
        """Send one station-sized distance packet through /api/update-data."""
        if not self.api_live_pulse or meters <= 0:
            return
        target = self.pulse_by_lane.get(state.lane.id)
        if target is None:
            return
        from minecraft.services.arena_motion.api_pulse import pulse_meters

        ok, err = pulse_meters(
            id_tag=target.id_tag,
            device_name=target.device_name,
            distance_m=meters,
        )
        if not ok:
            logger.warning(
                "[arena_motion] API-Live pulse failed lane=%s: %s",
                state.lane.id,
                err,
            )
            race_state.update_state(last_error=f"API-Live: {err}")

    def _read_session_km(self, state: CartState) -> float:
        """Current device-session km for the assigned cyclist (0 if no session)."""
        from api.models import Cyclist, CyclistDeviceCurrentMileage

        key = str(state.cyclist or "").strip()
        if not key:
            return 0.0
        cyclist = (
            Cyclist.objects.filter(user_id=key).first()
            or Cyclist.objects.filter(id_tag=key).first()
        )
        if cyclist is None:
            return 0.0
        try:
            session = cyclist.cyclistdevicecurrentmileage
        except CyclistDeviceCurrentMileage.DoesNotExist:
            return 0.0
        device_name = str(getattr(state.assignment, "device_name", "") or "").strip()
        if device_name and session.device_id and session.device.name != device_name:
            return float(state.last_session_km or 0.0)
        return float(session.cumulative_mileage or 0.0)

    def _apply_device_live_tick(self, state: CartState, *, now: float) -> None:
        """
        Normal Velo-Arena: Motion follows real /api/update-data session km.

        Carts stay still until the assigned device posts distance; then hold the
        implied m/s until the next pulse or a timeout.
        """
        interval = clamp_send_interval(
            state.send_interval_seconds,
            default=DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
        )
        state.send_interval_seconds = interval
        km = self._read_session_km(state)

        if state.last_session_km is None:
            state.last_session_km = km
            state.held_mps = 0.0
            state.target_speed = 0.0
            state.last_speed_kmh = 0.0
            return

        delta_km = max(0.0, km - float(state.last_session_km))
        if delta_km > 1e-9:
            meters = delta_km * 1000.0
            if state.last_pulse_at > 0:
                dt = max(now - float(state.last_pulse_at), self.config.tick_interval_seconds)
            else:
                dt = max(interval, self.config.tick_interval_seconds)
            state.held_mps = meters / max(dt, 1e-3)
            state.last_delta_m = meters
            # Authoritative race meters = session km (same source as OLED/session Velos).
            # Cart path length must NOT be added on top — that doubled ArenaLive Velos.
            state.distance_m += meters
            state.live_distance_m += meters
            state.last_pulse_at = now
            state.last_session_km = km
            state.refresh_velos()
            state.refresh_live_velos()
        elif pulse_timed_out(
            now=now,
            last_pulse_at=state.last_pulse_at,
            interval_s=interval,
        ):
            state.held_mps = 0.0
            state.last_delta_m = 0.0

        if state.held_mps > 0:
            state.target_speed = motion_from_mps(
                state.held_mps, max_motion=self.config.max_motion_speed
            )
            state.last_speed_kmh = state.held_mps * 3.6
        else:
            state.target_speed = 0.0
            state.last_speed_kmh = 0.0

    def _flush_iot_partial_distance(self, state: CartState, *, now: float) -> None:
        """
        Credit meters for the unfinished send interval when a lane finishes.

        Sparse pulses only land every send_interval_seconds; without a flush the
        last partial window would never count toward distance/Velos.
        """
        if not (self.sim_distance or self.api_live_pulse):
            return
        if state.last_pulse_at <= 0:
            return
        rate = max(0.0, float(state.held_mps or state.assignment.motion_mps))
        if rate <= 0:
            return
        elapsed = max(0.0, float(now) - float(state.last_pulse_at))
        if elapsed < 0.05:
            return
        meters = rate * elapsed
        if meters <= 0:
            return
        state.last_delta_m = meters
        state.distance_m += meters
        state.live_distance_m += meters
        state.last_pulse_at = now
        state.next_pulse_at = now + clamp_send_interval(
            state.send_interval_seconds,
            default=DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
        )
        self._emit_api_pulse(state, meters)
        state.refresh_velos()
        state.refresh_live_velos()

    def _apply_iot_distance_tick(self, state: CartState, *, now: float) -> None:
        """
        Sparse IoT updates + held Motion rate.

        Every send_interval_seconds: one distance packet (and optional update-data).
        Between pulses: keep held_mps so RCON Motion continues at ~tick rate.
        """
        interval = clamp_send_interval(
            state.send_interval_seconds,
            default=DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
        )
        state.send_interval_seconds = interval

        if now >= state.next_pulse_at:
            meters = simulate_iot_pulse_meters(
                motion_mps=state.assignment.motion_mps,
                interval_s=interval,
            )
            state.last_delta_m = meters
            state.distance_m += meters
            state.live_distance_m += meters
            state.held_mps = mps_from_pulse_meters(meters, interval)
            state.last_pulse_at = now
            state.next_pulse_at = now + interval
            self._emit_api_pulse(state, meters)
            state.refresh_velos()
            state.refresh_live_velos()
        elif pulse_timed_out(
            now=now,
            last_pulse_at=state.last_pulse_at,
            interval_s=interval,
        ):
            state.held_mps = 0.0
            state.last_delta_m = 0.0

        if state.held_mps > 0:
            state.target_speed = motion_from_mps(
                state.held_mps, max_motion=self.config.max_motion_speed
            )
            state.last_speed_kmh = state.held_mps * 3.6
        else:
            state.target_speed = 0.0
            state.last_speed_kmh = 0.0

    def _do_stop(self) -> None:
        for state in self.states:
            try:
                self.controller.stop_cart(state.lane)
            except Exception as exc:
                logger.warning("[arena_motion] stop_cart failed: %s", exc)
            state.last_speed_kmh = 0.0
            state.last_mx, state.last_mz = 0.0, 0.0
            state.held_mps = 0.0
            try:
                # Keep live place after stop; clear only the km/h line.
                self.controller.update_cart_label(
                    state.lane,
                    state.cyclist,
                    speed_kmh=None,
                    place=state.place if state.place else None,
                    force=True,
                    track=state,
                )
            except Exception as exc:
                logger.warning("[arena_motion] clear speed label failed: %s", exc)
        race_state.update_state(
            status=race_state.STATUS_IDLE,
            pending_command=None,
            api_live_pulse=False,
        )
        self._publish()
        self._clear_bossbar()
        logger.info("[arena_motion] race stopped")
        self.race_start = None
        self.official_ended = False
        self.api_live_pulse = False
        self.pulse_by_lane = {}

    def _apply_places(self) -> None:
        apply_places(
            self.states,
            self.target_laps,
            by_velos=ranks_by_velos(self.race_mode),
        )

    def _remaining_s(self, now: float | None = None) -> float | None:
        if not uses_time_limit(self.race_mode) or self.race_start is None:
            return None
        t = time.time() if now is None else now
        return max(0.0, float(self.time_limit_seconds) - (t - self.race_start))

    def _publish(self) -> None:
        remaining = self._remaining_s()
        _publish_live(
            self.states,
            race_start=self.race_start,
            race_mode=self.race_mode,
            target_laps=self.target_laps if uses_laps(self.race_mode) else None,
            time_limit_seconds=self.time_limit_seconds if uses_time_limit(self.race_mode) else None,
            remaining_s=remaining,
        )

    def _clear_bossbar(self) -> None:
        self.controller.clear_race_bossbar()
        self._bossbar_remaining = None
        self._bossbar_updated_at = 0.0

    def _sync_bossbar(self, now: float, *, force: bool = False) -> None:
        if not uses_time_limit(self.race_mode) or self.race_start is None:
            return
        remaining = self._remaining_s(now)
        if remaining is None:
            return
        rem_int = max(0, int(round(remaining)))
        if (
            not force
            and self._bossbar_remaining == rem_int
            and (now - self._bossbar_updated_at) < 1.0
        ):
            return
        create = self._bossbar_remaining is None
        self.controller.update_race_bossbar(
            remaining_s=rem_int,
            time_limit_seconds=self.time_limit_seconds,
            create=create,
        )
        self._bossbar_remaining = rem_int
        self._bossbar_updated_at = now

    def _label_velos_arg(self, state: CartState, *, finished: bool) -> int | None:
        if finished and show_velos_on_finish(self.race_mode):
            return _display_velos(state)
        if not finished and show_velos_live(self.race_mode):
            return _display_velos(state)
        return None

    def _laps_label_args(self, state: CartState) -> dict[str, int | None]:
        if not uses_laps(self.race_mode):
            return {"laps_completed": None, "target_laps": None}
        return {
            "laps_completed": state.laps_completed(self.target_laps),
            "target_laps": self.target_laps,
        }

    def _finish_lane(self, state: CartState, *, now: float, force_label: bool = True) -> None:
        """Mark one lane finished and update its nameplate."""
        if state.finished:
            return
        state.finished = True
        state.finish_time = now
        if not self.continue_after_finish:
            self.controller.stop_cart(state.lane)
        self._flush_iot_partial_distance(state, now=now)
        state.refresh_velos()
        state.refresh_live_velos()
        self._apply_places()
        finish_s = (
            (state.finish_time - self.race_start) if self.race_start is not None else None
        )
        laps_args = self._laps_label_args(state)
        self.controller.update_cart_label(
            state.lane,
            state.cyclist,
            place=state.place,
            final=True,
            finish_time_s=finish_s,
            velos=self._label_velos_arg(state, finished=True),
            force=force_label,
            track=state,
            **laps_args,
        )

    def _finish_all_for_time_limit(self, *, now: float) -> None:
        for state in self.states:
            if not state.finished:
                self._finish_lane(state, now=now)

    def _build_result(self) -> dict[str, Any]:
        self._apply_places()
        time_winner = None
        velo_winner = None
        if self.states:
            if ranks_by_velos(self.race_mode):
                velo_winner = max(self.states, key=lambda s: (_display_velos(s), s.distance_m))
            else:
                time_winner = min(self.states, key=lambda s: s.place)
                velo_winner = max(self.states, key=lambda s: (_display_velos(s), -s.place))
        result: dict[str, Any] = {
            "race_mode": self.race_mode,
            "target_laps": self.target_laps,
            "time_limit_seconds": self.time_limit_seconds,
        }
        if time_winner is not None and self.race_start is not None:
            finish_s = (
                round(time_winner.finish_time - self.race_start, 2)
                if time_winner.finish_time is not None
                else None
            )
            result["time_winner"] = {
                "cyclist": time_winner.cyclist,
                "lane_id": time_winner.lane.id,
                "finish_time_s": finish_s,
                "place": time_winner.place,
            }
        if velo_winner is not None:
            result["velo_winner"] = {
                "cyclist": velo_winner.cyclist,
                "lane_id": velo_winner.lane.id,
                "velos": _display_velos(velo_winner),
                "place": velo_winner.place,
            }
        result["lanes"] = [
            {
                "lane_id": s.lane.id,
                "cyclist": s.cyclist,
                "place": s.place,
                "velos": _display_velos(s),
                "distance_m": int(round(s.distance_m)),
                "finish_time_s": (
                    round(s.finish_time - self.race_start, 2)
                    if s.finish_time is not None and self.race_start is not None
                    else None
                ),
            }
            for s in self.states
        ]
        return result

    def _announce_race_end(self, total_s: float) -> None:
        result = self._build_result()
        if announce_dual_winners(self.race_mode):
            tw = result.get("time_winner") or {}
            vw = result.get("velo_winner") or {}
            time_txt = (
                f"{tw.get('cyclist', '?')} ({tw.get('finish_time_s', '?')}s)"
                if tw
                else "—"
            )
            velo_txt = (
                f"{vw.get('cyclist', '?')} ({vw.get('velos', 0)} Velos)"
                if vw
                else "—"
            )
            msg = f"Strecken-Sieger: {time_txt} · Velo-Sieger: {velo_txt}"
        elif ranks_by_velos(self.race_mode):
            vw = result.get("velo_winner") or {}
            msg = f"Velo-Sieger: {vw.get('cyclist', '?')} ({vw.get('velos', 0)} Velos)"
        else:
            tw = result.get("time_winner") or {}
            msg = (
                f"Sieg: {tw.get('cyclist', '?')} (Platz 1) — {tw.get('finish_time_s', total_s)}s"
            )
        self.controller.announce(msg, color="gold")
        race_state.update_state(result=result)

    def _refresh_live_sim_rates(self) -> None:
        """
        Pick up sim_rate_mps changes from shared state while a sim/API race runs.

        Operator can adjust rates via „Raten speichern“ without Stop/Start.
        """
        if not (self.sim_distance or self.api_live_pulse) or not self.states:
            return
        st = race_state.load_state()
        by_lane = {
            str(entry.get("lane_id") or "").strip(): entry
            for entry in (st.get("assignments") or [])
            if str(entry.get("lane_id") or "").strip()
        }
        for state in self.states:
            if state.finished and not self.continue_after_finish:
                continue
            entry = by_lane.get(state.lane.id)
            if entry is None:
                continue
            new_rate = float(entry.get("sim_rate_mps", state.assignment.sim_rate_mps))
            if abs(new_rate - float(state.assignment.sim_rate_mps)) < 1e-9:
                continue
            state.assignment = LaneAssignment(
                lane=state.assignment.lane,
                cyclist=state.assignment.cyclist,
                sim_rate_mps=new_rate,
                device_factor=state.assignment.device_factor,
                device_name=getattr(state.assignment, "device_name", "") or "",
                send_interval_seconds=getattr(
                    state.assignment, "send_interval_seconds", state.send_interval_seconds
                ),
            )
            # Operator rate change takes effect immediately for held Motion.
            state.held_mps = max(0.0, new_rate)

    def _tick(self) -> None:
        if not self.states or self.race_start is None:
            return
        self._refresh_live_sim_rates()
        config = self.config
        self.step += 1
        now = time.time()

        # Official time limit: score everyone, optionally keep coasting.
        if (
            uses_time_limit(self.race_mode)
            and not self.official_ended
            and now >= self.race_start + self.time_limit_seconds
        ):
            self._finish_all_for_time_limit(now=now)
            self._complete_race(now=now)
            if not self.continue_after_finish:
                return

        for state in self.states:
            hard_stopped = state.finished and not self.continue_after_finish
            if hard_stopped:
                continue
            if state.cooldown_ticks > 0:
                state.cooldown_ticks -= 1

            if self.sim_distance or self.api_live_pulse:
                self._apply_iot_distance_tick(state, now=now)
            else:
                self._apply_device_live_tick(state, now=now)

            pos = self.controller.get_position(state.lane)
            if pos is None:
                state.missing_ticks += 1
                if state.missing_ticks >= 20:
                    raise RuntimeError(
                        f"Lore nicht gefunden: {state.cyclist}@{state.lane.id} "
                        f"(tag={state.lane.tag})"
                    )
                continue
            state.missing_ticks = 0
            curr_x, curr_z = pos
            dx = curr_x - state.last_x
            dz = curr_z - state.last_z
            dist = math.sqrt(dx * dx + dz * dz)
            # Cart movement drives Motion direction / lap progress only.
            # Live meters + Velos stay on session/IoT pulses (see handlers above).

            if (
                not state.finished
                and state.cooldown_ticks == 0
                and self.step > config.lap_cooldown_ticks
                and _crossed_finish(state, curr_x, curr_z)
            ):
                self.controller.play_lap_sound()
                if uses_laps(self.race_mode) and state.current_lap >= self.target_laps:
                    self._finish_lane(state, now=now)
                else:
                    state.current_lap += 1
                    state.lap_start_time = now
                    state.cooldown_ticks = config.lap_cooldown_ticks

            if (not state.finished or self.continue_after_finish) and state.target_speed > 0:
                if dist > config.motion_min_distance:
                    # Follow current travel direction on the track.
                    mx = round((dx / dist) * state.target_speed, 3)
                    mz = round((dz / dist) * state.target_speed, 3)
                    self.controller.set_motion(state.lane, mx, 0.0, mz)
                    state.last_mx, state.last_mz = mx, mz
                else:
                    # Stationary after Start: kick with lane impulse so Motion can begin
                    # (device-live waits for pulses with speed>0 but dist==0 until then).
                    self.controller.apply_impulse(state.lane, state.target_speed)
                    state.last_mx = state.lane.impulse_x
                    state.last_mz = state.lane.impulse_z
            else:
                state.last_mx, state.last_mz = 0.0, 0.0

            # Device-live / IoT sim: km/h and official meters come from pulse handlers.
            # Do not overwrite with cart-block heuristics in those modes.
            if (
                not self.sim_distance
                and not self.api_live_pulse
                and state.last_pulse_at <= 0
                and not state.finished
            ):
                # Still waiting for the first device pulse — keep HUD speed at 0.
                state.last_speed_kmh = 0.0
            state.refresh_velos()

            state.progress_blocks += dist
            state.last_x, state.last_z = curr_x, curr_z

        # Live ranking every tick so place numbers track the race without needing Reset.
        self._apply_places()

        for state in self.states:
            laps_args = self._laps_label_args(state)
            if state.finished:
                finish_s = (
                    (state.finish_time - self.race_start)
                    if state.finish_time is not None
                    else None
                )
                moving_kmh = None
                if self.continue_after_finish and state.last_speed_kmh > 0:
                    moving_kmh = state.last_speed_kmh
                self.controller.update_cart_label(
                    state.lane,
                    state.cyclist,
                    place=state.place,
                    final=True,
                    finish_time_s=finish_s,
                    speed_kmh=moving_kmh,
                    velos=self._label_velos_arg(state, finished=True),
                    track=state,
                    **laps_args,
                )
            else:
                moving_kmh = state.last_speed_kmh if state.last_speed_kmh > 0 else None
                self.controller.update_cart_label(
                    state.lane,
                    state.cyclist,
                    speed_kmh=moving_kmh,
                    place=state.place,
                    velos=self._label_velos_arg(state, finished=False),
                    track=state,
                    **laps_args,
                )
        self._publish()
        if not self.official_ended:
            self._sync_bossbar(now)

        if (
            uses_laps(self.race_mode)
            and self.states
            and all(s.finished for s in self.states)
            and not self.official_ended
        ):
            self._complete_race(now=now)

    def _complete_race(self, *, now: float) -> None:
        if not self.states or self.race_start is None or self.official_ended:
            return
        self._apply_places()
        self.controller.play_finish_sound()
        total = round(now - self.race_start, 2)
        self._announce_race_end(total)
        self._publish()
        self._clear_bossbar()
        self.official_ended = True
        if self.continue_after_finish:
            # Keep RUNNING so carts still follow pedaling until operator Stop.
            race_state.update_state(pending_command=None)
            logger.info(
                "[arena_motion] soft finish mode=%s total=%ss (continue after finish)",
                self.race_mode,
                total,
            )
            return
        race_state.update_state(
            status=race_state.STATUS_IDLE,
            pending_command=None,
            api_live_pulse=False,
        )
        logger.info(
            "[arena_motion] race finished mode=%s total=%ss",
            self.race_mode,
            total,
        )
        self.race_start = None
        self.api_live_pulse = False
        self.pulse_by_lane = {}

    def process_pending(self) -> None:
        st = race_state.load_state()
        cmd = st.get("pending_command")
        if not cmd:
            return
        try:
            if cmd == "start":
                self._do_start()
            elif cmd == "stop":
                self._do_stop()
            elif cmd in ("init", "reset"):
                self._do_init(kill_all=bool(st.get("kill_all_on_reset", False)))
            elif cmd == "clear_all":
                self._do_clear_all()
            else:
                race_state.update_state(
                    pending_command=None,
                    last_error=f"Unbekannter Befehl: {cmd}",
                )
        except Exception as exc:
            logger.exception("[arena_motion] command %s failed", cmd)
            race_state.update_state(
                pending_command=None,
                status=race_state.STATUS_IDLE,
                last_error=str(exc),
            )

    def run_forever(self, *, poll_idle_seconds: float = 0.25) -> None:
        self.connect_with_retry()
        race_state.update_state(worker_heartbeat=time.time(), worker_pid=os.getpid(), last_error="")
        logger.info("[arena_motion] worker started config=%s", self.config.config_path)
        last_rcon_ping = 0.0
        try:
            while True:
                self.process_pending()
                st = race_state.load_state()
                now = time.time()
                # After Paper restart the TCP session can sit in CLOSE-WAIT while the
                # idle loop only writes heartbeats — probe RCON periodically.
                if now - last_rcon_ping >= 10.0:
                    if not self.gateway.ping():
                        race_state.update_state(
                            worker_heartbeat=now,
                            worker_pid=os.getpid(),
                            last_error="Paper-RCON nicht erreichbar — reconnect läuft",
                        )
                    else:
                        # Clear transient RCON wait errors once healthy again.
                        if str(st.get("last_error") or "").startswith(
                            ("Warte auf Paper-RCON", "Paper-RCON nicht erreichbar")
                        ):
                            race_state.update_state(last_error="")
                    last_rcon_ping = now
                if st.get("status") == race_state.STATUS_RUNNING and self.states:
                    self._tick()
                    time.sleep(self.config.tick_interval_seconds)
                else:
                    race_state.update_state(
                        worker_heartbeat=time.time(),
                        worker_pid=os.getpid(),
                    )
                    time.sleep(poll_idle_seconds)
        finally:
            self.close()
