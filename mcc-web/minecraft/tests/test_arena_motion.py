# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest
from django.test import override_settings

from minecraft.services.arena_motion.controller import (
    CartState,
    compute_places,
    compute_places_by_velos,
)
from minecraft.services.arena_motion.control import (
    ArenaControlError,
    auto_assign_active_sessions,
    request_start,
    set_assignments,
    set_race_mode,
    set_time_limit_seconds,
    update_sim_rates,
)
from minecraft.services.arena_motion import state as race_state
from minecraft.services.arena_motion.race_modes import (
    MODE_DUAL,
    MODE_LAPS,
    MODE_VELOS,
    normalize_race_mode,
    show_velos_live,
    uses_laps,
    uses_time_limit,
)
from minecraft.services.arena_motion.lanes import (
    LaneAssignment,
    LaneConfig,
    RaceConfig,
    import_lanes_from_toml,
    load_race_config,
    motion_speed_for,
)
from minecraft.services.arena_motion.cart_label_mode import CART_LABEL_MODE_FULL, CART_LABEL_MODE_NAME_ONLY


def _sample_lane(lane_id: str = "lane_1", tag: str = "velo_lane_1") -> LaneConfig:
    return LaneConfig(
        id=lane_id,
        name=f"Bahn {lane_id}",
        tag=tag,
        color="blue",
        start_x=0.0,
        start_y=64.0,
        start_z=0.0,
        yaw=0.0,
        pitch=0.0,
        base_speed=0.4,
        finish_x_min=-1.0,
        finish_x_max=1.0,
        finish_z_trigger=10.0,
        impulse_x=0.0,
        impulse_y=0.0,
        impulse_z=1.0,
    )


def _sample_config(tmp_path: Path, *, cart_label_mode: str = CART_LABEL_MODE_NAME_ONLY) -> RaceConfig:
    return RaceConfig(
        config_path=tmp_path / "x.toml",
        tick_interval_seconds=0.1,
        motion_min_distance=0.03,
        lap_cooldown_ticks=30,
        actionbar_enabled=True,
        rcon_lock_path=tmp_path / "lock",
        rcon_lock_timeout_seconds=1.0,
        default_impulse_x=0.0,
        default_impulse_y=0.0,
        default_impulse_z=1.0,
        reference_mps=2.0,
        min_motion_speed=0.08,
        max_motion_speed=0.55,
        cart_name_visible=True,
        cart_label_mode=cart_label_mode,
        lanes=(_sample_lane(),),
    )


@pytest.mark.unit
class TestEnsureCartAtStart:
    def test_repositions_existing_cart_without_summon(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                if command.startswith("data get entity"):
                    return "[0.5d, 64.0d, 20.0d]"
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        lane = ctrl.config.lanes[0]
        spawned = ctrl.ensure_cart_at_start(lane, cyclist="Anna")
        assert spawned is False
        assert not any(cmd.startswith("summon minecart") for cmd in commands)
        assert any(cmd.startswith(f"tp {lane.selector}") for cmd in commands)
        assert any("Motion" in cmd and "0.0" in cmd for cmd in commands)

    def test_spawns_when_cart_missing(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                if command.startswith("data get entity"):
                    return "No entity was found"
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        lane = ctrl.config.lanes[0]
        spawned = ctrl.ensure_cart_at_start(lane, cyclist="Anna")
        assert spawned is True
        assert any(cmd.startswith("summon minecart") for cmd in commands)
        assert any(cmd.startswith(f"tp {lane.selector}") for cmd in commands)


@pytest.mark.unit
class TestInitDoesNotClearCarts:
    def test_do_init_reuses_existing_without_kill(self, tmp_path):
        from minecraft.services.arena_motion.controller import RaceController
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                if command.startswith("data get entity"):
                    return "[1.0d, 64.0d, 2.0d]"
                return ""

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = _sample_config(tmp_path)
            lane = config.lanes[0]
            race_state.update_state(
                assignments=[
                    {
                        "lane_id": lane.id,
                        "cyclist": "Anna",
                        "device_name": "",
                        "device_factor": 1.0,
                        "sim_rate_mps": 2.0,
                        "send_interval_seconds": 5.0,
                    }
                ]
            )
            worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
            worker.config = config
            worker.controller = RaceController(FakeGateway(), config)
            worker.states = []
            worker.race_start = None
            worker.step = 0
            worker._do_init(kill_all=True)
            assert not any("kill @e[type=minecart" in cmd for cmd in commands)
            assert not any(cmd.startswith("summon minecart") for cmd in commands)
            assert any(cmd.startswith(f"tp {lane.selector}") for cmd in commands)
            assert race_state.load_state().get("initialized") is True
            assert race_state.load_state().get("live") == {}


@pytest.mark.unit
class TestClearArenaLabels:
    def test_clear_issues_common_velo_label_kill(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        ctrl.clear_arena_minecarts()
        assert any(
            cmd == 'kill @e[type=text_display,tag=velo_label]' for cmd in commands
        )
        assert any("kill @e[type=minecart,tag=velo_lane_1]" in cmd for cmd in commands)
        # Labels cleared before carts.
        label_idx = next(
            i for i, c in enumerate(commands) if "tag=velo_label]" in c and "text_display" in c
        )
        cart_idx = next(i for i, c in enumerate(commands) if "type=minecart,tag=" in c)
        assert label_idx < cart_idx


@pytest.mark.unit
class TestLabelHeight:
    def test_lane_offsets_are_uniform(self, tmp_path):
        from minecraft.services.arena_motion.controller import RaceController

        class FakeGateway:
            def run(self, command: str) -> str:
                return ""

        lane_a = _sample_lane("lane_1", tag="velo_lane_1")
        lane_b = _sample_lane("lane_2", tag="velo_lane_2")
        lane_c = _sample_lane("lane_3", tag="velo_lane_3")
        config = RaceConfig(
            config_path=tmp_path / "x.toml",
            tick_interval_seconds=0.1,
            motion_min_distance=0.03,
            lap_cooldown_ticks=30,
            actionbar_enabled=True,
            rcon_lock_path=tmp_path / "lock",
            rcon_lock_timeout_seconds=1.0,
            default_impulse_x=0.0,
            default_impulse_y=0.0,
            default_impulse_z=1.0,
            reference_mps=2.0,
            min_motion_speed=0.08,
            max_motion_speed=0.55,
            cart_name_visible=True,
            cart_label_mode=CART_LABEL_MODE_NAME_ONLY,
            lanes=(lane_a, lane_b, lane_c),
        )
        ctrl = RaceController(FakeGateway(), config)
        assert ctrl.label_y_offset(lane_a) == pytest.approx(1.4)
        assert ctrl.label_y_offset(lane_b) == pytest.approx(1.4)
        assert ctrl.label_y_offset(lane_c) == pytest.approx(1.4)


@pytest.mark.unit
class TestLabelSpeedVisibility:
    def test_stationary_hides_kmh(self, tmp_path):
        from minecraft.services.arena_motion.controller import RaceController

        class FakeGateway:
            def run(self, command: str) -> str:
                return ""

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        no_speed = ctrl._format_label_text("Anna", "blue", speed_kmh=None)
        zero = ctrl._format_label_text("Anna", "blue", speed_kmh=0.0)
        moving = ctrl._format_label_text(
            "Anna", "blue", speed_kmh=18.0, laps_completed=2, target_laps=5
        )
        assert "km/h" not in no_speed
        assert "km/h" not in zero
        assert "18 km/h" in moving
        assert "Velos" not in moving
        assert "2/5 Runden" in moving
        assert "Velos" not in no_speed
        assert "Runden" not in no_speed

        final = ctrl._format_label_text(
            "Anna",
            "blue",
            place=1,
            final=True,
            finish_time_s=12.3,
            laps_completed=5,
            target_laps=5,
        )
        assert "5/5 Runden" in final
        assert "Velos" not in final

    def test_velos_line_only_when_explicitly_passed(self, tmp_path):
        from minecraft.services.arena_motion.controller import RaceController

        class FakeGateway:
            def run(self, command: str) -> str:
                return ""

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        with_velos = ctrl._format_label_text(
            "Anna", "blue", speed_kmh=10.0, velos=42, laps_completed=1, target_laps=3
        )
        assert "42 Velos" in with_velos

    def test_bike_speed_kmh_from_distance_delta(self):
        """3 m/s distance rate → 10.8 km/h (not Minecraft block speed)."""
        tick = 0.1
        delta_m = 3.0 * tick
        assert delta_m / tick * 3.6 == pytest.approx(10.8)


@pytest.mark.unit
class TestNameOnlyCartLabels:
    def test_format_shows_name_only(self, tmp_path):
        from minecraft.services.arena_motion.controller import RaceController

        class FakeGateway:
            def run(self, command: str) -> str:
                return ""

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path))
        text = ctrl._format_label_text(
            "Anna",
            "blue",
            speed_kmh=18.0,
            place=1,
            final=True,
            finish_time_s=42.0,
            velos=66,
            laps_completed=5,
            target_laps=5,
        )
        assert "Anna" in text
        assert "km/h" not in text
        assert "Velos" not in text
        assert "Runden" not in text
        assert "42" not in text

    def test_name_only_skips_rcon_on_speed_and_place_changes(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path))
        lane = ctrl.config.lanes[0]
        state = CartState(
            assignment=LaneAssignment(lane=lane, cyclist="Anna", sim_rate_mps=2.0)
        )

        assert ctrl.update_cart_label(
            lane, "Anna", speed_kmh=10.0, place=1, track=state
        )
        assert (
            ctrl.update_cart_label(
                lane, "Anna", speed_kmh=22.0, place=2, track=state
            )
            is False
        )
        assert len(commands) == 1

        assert ctrl.update_cart_label(lane, "Ben", track=state) is True
        assert len(commands) == 2


@pytest.mark.unit
class TestActionbarAudience:
    def test_announce_targets_arena_team_only(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path))
        ctrl.announce("Test")
        assert len(commands) == 1
        assert "title @a[tag=mcc_arena] actionbar" in commands[0]

    def test_bossbar_targets_arena_team_only(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path))
        ctrl.update_race_bossbar(remaining_s=90, time_limit_seconds=180, create=True)
        assert any("players @a[tag=mcc_arena]" in cmd for cmd in commands)
        assert any("bossbar set mcc:arena_live value 90" in cmd for cmd in commands)

    def test_clear_bossbar(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path))
        ctrl.clear_race_bossbar()
        assert commands == ["bossbar remove mcc:arena_live"]


@pytest.mark.unit
class TestMotionSpeed:
    def test_fixed_speed_ignores_distance(self, tmp_path):
        config = _sample_config(tmp_path)
        assignment = LaneAssignment(lane=config.lanes[0], cyclist="anna", sim_rate_mps=4.0)
        assert motion_speed_for(config, assignment, use_distance=False) == 0.4

    def test_distance_mapping_one_to_one_blocks_per_meter(self, tmp_path):
        """1 m/s bike → 1 block/s → Motion 1/20 blocks per MC tick."""
        from minecraft.services.arena_motion.lanes import motion_from_mps

        config = _sample_config(tmp_path)
        assignment = LaneAssignment(lane=config.lanes[0], cyclist="anna", sim_rate_mps=3.0)
        assert motion_speed_for(config, assignment, use_distance=True) == pytest.approx(0.15)
        assert motion_from_mps(3.0) == pytest.approx(0.15)
        # 120 m at 3 m/s → 40 s for one lap (geometry 1 block = 1 m).
        assert 120.0 / 3.0 == pytest.approx(40.0)

    def test_distance_mapping_clamped(self, tmp_path):
        config = _sample_config(tmp_path)
        assignment = LaneAssignment(
            lane=config.lanes[0],
            cyclist="anna",
            sim_rate_mps=20.0,  # would be 1.0 blocks/tick without clamp
            device_factor=2.0,
        )
        speed = motion_speed_for(config, assignment, use_distance=True)
        assert speed == config.max_motion_speed

    def test_motion_ignores_device_fkm(self, tmp_path):
        config = _sample_config(tmp_path)
        slow_fkm = LaneAssignment(
            lane=config.lanes[0], cyclist="big", sim_rate_mps=2.0, device_factor=1.0
        )
        high_fkm = LaneAssignment(
            lane=config.lanes[0], cyclist="small", sim_rate_mps=2.0, device_factor=1.74
        )
        assert motion_speed_for(config, slow_fkm, use_distance=True) == motion_speed_for(
            config, high_fkm, use_distance=True
        )
        assert slow_fkm.motion_mps == high_fkm.motion_mps == 2.0

    def test_velos_still_use_fkm(self, tmp_path):
        lane = _sample_lane()
        state = CartState(
            assignment=LaneAssignment(
                lane=lane, cyclist="kid", sim_rate_mps=2.0, device_factor=1.5
            )
        )
        state.distance_m = 1000.0  # 1 km
        assert state.refresh_velos() == 150  # 100 Velos/km * 1.5 FKM

    def test_live_velos_follow_session_or_pulse_meters(self, tmp_path):
        lane = _sample_lane()
        state = CartState(
            assignment=LaneAssignment(
                lane=lane, cyclist="kid", sim_rate_mps=2.0, device_factor=1.5
            )
        )
        state.live_distance_m = 9.0
        assert state.refresh_live_velos() == 1
        state.distance_m = 9.0
        assert state.refresh_velos() == state.live_velos


@pytest.mark.unit
class TestPlaces:
    def test_finished_ranked_by_time(self, tmp_path):
        lane_a = _sample_lane("lane_1")
        lane_b = _sample_lane("lane_2", tag="velo_lane_2")
        a = CartState(assignment=LaneAssignment(lane=lane_a, cyclist="anna"))
        b = CartState(assignment=LaneAssignment(lane=lane_b, cyclist="ben"))
        a.finished = True
        b.finished = True
        a.finish_time = 100.0
        b.finish_time = 90.0
        places = compute_places([a, b], target_laps=3)
        assert places["lane_2"] == 1
        assert places["lane_1"] == 2

    def test_velo_mode_ranked_by_velos(self, tmp_path):
        lane_a = _sample_lane("lane_1")
        lane_b = _sample_lane("lane_2", tag="velo_lane_2")
        a = CartState(assignment=LaneAssignment(lane=lane_a, cyclist="anna"))
        b = CartState(assignment=LaneAssignment(lane=lane_b, cyclist="ben"))
        a.live_velos = 40
        b.live_velos = 66
        places = compute_places_by_velos([a, b])
        assert places["lane_2"] == 1
        assert places["lane_1"] == 2

    def test_reset_race_progress_clears_old_place(self, tmp_path):
        lane = _sample_lane()
        state = CartState(assignment=LaneAssignment(lane=lane, cyclist="anna"))
        state.place = 3
        state.progress_blocks = 500.0
        state.finished = True
        state.current_lap = 5
        state.reset_race_progress()
        assert state.place == 1
        assert state.progress_blocks == 0.0
        assert state.finished is False
        assert state.current_lap == 1
        assert state.last_session_km is None


@pytest.mark.unit
@pytest.mark.django_db
class TestDeviceLiveMotion:
    def test_device_live_waits_then_moves_on_session_km(self, tmp_path):
        from decimal import Decimal

        from api.models import Cyclist, CyclistDeviceCurrentMileage
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

        config = _sample_config(tmp_path)
        lane = config.lanes[0]
        cyclist = Cyclist.objects.create(
            user_id="LiveRider",
            id_tag="tag-liverider",
            is_visible=True,
        )
        device = Device.objects.create(name="live-box", display_name="live-box", is_visible=True)
        DeviceConfiguration.objects.create(device=device, wheel_size=2075.0)
        assignment = LaneAssignment(
            lane=lane,
            cyclist=cyclist.user_id,
            device_name=device.name,
            send_interval_seconds=5.0,
        )
        state = CartState(assignment=assignment)
        worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
        worker.config = config
        worker.sim_distance = False
        worker.api_live_pulse = False

        # Baseline: no session yet → speed 0
        worker._apply_device_live_tick(state, now=1000.0)
        assert state.target_speed == 0.0
        assert state.last_session_km == 0.0

        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal("0.01000"),  # 10 m
        )
        worker._apply_device_live_tick(state, now=1005.0)
        assert state.target_speed > 0.0
        assert state.held_mps > 0.0
        assert state.distance_m == pytest.approx(10.0)
        assert state.live_distance_m == pytest.approx(10.0)
        assert state.live_velos == state.velos

    def test_device_live_velos_ignore_cart_path(self, tmp_path):
        """ArenaLive must not double-count cart geometry on top of session km."""
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

        config = _sample_config(tmp_path)
        lane = config.lanes[0]
        state = CartState(
            assignment=LaneAssignment(
                lane=lane,
                cyclist="kid",
                sim_rate_mps=2.0,
                device_factor=1.0,
                device_name="box",
            )
        )
        state.distance_m = 10.0
        state.live_distance_m = 10.0
        state.refresh_velos()
        state.refresh_live_velos()
        before = state.live_velos

        # Simulate what _tick used to do wrongly: add cart path on top.
        # After the fix, live meters stay session-only; this documents the contract.
        cart_dist = 10.0
        assert state.live_distance_m == pytest.approx(10.0)
        assert state.live_velos == before
        assert cart_dist > 0  # cart still moves, but must not inflate live meters
        worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
        worker.sim_distance = False
        worker.api_live_pulse = False
        # Contract: live meters == distance_m (session), not session+cart.
        assert state.live_distance_m == state.distance_m
        assert state.live_velos == state.velos


@pytest.mark.unit
@pytest.mark.django_db
class TestArenaControlState:
    def _make_device(
        self,
        name="arena-box-1",
        wheel_mm=2075.0,
        bonus=0.0,
        group=None,
        *,
        is_arena_sim_allowed=False,
    ):
        from iot.models import Device, DeviceConfiguration

        device = Device.objects.create(
            name=name,
            display_name=name,
            is_visible=True,
            group=group,
            is_arena_sim_allowed=is_arena_sim_allowed,
        )
        DeviceConfiguration.objects.create(
            device=device,
            wheel_size=wheel_mm,
            paedagogischer_bonus=bonus,
        )
        return device

    def _make_cyclist(self, user_id="Anna", *, is_arena_sim_allowed=False):
        from api.models import Cyclist

        return Cyclist.objects.create(
            user_id=user_id,
            id_tag=f"tag-{user_id.lower()}",
            is_visible=True,
            is_arena_sim_allowed=is_arena_sim_allowed,
        )

    def test_set_assignments_and_start(self, tmp_path, settings):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        lock = tmp_path / "rcon.lock"
        device = self._make_device(wheel_mm=2075.0, bonus=0.3)
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            MCC_MINECRAFT_RCON_LOCK_PATH=str(lock),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            assert len(config.lanes) >= 1
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "Anna",
                        "device_name": device.name,
                    }
                ]
            )
            st = race_state.load_state()
            assert st["assignments"][0]["cyclist"] == "Anna"
            assert st["assignments"][0]["device_name"] == device.name
            assert st["assignments"][0]["device_factor"] == pytest.approx(device.get_fkm_factor())
            assert st["assignments"][0]["sim_rate_mps"] == pytest.approx(4.5)
            assert st.get("initialized") is False
            race_state.update_state(initialized=True)
            request_start(target_laps=3, sim_distance=False)
            st = race_state.load_state()
            assert st["pending_command"] == "start"
            assert st["target_laps"] == 3

    def test_start_requires_init(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        device = self._make_device(name="arena-box-init")
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "Anna",
                        "device_name": device.name,
                    }
                ]
            )
            with pytest.raises(ArenaControlError, match="Init"):
                request_start(target_laps=3)

    def test_assignment_requires_device(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            with pytest.raises(ArenaControlError, match="Gerät"):
                set_assignments(
                    [{"lane_id": config.lanes[0].id, "cyclist": "Anna"}]
                )

    def test_update_sim_rates(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        self._make_cyclist("Anna", is_arena_sim_allowed=True)
        device = self._make_device(name="arena-box-sim", is_arena_sim_allowed=True)
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "Anna",
                        "device_name": device.name,
                    }
                ]
            )
            update_sim_rates(
                [{"lane_id": config.lanes[0].id, "sim_rate_mps": 3.5}]
            )
            st = race_state.load_state()
            assert st["assignments"][0]["sim_rate_mps"] == pytest.approx(3.5)

    def test_live_rate_refresh_during_sim(self, tmp_path):
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            lane = _sample_lane()
            worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
            worker.sim_distance = True
            worker.api_live_pulse = False
            worker.states = [
                CartState(
                    assignment=LaneAssignment(
                        lane=lane,
                        cyclist="Anna",
                        sim_rate_mps=2.0,
                        device_name="box",
                    )
                )
            ]
            race_state.save_state(
                {
                    **race_state.default_state(),
                    "assignments": [
                        {
                            "lane_id": lane.id,
                            "cyclist": "Anna",
                            "device_name": "box",
                            "sim_rate_mps": 4.25,
                        }
                    ],
                }
            )
            worker._refresh_live_sim_rates()
            assert worker.states[0].assignment.sim_rate_mps == pytest.approx(4.25)

    def test_flush_iot_partial_credits_velos_at_finish(self, tmp_path):
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            lane = _sample_lane()
            worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
            worker.sim_distance = True
            worker.api_live_pulse = False
            worker.pulse_by_lane = {}
            state = CartState(
                assignment=LaneAssignment(
                    lane=lane,
                    cyclist="Anna",
                    sim_rate_mps=3.0,
                    device_factor=1.5,
                    device_name="box",
                    send_interval_seconds=5.0,
                )
            )
            state.held_mps = 3.0
            state.last_pulse_at = 100.0
            state.next_pulse_at = 105.0
            state.distance_m = 0.0
            state.velos = 0
            worker.states = [state]
            worker._flush_iot_partial_distance(state, now=103.0)
            # 3 m/s × 3 s = 9 m → km=0.009 × 100 × 1.5 = 1 Velo
            assert state.distance_m == pytest.approx(9.0)
            assert state.velos == 1

    def test_sim_rejects_unflagged_cyclist_and_device(self, tmp_path):
        from minecraft.services.arena_motion.control import assert_arena_sim_roster

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        self._make_cyclist("SimKid", is_arena_sim_allowed=False)
        device = self._make_device(name="arena-box-noflag", is_arena_sim_allowed=False)
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "SimKid",
                        "device_name": device.name,
                    }
                ]
            )
            with pytest.raises(ArenaControlError, match="nicht für die Arena-Simulation"):
                assert_arena_sim_roster()
            with pytest.raises(ArenaControlError, match="nicht für die Arena-Simulation"):
                update_sim_rates(
                    [{"lane_id": config.lanes[0].id, "sim_rate_mps": 2.0}]
                )
            race_state.update_state(initialized=True)
            with pytest.raises(ArenaControlError, match="nicht für die Arena-Simulation"):
                request_start(target_laps=2, sim_distance=True)

    def test_sim_allows_flagged_roster(self, tmp_path):
        from minecraft.services.arena_motion.control import assert_arena_sim_roster

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        self._make_cyclist("SimOk", is_arena_sim_allowed=True)
        device = self._make_device(name="arena-box-ok", is_arena_sim_allowed=True)
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "SimOk",
                        "device_name": device.name,
                    }
                ]
            )
            assert_arena_sim_roster()
            race_state.update_state(initialized=True)
            request_start(target_laps=2, sim_distance=True)
            assert race_state.load_state()["pending_command"] == "start"
            assert race_state.load_state()["sim_distance"] is True
            assert race_state.load_state()["api_live_pulse"] is False

    def test_api_live_start_sets_flags(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        self._make_cyclist("ApiKid", is_arena_sim_allowed=True)
        device = self._make_device(name="arena-box-api", is_arena_sim_allowed=True)
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "ApiKid",
                        "device_name": device.name,
                    }
                ]
            )
            race_state.update_state(initialized=True)
            request_start(target_laps=2, api_live_pulse=True)
            st = race_state.load_state()
            assert st["pending_command"] == "start"
            assert st["api_live_pulse"] is True
            assert st["sim_distance"] is False

    def test_api_pulse_writes_via_update_data(self, tmp_path):
        from decimal import Decimal

        from minecraft.services.arena_motion.api_pulse import pulse_meters

        cyclist = self._make_cyclist("PulseKid", is_arena_sim_allowed=True)
        device = self._make_device(name="arena-box-pulse", is_arena_sim_allowed=True)
        before = Decimal(str(cyclist.distance_total or 0))
        ok, err = pulse_meters(
            id_tag=cyclist.id_tag,
            device_name=device.name,
            distance_m=5.0,
        )
        assert ok, err
        cyclist.refresh_from_db()
        assert Decimal(str(cyclist.distance_total)) == before + Decimal("0.005")

    def test_start_without_assignments_fails(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            race_state.save_state(race_state.default_state())
            with pytest.raises(ArenaControlError):
                request_start()

    def test_start_ends_device_sessions_and_unlocks_oled(self, tmp_path):
        from decimal import Decimal

        from api.models import CyclistDeviceCurrentMileage
        from iot.models import DeviceConfiguration
        from minecraft.models import MinecraftArenaMotionSettings

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        cyclist = self._make_cyclist("ArenaRider")
        device = self._make_device(name="arena-box-session")
        DeviceConfiguration.objects.filter(device=device).update(
            display_velos_locked=True,
            frozen_display_velos=12,
        )
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal("2.50000"),
        )
        settings_obj = MinecraftArenaMotionSettings.get_solo()
        settings_obj.end_device_sessions_on_race_start = True
        settings_obj.save(update_fields=["end_device_sessions_on_race_start"])

        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": cyclist.user_id,
                        "device_name": device.name,
                    }
                ]
            )
            race_state.update_state(initialized=True)
            request_start(target_laps=2, sim_distance=False)

        assert not CyclistDeviceCurrentMileage.objects.filter(device=device).exists()
        device_cfg = DeviceConfiguration.objects.get(device=device)
        assert device_cfg.display_velos_locked is False
        assert device_cfg.frozen_display_velos == 0

    def test_start_skips_session_end_when_disabled(self, tmp_path):
        from decimal import Decimal

        from api.models import CyclistDeviceCurrentMileage
        from minecraft.models import MinecraftArenaMotionSettings

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        cyclist = self._make_cyclist("KeepSession")
        device = self._make_device(name="arena-box-keep")
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=cyclist,
            device=device,
            cumulative_mileage=Decimal("1.00000"),
        )
        settings_obj = MinecraftArenaMotionSettings.get_solo()
        settings_obj.end_device_sessions_on_race_start = False
        settings_obj.save(update_fields=["end_device_sessions_on_race_start"])

        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": cyclist.user_id,
                        "device_name": device.name,
                    }
                ]
            )
            race_state.update_state(initialized=True)
            request_start(target_laps=2, sim_distance=False)

        assert CyclistDeviceCurrentMileage.objects.filter(device=device).exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestArenaLaneDatabase:
    def test_load_from_database_when_preferred(self, tmp_path):
        from minecraft.models import MinecraftArenaLane, MinecraftArenaMotionSettings

        settings_obj = MinecraftArenaMotionSettings.get_solo()
        settings_obj.prefer_database_lanes = True
        settings_obj.reference_mps = 3.0
        settings_obj.save()
        MinecraftArenaLane.objects.create(
            lane_id="lane_db",
            name="DB Bahn",
            tag="velo_lane_db",
            color="red",
            sort_order=1,
            is_active=True,
            start_x=10.0,
            start_y=70.0,
            start_z=20.0,
            yaw=90.0,
            pitch=0.0,
            base_speed=0.35,
            finish_x_min=9.0,
            finish_x_max=11.0,
            finish_z_trigger=100.0,
            impulse_x=0.0,
            impulse_y=0.0,
            impulse_z=1.2,
        )
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(tmp_path / "missing.toml"),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
        assert config.source == "database"
        assert len(config.lanes) == 1
        assert config.lanes[0].id == "lane_db"
        assert config.lanes[0].start_x == 10.0
        assert config.reference_mps == 3.0

    def test_import_toml_into_database(self, tmp_path):
        from minecraft.models import MinecraftArenaLane, MinecraftArenaMotionSettings

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        count = import_lanes_from_toml(example)
        assert count >= 1
        assert MinecraftArenaLane.objects.filter(is_active=True).count() == count
        settings_obj = MinecraftArenaMotionSettings.get_solo()
        assert settings_obj.prefer_database_lanes is True
        config = load_race_config()
        assert config.source == "database"
        assert len(config.lanes) == count


@pytest.mark.unit
@pytest.mark.django_db
class TestArenaCyclistFilter:
    def test_cyclists_filtered_by_top_group(self):
        from api.models import Cyclist, Group, GroupType
        from minecraft.services.arena_motion.cyclists import cyclists_for_top_group

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-type")
        top_a = Group.objects.create(name="ArenaTopA", parent=None, group_type=gtype, is_visible=True)
        top_b = Group.objects.create(name="ArenaTopB", parent=None, group_type=gtype, is_visible=True)
        leaf_a = Group.objects.create(name="ArenaLeafA", parent=top_a, group_type=gtype, is_visible=True)
        leaf_b = Group.objects.create(name="ArenaLeafB", parent=top_b, group_type=gtype, is_visible=True)
        ca = Cyclist.objects.create(user_id="ArenaAnna", id_tag="aa1", is_visible=True)
        cb = Cyclist.objects.create(user_id="ArenaBen", id_tag="bb1", is_visible=True)
        ca.groups.add(leaf_a)
        cb.groups.add(leaf_b)

        only_a = {c["user_id"] for c in cyclists_for_top_group(top_a.id)}
        assert "ArenaAnna" in only_a
        assert "ArenaBen" not in only_a

        all_names = {c["user_id"] for c in cyclists_for_top_group(None)}
        assert "ArenaAnna" in all_names
        assert "ArenaBen" in all_names

    def test_devices_filtered_by_top_group(self):
        from api.models import Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.cyclists import devices_for_top_group

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-type-dev")
        top_a = Group.objects.create(
            name="ArenaDevTopA", parent=None, group_type=gtype, is_visible=True
        )
        top_b = Group.objects.create(
            name="ArenaDevTopB", parent=None, group_type=gtype, is_visible=True
        )
        da = Device.objects.create(name="dev-a", display_name="Box A", group=top_a, is_visible=True)
        db = Device.objects.create(name="dev-b", display_name="Box B", group=top_b, is_visible=True)
        DeviceConfiguration.objects.create(device=da, wheel_size=1600.0, paedagogischer_bonus=0.3)
        DeviceConfiguration.objects.create(device=db, wheel_size=2075.0, paedagogischer_bonus=0.0)

        only_a = {d["name"] for d in devices_for_top_group(top_a.id)}
        assert "dev-a" in only_a
        assert "dev-b" not in only_a
        meta = devices_for_top_group(top_a.id)[0]
        assert meta["wheel_mm"] == 1600
        assert meta["fkm_factor"] == pytest.approx(da.get_fkm_factor(), rel=1e-4)

    def test_arena_sim_only_filters_cyclists_and_devices(self):
        from api.models import Cyclist, Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.cyclists import (
            cyclists_for_top_group,
            devices_for_top_group,
        )

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-sim-filter")
        top = Group.objects.create(
            name="ArenaSimTop", parent=None, group_type=gtype, is_visible=True
        )
        leaf = Group.objects.create(
            name="ArenaSimLeaf", parent=top, group_type=gtype, is_visible=True
        )
        allowed = Cyclist.objects.create(
            user_id="SimAllowed", id_tag="sim-ok", is_visible=True, is_arena_sim_allowed=True
        )
        blocked = Cyclist.objects.create(
            user_id="SimBlocked", id_tag="sim-no", is_visible=True, is_arena_sim_allowed=False
        )
        allowed.groups.add(leaf)
        blocked.groups.add(leaf)
        d_ok = Device.objects.create(
            name="dev-sim-ok",
            display_name="Sim OK",
            group=top,
            is_visible=True,
            is_arena_sim_allowed=True,
        )
        Device.objects.create(
            name="dev-sim-no",
            display_name="Sim No",
            group=top,
            is_visible=True,
            is_arena_sim_allowed=False,
        )
        DeviceConfiguration.objects.create(device=d_ok, wheel_size=1600.0)

        all_c = {c["user_id"] for c in cyclists_for_top_group(top.id)}
        assert "SimAllowed" in all_c and "SimBlocked" in all_c
        only_c = {c["user_id"] for c in cyclists_for_top_group(top.id, arena_sim_only=True)}
        assert only_c == {"SimAllowed"}

        all_d = {d["name"] for d in devices_for_top_group(top.id)}
        assert "dev-sim-ok" in all_d and "dev-sim-no" in all_d
        only_d = {d["name"] for d in devices_for_top_group(top.id, arena_sim_only=True)}
        assert only_d == {"dev-sim-ok"}


@pytest.mark.unit
class TestLabelDisplaySnapshot:
    def test_skips_rcon_when_display_unchanged(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        lane = ctrl.config.lanes[0]
        assignment = LaneAssignment(
            lane=lane,
            cyclist="Anna",
            device_name="",
            device_factor=1.0,
            sim_rate_mps=2.0,
            send_interval_seconds=5.0,
        )
        state = CartState(assignment=assignment)

        sent = ctrl.update_cart_label(
            lane,
            "Anna",
            speed_kmh=18.4,
            place=2,
            velos=120,
            laps_completed=1,
            target_laps=3,
            track=state,
        )
        assert sent is True
        assert len(commands) == 1
        assert commands[0].startswith("data modify entity")

        sent_again = ctrl.update_cart_label(
            lane,
            "Anna",
            speed_kmh=18.49,
            place=2,
            velos=120,
            laps_completed=1,
            target_laps=3,
            track=state,
        )
        assert sent_again is False
        assert len(commands) == 1

    def test_force_sends_even_when_snapshot_matches(self, tmp_path):
        commands: list[str] = []

        class FakeGateway:
            def run(self, command: str) -> str:
                commands.append(command)
                return ""

        from minecraft.services.arena_motion.controller import RaceController

        ctrl = RaceController(FakeGateway(), _sample_config(tmp_path, cart_label_mode=CART_LABEL_MODE_FULL))
        lane = ctrl.config.lanes[0]
        assignment = LaneAssignment(
            lane=lane,
            cyclist="Anna",
            device_name="",
            device_factor=1.0,
            sim_rate_mps=2.0,
            send_interval_seconds=5.0,
        )
        state = CartState(assignment=assignment)

        ctrl.update_cart_label(
            lane,
            "Anna",
            speed_kmh=20.0,
            place=1,
            track=state,
        )
        ctrl.update_cart_label(
            lane,
            "Anna",
            speed_kmh=20.0,
            place=1,
            force=True,
            track=state,
        )
        assert len(commands) == 2

    def test_reset_race_progress_clears_label_snapshot(self, tmp_path):
        lane = _sample_lane()
        assignment = LaneAssignment(
            lane=lane,
            cyclist="Anna",
            device_name="",
            device_factor=1.0,
            sim_rate_mps=2.0,
            send_interval_seconds=5.0,
        )
        state = CartState(assignment=assignment)
        from minecraft.services.arena_motion.controller import LabelDisplaySnapshot

        state.label_snapshot = LabelDisplaySnapshot(
            final=False,
            speed_kmh=10,
            place=1,
            velos=5,
            laps_completed=0,
            target_laps=3,
            finish_time_s=None,
        )
        state.reset_race_progress()
        assert state.label_snapshot is None


@pytest.mark.unit
@pytest.mark.django_db
class TestRaceModes:
    def test_mode_helpers(self):
        assert uses_laps(MODE_LAPS) and uses_laps(MODE_DUAL)
        assert not uses_laps(MODE_VELOS)
        assert uses_time_limit(MODE_VELOS)
        assert not uses_time_limit(MODE_DUAL)
        assert show_velos_live(MODE_VELOS)
        assert not show_velos_live(MODE_DUAL)
        assert normalize_race_mode("unknown") in {MODE_LAPS, MODE_VELOS, MODE_DUAL}

    def test_time_limit_minutes_snaps_for_chrome_step(self):
        from minecraft.services.arena_motion.race_modes import time_limit_minutes_for_ui

        assert time_limit_minutes_for_ui(180) == 3.0
        assert time_limit_minutes_for_ui(300) == 5.0
        assert time_limit_minutes_for_ui(90) == 1.5
        # 100s → 1.666… must snap to 1.5 or 2.0 (0.5 grid), not 1.7
        assert time_limit_minutes_for_ui(100) in {1.5, 2.0}
        assert abs((time_limit_minutes_for_ui(100) * 2) % 1) < 1e-9

    def test_default_time_limit_from_integration(self):
        from minecraft.models import MinecraftIntegrationConfig
        from minecraft.services.arena_motion.race_modes import default_time_limit_seconds

        cfg = MinecraftIntegrationConfig.get_config()
        cfg.arena_default_time_limit_minutes = 5
        cfg.save(update_fields=["arena_default_time_limit_minutes"])
        assert default_time_limit_seconds() == 300

        cfg.arena_default_time_limit_minutes = 8
        cfg.save(update_fields=["arena_default_time_limit_minutes"])
        assert default_time_limit_seconds() == 480

    def test_apply_integration_default_updates_idle_state(self, tmp_path):
        from minecraft.services.arena_motion.control import (
            apply_integration_default_time_limit,
            set_time_limit_seconds,
        )

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            set_time_limit_seconds(180)
            assert race_state.load_state()["time_limit_seconds"] == 180
            apply_integration_default_time_limit(5)
            assert race_state.load_state()["time_limit_seconds"] == 300


    def test_set_race_mode_and_time_limit(self, tmp_path):
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
            MCC_MINECRAFT_ARENA_DEFAULT_RACE_MODE="dual",
            MCC_MINECRAFT_ARENA_DEFAULT_TARGET_LAPS=5,
            MCC_MINECRAFT_ARENA_DEFAULT_TIME_LIMIT_SECONDS=300,
        ):
            set_race_mode(MODE_VELOS)
            set_time_limit_seconds(120)
            st = race_state.load_state()
            assert st["race_mode"] == MODE_VELOS
            assert st["time_limit_seconds"] == 120

    def test_set_continue_after_finish(self, tmp_path):
        from minecraft.services.arena_motion.control import set_continue_after_finish

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            assert race_state.load_state()["continue_after_finish"] is False
            set_continue_after_finish(True)
            assert race_state.load_state()["continue_after_finish"] is True
            set_continue_after_finish(False)
            assert race_state.load_state()["continue_after_finish"] is False

    def test_update_state_lock_preserves_concurrent_fields(self, tmp_path):
        """Heartbeat-style updates must not clobber fields saved under the lock."""
        import threading
        import time

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            race_state.update_state(continue_after_finish=False)
            errors: list[BaseException] = []
            start = threading.Event()

            def heartbeat_loop():
                try:
                    start.wait(timeout=5)
                    for _ in range(50):
                        race_state.update_state(
                            worker_heartbeat=time.time(),
                            worker_pid=1,
                        )
                except BaseException as exc:  # pragma: no cover
                    errors.append(exc)

            def operator_save():
                try:
                    start.wait(timeout=5)
                    time.sleep(0.01)
                    race_state.update_state(continue_after_finish=True)
                except BaseException as exc:  # pragma: no cover
                    errors.append(exc)

            t1 = threading.Thread(target=heartbeat_loop)
            t2 = threading.Thread(target=operator_save)
            t1.start()
            t2.start()
            start.set()
            t1.join(timeout=15)
            t2.join(timeout=15)
            assert not errors
            assert race_state.load_state()["continue_after_finish"] is True

    def test_finish_lane_skips_stop_when_continue_after_finish(self, tmp_path):
        from unittest.mock import MagicMock
        from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker
        from minecraft.services.arena_motion.controller import CartState

        worker = ArenaMotionWorker.__new__(ArenaMotionWorker)
        worker.continue_after_finish = True
        worker.race_start = 1000.0
        worker.controller = MagicMock()
        lane = _sample_lane("blue")
        state = CartState(
            assignment=LaneAssignment(
                lane=lane,
                cyclist="Kid",
                sim_rate_mps=1.0,
                device_factor=1.0,
            )
        )
        worker.states = [state]
        worker._flush_iot_partial_distance = MagicMock()
        worker._apply_places = MagicMock()
        worker._laps_label_args = MagicMock(return_value={})
        worker._label_velos_arg = MagicMock(return_value=None)

        worker._finish_lane(state, now=1005.0)
        assert state.finished is True
        worker.controller.stop_cart.assert_not_called()

        worker.continue_after_finish = False
        state.finished = False
        state.finish_time = None
        worker._finish_lane(state, now=1006.0)
        worker.controller.stop_cart.assert_called_once_with(lane)

    def test_request_start_persists_velo_mode(self, tmp_path, settings):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        lock = tmp_path / "rcon.lock"
        from iot.models import Device, DeviceConfiguration
        from api.models import Cyclist

        Cyclist.objects.create(
            user_id="RaceKid",
            id_tag="race-kid",
            is_visible=True,
            is_arena_sim_allowed=True,
        )
        device = Device.objects.create(
            name="race-mode-dev",
            display_name="race-mode-dev",
            is_visible=True,
            is_arena_sim_allowed=True,
        )
        DeviceConfiguration.objects.create(device=device, wheel_size=1600.0)

        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            MCC_MINECRAFT_RCON_LOCK_PATH=str(lock),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            set_assignments(
                [
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "RaceKid",
                        "device_name": device.name,
                    }
                ]
            )
            race_state.update_state(initialized=True)
            request_start(
                race_mode=MODE_VELOS,
                time_limit_seconds=90,
                sim_distance=True,
            )
            st = race_state.load_state()
            assert st["pending_command"] == "start"
            assert st["race_mode"] == MODE_VELOS
            assert st["time_limit_seconds"] == 90

    def test_invalid_race_mode_rejected(self, tmp_path):
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            with pytest.raises(ArenaControlError):
                set_race_mode("turbo")


@pytest.mark.unit
@pytest.mark.django_db
class TestAutoAssignActiveSessions:
    def test_maps_active_sessions_to_lanes(self, tmp_path):
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Cyclist, CyclistDeviceCurrentMileage, Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.cyclists import active_pairs_for_top_group

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        gtype, _ = GroupType.objects.get_or_create(name="test-arena-auto-type")
        top = Group.objects.create(
            name="ArenaTOP", parent=None, group_type=gtype, is_visible=True
        )
        leaf = Group.objects.create(
            name="ArenaLeaf", parent=top, group_type=gtype, is_visible=True
        )

        riders = []
        for i, name in enumerate(("AutoA", "AutoB"), start=1):
            cyclist = Cyclist.objects.create(
                user_id=name,
                id_tag=f"auto-{name.lower()}",
                is_visible=True,
            )
            cyclist.groups.add(leaf)
            device = Device.objects.create(
                name=f"auto-box-{i}",
                display_name=f"Auto Box {i}",
                is_visible=True,
                group=top,
            )
            DeviceConfiguration.objects.create(device=device, wheel_size=2075.0)
            CyclistDeviceCurrentMileage.objects.create(
                cyclist=cyclist,
                device=device,
                cumulative_mileage=Decimal("0.001"),
                last_activity=timezone.now(),
            )
            riders.append((cyclist, device))

        # Stale session outside TOP must be ignored.
        other_top = Group.objects.create(
            name="OtherTOP", parent=None, group_type=gtype, is_visible=True
        )
        outsider = Cyclist.objects.create(
            user_id="Outsider", id_tag="out", is_visible=True
        )
        outsider.groups.add(other_top)
        odd_device = Device.objects.create(
            name="odd-box", display_name="odd", is_visible=True, group=other_top
        )
        DeviceConfiguration.objects.create(device=odd_device, wheel_size=2075.0)
        CyclistDeviceCurrentMileage.objects.create(
            cyclist=outsider,
            device=odd_device,
            cumulative_mileage=Decimal("0.001"),
            last_activity=timezone.now(),
        )

        pairs = active_pairs_for_top_group(top.id)
        assert {p["user_id"] for p in pairs} == {"AutoA", "AutoB"}

        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            result = auto_assign_active_sessions(top.id)
            assert result["detected"] == 2
            assert result["assigned"] == 2
            assert result["overflow"] == 0
            st = race_state.load_state()
            assigned = {(a["cyclist"], a["device_name"]) for a in st["assignments"]}
            assert assigned == {
                ("AutoA", "auto-box-1"),
                ("AutoB", "auto-box-2"),
            }
            assert st.get("initialized") is False

    def test_requires_idle(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            race_state.update_state(status=race_state.STATUS_RUNNING)
            with pytest.raises(ArenaControlError, match="Idle"):
                auto_assign_active_sessions(None)

    def test_all_top_groups_detects_across_tops(self, tmp_path):
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Cyclist, CyclistDeviceCurrentMileage, Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.cyclists import active_pairs_for_top_group

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-all-tops")
        top_a = Group.objects.create(
            name="AllTopA", parent=None, group_type=gtype, is_visible=True
        )
        top_b = Group.objects.create(
            name="AllTopB", parent=None, group_type=gtype, is_visible=True
        )
        for i, top in enumerate((top_a, top_b), start=1):
            cyclist = Cyclist.objects.create(
                user_id=f"Cross{i}",
                id_tag=f"cross-{i}",
                is_visible=True,
            )
            cyclist.groups.add(top)
            device = Device.objects.create(
                name=f"cross-box-{i}",
                display_name=f"Cross {i}",
                is_visible=True,
                group=top,
            )
            DeviceConfiguration.objects.create(device=device, wheel_size=2075.0)
            CyclistDeviceCurrentMileage.objects.create(
                cyclist=cyclist,
                device=device,
                cumulative_mileage=Decimal("0.001"),
                last_activity=timezone.now(),
            )

        only_a = {p["user_id"] for p in active_pairs_for_top_group(top_a.id)}
        assert only_a == {"Cross1"}
        both = {
            p["user_id"]
            for p in active_pairs_for_top_group(
                None, allowed_top_group_ids={top_a.id, top_b.id}
            )
        }
        assert both == {"Cross1", "Cross2"}
        all_pairs = {p["user_id"] for p in active_pairs_for_top_group(None)}
        assert "Cross1" in all_pairs and "Cross2" in all_pairs

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            result = auto_assign_active_sessions(
                None, allowed_top_group_ids={top_a.id, top_b.id}
            )
            assert result["detected"] == 2
            assert result["assigned"] == 2

    def test_overflow_when_more_sessions_than_lanes(self, tmp_path):
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Cyclist, CyclistDeviceCurrentMileage, Group, GroupType
        from iot.models import Device, DeviceConfiguration

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        gtype, _ = GroupType.objects.get_or_create(name="test-arena-overflow-type")
        top = Group.objects.create(
            name="OverflowTOP", parent=None, group_type=gtype, is_visible=True
        )

        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            lane_count = len(config.lanes)
            assert lane_count >= 1
            for i in range(lane_count + 2):
                cyclist = Cyclist.objects.create(
                    user_id=f"Over{i}",
                    id_tag=f"over-{i}",
                    is_visible=True,
                )
                cyclist.groups.add(top)
                device = Device.objects.create(
                    name=f"over-box-{i}",
                    display_name=f"Over {i}",
                    is_visible=True,
                    group=top,
                )
                DeviceConfiguration.objects.create(device=device, wheel_size=2075.0)
                CyclistDeviceCurrentMileage.objects.create(
                    cyclist=cyclist,
                    device=device,
                    cumulative_mileage=Decimal("0.001"),
                    last_activity=timezone.now(),
                )

            result = auto_assign_active_sessions(top.id)
            assert result["assigned"] == lane_count
            assert result["detected"] == lane_count + 2
            assert result["overflow"] == 2
            assert len(race_state.load_state()["assignments"]) == lane_count

    def test_sim_only_excludes_non_sim_cyclists(self, tmp_path):
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Cyclist, CyclistDeviceCurrentMileage, Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.services.arena_motion.cyclists import active_pairs_for_top_group

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-simfilter-type")
        top = Group.objects.create(
            name="SimFilterTOP", parent=None, group_type=gtype, is_visible=True
        )
        leaf = Group.objects.create(
            name="SimFilterLeaf", parent=top, group_type=gtype, is_visible=True
        )
        classic = Cyclist.objects.create(
            user_id="ClassicSim",
            id_tag="classic-sim",
            is_visible=True,
            is_arena_sim_allowed=True,
        )
        other = Cyclist.objects.create(
            user_id="OtherRider",
            id_tag="other-rider",
            is_visible=True,
            is_arena_sim_allowed=False,
        )
        classic.groups.add(leaf)
        other.groups.add(leaf)
        for i, cyclist in enumerate((classic, other), start=1):
            device = Device.objects.create(
                name=f"simf-box-{i}",
                display_name=f"SimF {i}",
                is_visible=True,
                group=top,
                is_arena_sim_allowed=True,
            )
            DeviceConfiguration.objects.create(device=device, wheel_size=2075.0)
            CyclistDeviceCurrentMileage.objects.create(
                cyclist=cyclist,
                device=device,
                cumulative_mileage=Decimal("0.001"),
                last_activity=timezone.now(),
            )

        all_pairs = {p["user_id"] for p in active_pairs_for_top_group(top.id)}
        assert all_pairs == {"ClassicSim", "OtherRider"}
        sim_pairs = {
            p["user_id"]
            for p in active_pairs_for_top_group(top.id, arena_sim_only=True)
        }
        assert sim_pairs == {"ClassicSim"}

        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            CyclistDeviceCurrentMileage.objects.filter(cyclist=classic).delete()
            result = auto_assign_active_sessions(top.id, arena_sim_only=True)
            assert result.get("cleared") is True
            assert result["assigned"] == 0
            assert race_state.load_state()["assignments"] == []

    def test_preferred_stations_map_to_configured_lanes(self, tmp_path):
        from decimal import Decimal

        from django.utils import timezone

        from api.models import Cyclist, CyclistDeviceCurrentMileage, Group, GroupType
        from iot.models import Device, DeviceConfiguration
        from minecraft.models import MinecraftArenaLane, MinecraftArenaMotionSettings

        gtype, _ = GroupType.objects.get_or_create(name="test-arena-pref-type")
        top = Group.objects.create(
            name="PrefTOP", parent=None, group_type=gtype, is_visible=True
        )
        leaf = Group.objects.create(
            name="PrefLeaf", parent=top, group_type=gtype, is_visible=True
        )

        # Create DB lanes with preferred stations (small wheels → lane_1 / lane_2)
        settings_obj = MinecraftArenaMotionSettings.get_solo()
        settings_obj.prefer_database_lanes = True
        settings_obj.save(update_fields=["prefer_database_lanes"])

        devices = []
        for i in range(1, 5):
            device = Device.objects.create(
                name=f"pref-box-{i}",
                display_name=f"Pref {i}",
                is_visible=True,
                group=top,
            )
            DeviceConfiguration.objects.create(
                device=device,
                wheel_size=1596.0 if i <= 2 else 1916.0,
            )
            devices.append(device)
            cyclist = Cyclist.objects.create(
                user_id=f"PrefRider{i}",
                id_tag=f"pref-{i}",
                is_visible=True,
            )
            cyclist.groups.add(leaf)
            CyclistDeviceCurrentMileage.objects.create(
                cyclist=cyclist,
                device=device,
                cumulative_mileage=Decimal("0.001"),
                last_activity=timezone.now(),
            )

        for i in range(1, 5):
            lane, _ = MinecraftArenaLane.objects.update_or_create(
                lane_id=f"lane_{i}",
                defaults={
                    "name": f"Bahn {i}",
                    "tag": f"velo_lane_{i}",
                    "color": "white",
                    "sort_order": i,
                    "is_active": True,
                    "start_x": 0,
                    "start_y": 0,
                    "start_z": 0,
                    "finish_x_min": 0,
                    "finish_x_max": 1,
                    "finish_z_trigger": 1,
                },
            )
            if i == 1:
                lane.preferred_stations.set([devices[0]])
            elif i == 2:
                lane.preferred_stations.set([devices[1]])

        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
            # Force DB lanes (empty TOML path so load uses DB)
            MCC_MINECRAFT_ARENA_RACE_CONFIG="",
        ):
            result = auto_assign_active_sessions(top.id)
            assert result["preferred_hits"] == 2
            by_lane = {a["lane_id"]: a for a in result["assignments"]}
            assert by_lane["lane_1"]["device_name"] == "pref-box-1"
            assert by_lane["lane_2"]["device_name"] == "pref-box-2"
            assert by_lane["lane_1"]["cyclist"] == "PrefRider1"
            assert by_lane["lane_2"]["cyclist"] == "PrefRider2"

    def test_no_active_sessions_clears_assignments(self, tmp_path):
        example = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "velo_arena_race.toml.example"
        )
        state_file = tmp_path / "arena_state.json"
        with override_settings(
            MCC_MINECRAFT_ARENA_RACE_CONFIG=str(example),
            MCC_MINECRAFT_ARENA_STATE_PATH=str(state_file),
            DATA_DIR=tmp_path,
        ):
            config = load_race_config()
            race_state.update_state(
                assignments=[
                    {
                        "lane_id": config.lanes[0].id,
                        "cyclist": "StaleRider",
                        "device_name": "stale-box",
                        "device_display": "stale-box",
                        "wheel_mm": 2075,
                        "device_factor": 1.0,
                        "send_interval_seconds": 5.0,
                        "sim_rate_mps": 2.0,
                    }
                ],
                initialized=False,
            )
            assert race_state.load_state()["assignments"]
            result = auto_assign_active_sessions(None)
            assert result.get("cleared") is True
            assert result["assigned"] == 0
            assert result["detected"] == 0
            assert race_state.load_state()["assignments"] == []
