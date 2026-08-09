# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from api.tests.conftest import GroupFactory
from minecraft.models import MCSession, MinecraftPlayAccount, MinecraftTeamRegistration
from minecraft.services.session_control import (
    AccountAlreadyActiveError,
    AccountNotFoundError,
    MissingMicrosoftLoginError,
    SessionNotActiveError,
    add_session_time,
    end_session,
    expire_due_sessions,
    set_session_gamemode,
    start_builder_session,
    start_player_session,
    toggle_session_spectator,
)
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="Arena1",
        short_name="Arena1",
        display_name="Arena 1",
        sort_order=1,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionControlPlayer:
    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"

    @pytest.fixture(autouse=True)
    def _minimal_player_bootstrap(self, settings):
        settings.MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED = False

    @pytest.fixture(autouse=True)
    def _mock_sidebar_routing(self):
        with (
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_builder_station_team"),
            patch("minecraft.services.sidebar_visibility.ensure_arena_station_team"),
        ):
            yield

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_player_session(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        session = start_player_session("Arena1", duration=15)
        assert session.status == MCSession.STATUS_ACTIVE
        assert session.account_type == MCSession.ACCOUNT_PLAYER
        assert session.account_name == "Arena1"
        assert session.duration_minutes == 15
        assert mock_rcon.call_args[0][0] == ["authme forcelogin Arena1"]
        mock_wait.assert_called_once_with("Arena1", timeout_sec=0.5)
        player_cmds = mock_player_rcon.call_args[0][0]
        assert player_cmds[0] == "gamemode adventure Arena1"
        assert "minecraft:emerald" in player_cmds[1]
        assert player_cmds[-2] == "tag Arena1 add mcc_arena"
        assert player_cmds[-1] == "team join mcc_arena1 Arena1"

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_player_teleport_to_spawn(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account, settings
    ):
        settings.MCC_MINECRAFT_LOBBY_X = 12
        settings.MCC_MINECRAFT_LOBBY_Y = 70
        settings.MCC_MINECRAFT_LOBBY_Z = -8
        session = start_player_session("Arena1", duration=15, teleport_to_spawn=True)
        assert session.teleport_to_spawn is True
        player_cmds = mock_player_rcon.call_args[0][0]
        assert player_cmds[-1] == "tp Arena1 12 70 -8"

    def test_spawn_offset_grid(self):
        from minecraft.services.session_control import spawn_offset_xz, world_spawn_tp_command

        assert spawn_offset_xz(0, spacing=3.0) == (0.0, 0.0)
        assert spawn_offset_xz(1, spacing=3.0) == (3.0, 0.0)
        assert spawn_offset_xz(2, spacing=3.0) == (-3.0, 0.0)
        assert spawn_offset_xz(3, spacing=3.0) == (0.0, 3.0)
        assert spawn_offset_xz(4, spacing=3.0) == (0.0, -3.0)
        assert spawn_offset_xz(5, spacing=3.0) == (3.0, 3.0)
        cmd0 = world_spawn_tp_command("A", offset_index=0)
        cmd1 = world_spawn_tp_command("B", offset_index=1)
        assert cmd0 != cmd1
        assert "tp A " in cmd0
        assert "tp B " in cmd1
        assert spawn_offset_xz(0) == (0.0, 0.0)

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_by_id_tag(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        play_account.id_tag = "RFID-AA-01"
        play_account.save()
        session = start_player_session("RFID-AA-01")
        assert session.account_name == "Arena1"

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_uses_account_session_duration(self, mock_rcon, mock_player_rcon, mock_wait, play_account, settings):
        settings.MCC_MINECRAFT_PLAYER_SESSION_MINUTES = 15
        play_account.session_duration_minutes = 25
        play_account.save()
        session = start_player_session("Arena1")
        assert session.duration_minutes == 25

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_dual_activation_blocked(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        start_player_session("Arena1")
        with pytest.raises(AccountAlreadyActiveError):
            start_player_session("Arena1")

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=False)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_active_even_if_client_focus_slow(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account
    ):
        session = start_player_session("Arena1", duration=15)
        assert session.status == MCSession.STATUS_ACTIVE
        assert session.last_error.startswith("PENDING_BOOTSTRAP:")
        mock_player_rcon.assert_not_called()

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_set_all_active_gamemodes(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        from minecraft.services.session_control import set_all_active_gamemodes

        start_player_session("Arena1", duration=15)
        MinecraftPlayAccount.objects.create(
            id_tag="Arena2",
            short_name="Arena2",
            display_name="Arena 2",
            sort_order=2,
            is_active=True,
            ms_username="",
        )
        # Second account without MS login would fail in online mode; authme uses short_name
        start_player_session("Arena2", duration=15)
        mock_player_rcon.reset_mock()
        ok, errors = set_all_active_gamemodes(
            "spectator",
            account_type=MCSession.ACCOUNT_PLAYER,
        )
        assert ok == 2
        assert errors == []
        assert (
            MCSession.objects.filter(
                status=MCSession.STATUS_ACTIVE,
                play_gamemode=MCSession.GAMEMODE_SPECTATOR,
            ).count()
            == 2
        )
        assert mock_player_rcon.call_count == 2

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_all_idle_sessions(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        from minecraft.services.session_control import start_all_idle_sessions

        MinecraftPlayAccount.objects.create(
            id_tag="Arena2",
            short_name="Arena2",
            display_name="Arena 2",
            sort_order=2,
            is_active=True,
            ms_username="",
        )
        start_player_session("Arena1", duration=15)
        mock_rcon.reset_mock()
        ok, errors = start_all_idle_sessions(account_type=MCSession.ACCOUNT_PLAYER)
        assert ok == 1
        assert errors == []
        assert (
            MCSession.objects.filter(
                status=MCSession.STATUS_ACTIVE,
                account_type=MCSession.ACCOUNT_PLAYER,
            ).count()
            == 2
        )

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.velocity_rcon.send_player_to_paper", return_value="sent")
    @patch("minecraft.services.player_presence.resolve_presences_for_logins")
    def test_start_all_prefers_waiting_in_lobby(
        self, mock_presence, mock_send, mock_rcon, mock_player_rcon, mock_wait, play_account, settings
    ):
        from minecraft.services.player_presence import PRESENCE_LIMBO, PRESENCE_OFFLINE, PlayerPresence
        from minecraft.services.session_control import start_all_idle_sessions

        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "online"
        play_account.ms_username = "mccpc01"
        play_account.save(update_fields=["ms_username"])
        MinecraftPlayAccount.objects.create(
            id_tag="Arena2",
            short_name="Arena2",
            display_name="Arena 2",
            sort_order=2,
            is_active=True,
            ms_username="mccpc02",
        )
        mock_presence.return_value = {
            "mccpc01": PlayerPresence(ms_username="mccpc01", state=PRESENCE_LIMBO, server="limbo"),
            "mccpc02": PlayerPresence(ms_username="mccpc02", state=PRESENCE_OFFLINE),
        }
        ok, errors = start_all_idle_sessions(account_type=MCSession.ACCOUNT_PLAYER)
        assert ok == 1
        assert errors == []
        assert MCSession.objects.filter(status=MCSession.STATUS_ACTIVE).count() == 1
        assert MCSession.objects.get(status=MCSession.STATUS_ACTIVE).account_name == "Arena1"
        mock_send.assert_called_once_with("mccpc01")

    def test_unknown_account(self, db):
        with pytest.raises(AccountNotFoundError):
            start_player_session("Missing")


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionControlBuilder:
    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"

    @pytest.fixture(autouse=True)
    def _minimal_builder_bootstrap(self, settings):
        settings.MCC_MINECRAFT_BUILDER_SESSION_BOOTSTRAP_ENABLED = False

    @pytest.fixture(autouse=True)
    def _mock_sidebar_routing(self):
        with (
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_builder_station_team"),
            patch("minecraft.services.sidebar_visibility.ensure_arena_station_team"),
        ):
            yield

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_builder_adventure(self, mock_rcon, mock_player_rcon, mock_wait):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(authme_is_registered=True)
        session = start_builder_session("Kette", duration=90)
        assert session.account_type == MCSession.ACCOUNT_BUILDER
        assert session.account_name == "Kette"
        assert mock_rcon.call_args[0][0] == ["authme forcelogin Kette"]
        assert mock_player_rcon.call_args[0][0] == [
            "gamemode adventure Kette",
            "team join mcc_kette Kette",
            'tellraw Kette {"text":"Du spielst als ","extra":[{"text":"Kette","bold":true,"color":"gold"},{"text":"."}]}',
        ]

    @override_settings(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret")
    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    def test_start_builder_auto_registers_when_needed(
        self, mock_authme_rcon, mock_session_rcon, mock_player_rcon, mock_wait
    ):
        group = GroupFactory(name="Kette", mc_username="Kette")
        registration = register_group_for_minecraft(group)
        assert registration.authme_is_registered is False
        start_builder_session("Kette", duration=90)
        mock_authme_rcon.assert_called_once_with(
            ["authme register Kette BuilderSecret"],
            stop_on_error=True,
        )
        assert mock_session_rcon.call_args[0][0] == ["authme forcelogin Kette"]
        registration.refresh_from_db()
        assert registration.authme_is_registered is True

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_inactive_registration_rejected(self, mock_rcon, mock_player_rcon, mock_wait):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(is_active=False)
        with pytest.raises(AccountNotFoundError):
            start_builder_session("Kette")

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_uses_registration_session_duration(self, mock_rcon, mock_player_rcon, mock_wait, settings):
        settings.MCC_MINECRAFT_BUILDER_SESSION_MINUTES = 90
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(
            session_duration_minutes=120,
            authme_is_registered=True,
        )
        session = start_builder_session("Kette")
        assert session.duration_minutes == 120

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_builder_region_spawn_priority(self, mock_rcon, mock_player_rcon, mock_wait):
        from minecraft.models import MinecraftProtectedRegion
        from minecraft.services.session_control import (
            SessionControlError,
            region_spawn_xyz,
        )

        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(authme_is_registered=True)
        region = MinecraftProtectedRegion.objects.create(
            region_id="kette_zone",
            world="MyCyclingCity",
            min_x=0,
            min_y=10,
            min_z=0,
            max_x=10,
            max_y=20,
            max_z=10,
        )
        region.builders.add(reg)
        x, y, z = region_spawn_xyz(region)
        assert 5.0 <= x <= 6.0
        assert 5.0 <= z <= 6.0
        assert y == 12.0

        tall = MinecraftProtectedRegion.objects.create(
            region_id="kette_tall",
            world="MyCyclingCity",
            min_x=0,
            min_y=-64,
            min_z=0,
            max_x=10,
            max_y=320,
            max_z=10,
        )
        _, tall_y, _ = region_spawn_xyz(tall)
        assert tall_y > 0  # not deep underground (min_y+2)
        assert -64 <= tall_y <= 320

        region.spawn_x, region.spawn_y, region.spawn_z = 3, 14, 4
        region.save()
        sx, sy, sz = region_spawn_xyz(region)
        assert (sx, sy, sz) == (3.5, 14.0, 4.5)

        session = start_builder_session(
            "Kette",
            duration=30,
            teleport_to_spawn=True,
            spawn_region_id=region.pk,
        )
        assert session.spawn_region_id == region.pk
        assert session.teleport_to_spawn is False
        joined = " ".join(mock_player_rcon.call_args[0][0])
        assert "tp Kette 3.5 14 4.5" in joined
        # World lobby spawn must not be used when region is set.
        assert session.teleport_to_spawn is False

        other = MinecraftProtectedRegion.objects.create(
            region_id="fremd",
            world="MyCyclingCity",
            min_x=100,
            min_y=0,
            min_z=100,
            max_x=110,
            max_y=10,
            max_z=110,
        )
        with pytest.raises(SessionControlError):
            start_builder_session("Kette", duration=30, spawn_region_id=other.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestRegionsForBuilder:
    def test_only_member_regions_listed(self):
        from minecraft.models import MinecraftProtectedRegion
        from minecraft.services.region_admin import regions_for_builder_choices
        from minecraft.services.team_registration import register_group_for_minecraft

        g1 = GroupFactory(name="TeamA", mc_username="TeamA")
        g2 = GroupFactory(name="TeamB", mc_username="TeamB")
        reg_a = register_group_for_minecraft(g1)
        reg_b = register_group_for_minecraft(g2)
        r1 = MinecraftProtectedRegion.objects.create(
            region_id="a_only",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=1,
            max_y=1,
            max_z=1,
        )
        r2 = MinecraftProtectedRegion.objects.create(
            region_id="b_only",
            world="MyCyclingCity",
            min_x=2,
            min_y=0,
            min_z=2,
            max_x=3,
            max_y=1,
            max_z=3,
        )
        r1.builders.add(reg_a)
        r2.builders.add(reg_b)
        choices = regions_for_builder_choices(reg_a)
        assert [c["region_id"] for c in choices] == ["a_only"]

    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"

    @pytest.fixture(autouse=True)
    def _minimal_bootstraps(self, settings):
        settings.MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED = False
        settings.MCC_MINECRAFT_BUILDER_SESSION_BOOTSTRAP_ENABLED = False

    @pytest.fixture(autouse=True)
    def _mock_sidebar_routing(self):
        with (
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_builder_station_team"),
            patch("minecraft.services.sidebar_visibility.ensure_arena_station_team"),
        ):
            yield

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_end_session_termination_commands(self, mock_rcon, mock_player_rcon, mock_wait, play_account, settings):
        settings.MCC_MINECRAFT_LOBBY_X = 10
        settings.MCC_MINECRAFT_LOBBY_Y = 70
        settings.MCC_MINECRAFT_LOBBY_Z = -5
        start_player_session("Arena1")
        mock_rcon.reset_mock()
        session = end_session("Arena1")
        assert session.status == MCSession.STATUS_FINISHED
        assert session.timestamp_end is not None
        # terminate: spectator+tp+team leave, then authme logout
        assert mock_rcon.call_count >= 2
        first = mock_rcon.call_args_list[0][0][0]
        assert first[0] == "gamemode spectator Arena1"
        assert first[1] == "tp Arena1 10 70 -5"
        assert first[2] == "tag Arena1 remove mcc_arena"
        assert first[3] == "team leave Arena1"
        second = mock_rcon.call_args_list[1][0][0]
        assert second == ["authme logout Arena1"]

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_add_session_time(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        session = start_player_session("Arena1", duration=15)
        original_end = session.ends_at
        updated = add_session_time("Arena1", minutes=10)
        assert updated.ends_at == original_end + timedelta(minutes=10)
        assert updated.duration_minutes == 25
        assert updated.status == MCSession.STATUS_ACTIVE

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_add_session_time_uses_account_default(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account, settings
    ):
        settings.MCC_MINECRAFT_SESSION_ADD_MINUTES = 15
        play_account.add_time_minutes = 20
        play_account.save()
        session = start_player_session("Arena1", duration=15)
        original_end = session.ends_at
        updated = add_session_time("Arena1")
        assert updated.ends_at == original_end + timedelta(minutes=20)
        assert updated.duration_minutes == 35

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_add_time_requires_active(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        with pytest.raises(SessionNotActiveError):
            add_session_time("Arena1")

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_expire_due_sessions(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        session = start_player_session("Arena1", duration=15)
        MCSession.objects.filter(pk=session.pk).update(
            ends_at=timezone.now() - timedelta(seconds=5)
        )
        finished = expire_due_sessions()
        assert len(finished) == 1
        session.refresh_from_db()
        assert session.status == MCSession.STATUS_FINISHED

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_start_with_prefer_spectator(self, mock_rcon, mock_player_rcon, mock_wait, play_account):
        play_account.prefer_spectator = True
        play_account.save()
        session = start_player_session("Arena1")
        assert session.gamemode_spectator is True
        assert session.play_gamemode == MCSession.GAMEMODE_SPECTATOR
        player_cmds = mock_player_rcon.call_args[0][0]
        assert player_cmds[0] == "gamemode spectator Arena1"

    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    def test_toggle_session_spectator(
        self, mock_wait, mock_rcon, mock_player_rcon, play_account
    ):
        start_player_session("Arena1")
        mock_player_rcon.reset_mock()
        session = toggle_session_spectator("Arena1")
        assert session.gamemode_spectator is True
        assert mock_player_rcon.call_args[0][0][0] == "gamemode spectator Arena1"
        session = toggle_session_spectator("Arena1")
        assert session.gamemode_spectator is False
        assert mock_player_rcon.call_args[0][0][0] == "gamemode adventure Arena1"


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionControlOnlineMode:
    @pytest.fixture(autouse=True)
    def _online_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "online"

    @pytest.fixture(autouse=True)
    def _minimal_bootstraps(self, settings):
        settings.MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED = False
        settings.MCC_MINECRAFT_BUILDER_SESSION_BOOTSTRAP_ENABLED = False

    @pytest.fixture(autouse=True)
    def _mock_sidebar_routing(self):
        with (
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_builder_station_team"),
            patch("minecraft.services.sidebar_visibility.ensure_arena_station_team"),
        ):
            yield

    def test_builder_requires_ms_login(self):
        group = GroupFactory(name="Kette", mc_username="Kette")
        register_group_for_minecraft(group)
        with pytest.raises(MissingMicrosoftLoginError):
            start_builder_session("Kette")

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.velocity_rcon.send_player_to_paper", return_value="sent")
    def test_builder_online_send_and_team_join(
        self, mock_send, mock_rcon, mock_player_rcon, mock_wait
    ):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(ms_username="mccpc01")
        session = start_builder_session("Kette", duration=90)
        assert session.ms_username == "mccpc01"
        assert session.play_gamemode == MCSession.GAMEMODE_ADVENTURE
        mock_send.assert_called_once_with("mccpc01")
        mock_wait.assert_called_once_with("mccpc01", timeout_sec=0.5)
        assert mock_player_rcon.call_args[0][0] == [
            "gamemode adventure mccpc01",
            "team join mcc_kette mccpc01",
            'tellraw mccpc01 {"text":"Du spielst als ","extra":[{"text":"Kette","bold":true,"color":"gold"},{"text":"."}]}',
        ]

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.velocity_rcon.send_player_to_paper", return_value="sent")
    def test_set_builder_gamemode_adventure(
        self, mock_send, mock_rcon, mock_player_rcon, mock_wait
    ):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(ms_username="mccpc01")
        start_builder_session("Kette", duration=90)
        mock_player_rcon.reset_mock()
        session = set_session_gamemode("Kette", "adventure")
        assert session.play_gamemode == MCSession.GAMEMODE_ADVENTURE
        assert session.gamemode_spectator is False
        assert mock_player_rcon.call_args[0][0][0] == "gamemode adventure mccpc01"

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.velocity_rcon.send_player_to_limbo", return_value="ok")
    @patch("minecraft.services.velocity_rcon.send_player_to_paper", return_value="sent")
    def test_end_sends_to_limbo(
        self, mock_paper, mock_limbo, mock_rcon, mock_player_rcon, mock_wait
    ):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(ms_username="mccpc01")
        start_builder_session("Kette", duration=90)
        mock_rcon.reset_mock()
        end_session("Kette")
        mock_limbo.assert_called_once_with("mccpc01")
        first = mock_rcon.call_args_list[0][0][0]
        assert first[0] == "gamemode spectator mccpc01"
        assert "team leave mccpc01" in first
