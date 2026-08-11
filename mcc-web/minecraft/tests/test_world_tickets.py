# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from api.tests.conftest import CyclistFactory, GroupFactory
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftPlayAccount,
    MinecraftSessionWaitlistEntry,
)
from minecraft.services.player_session_bootstrap import build_player_post_login_commands
from minecraft.services.session_control import (
    InsufficientVelosError,
    start_player_session,
)
from minecraft.services.waitlist_service import add_waitlist_entry, assign_player_from_waitlist
from minecraft.services.world_tickets import (
    build_world_ticket_give_command,
    get_world_ticket_settings,
    normalize_ticket_count,
    ticket_cost_velos,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestWorldTicketHelpers:
    def test_defaults(self):
        settings = get_world_ticket_settings()
        assert settings.enabled is True
        assert settings.velos_per_ticket == 100
        assert settings.max_count == 10

    def test_normalize_clamps_and_respects_disabled(self):
        config = MinecraftIntegrationConfig.get_config()
        config.world_ticket_max = 5
        config.save(update_fields=["world_ticket_max"])
        assert normalize_ticket_count(3, config=config) == 3
        assert normalize_ticket_count(99, config=config) == 5
        assert normalize_ticket_count(-1, config=config) == 0
        assert normalize_ticket_count("x", config=config) == 0

        config.world_ticket_enabled = False
        config.save(update_fields=["world_ticket_enabled"])
        assert normalize_ticket_count(4, config=config) == 0

    def test_give_command_shape(self):
        cmd = build_world_ticket_give_command("Arena1", 3)
        assert cmd is not None
        assert cmd.startswith("give Arena1 paper[")
        assert "custom_data={mcc_ticket:true}" in cmd
        assert 'color:"gold"' in cmd
        assert "item_name=" in cmd
        assert cmd.endswith("] 3")
        assert build_world_ticket_give_command("Arena1", 0) is None

    def test_ticket_cost(self):
        config = MinecraftIntegrationConfig.get_config()
        config.world_ticket_velos = 100
        config.save(update_fields=["world_ticket_velos"])
        assert ticket_cost_velos(2, config=config) == 200

    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_post_login_includes_tickets(self, _mock_team):
        commands = build_player_post_login_commands(
            "Arena1",
            emerald_count=4,
            world_ticket_count=2,
        )
        assert "give Arena1 minecraft:emerald 4" in commands
        ticket_cmds = [c for c in commands if "mcc_ticket:true" in c]
        assert len(ticket_cmds) == 1
        assert ticket_cmds[0].endswith("] 2")


@pytest.mark.unit
@pytest.mark.django_db
class TestWorldTicketsOnSessionStart:
    @pytest.fixture(autouse=True)
    def _authme_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"
        settings.MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED = False

    @pytest.fixture(autouse=True)
    def _mock_sidebar_routing(self):
        with (
            patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams"),
            patch("minecraft.services.sidebar_visibility.ensure_arena_station_team"),
        ):
            yield

    @pytest.fixture
    def play_account(self, db):
        return MinecraftPlayAccount.objects.create(
            id_tag="Arena1",
            short_name="Arena1",
            display_name="Arena 1",
            sort_order=1,
        )

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_flyer_start_gives_tickets_without_debit(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account
    ):
        session = start_player_session("Arena1", duration=15, ticket_count=3)
        assert session.world_ticket_count == 3
        player_cmds = mock_player_rcon.call_args[0][0]
        assert any("mcc_ticket:true" in c and c.endswith("] 3") for c in player_cmds)

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_radler_debits_n_times_price(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account
    ):
        leaf = GroupFactory(name="Ticket Leaf")
        cyclist = CyclistFactory(velos_balance=500)
        cyclist.groups.set([leaf])
        entry = add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="4821",
            velos_cost=300,
            guest_label="Kid",
            source=MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM,
            cyclist=cyclist,
        )
        assign_player_from_waitlist(entry.pk, "Arena1")

        session = start_player_session("Arena1", ticket_count=2)
        assert session.world_ticket_count == 2
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 300  # 500 - 2*100

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_insufficient_velos_rejects_start(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account
    ):
        leaf = GroupFactory(name="Ticket Leaf Low")
        cyclist = CyclistFactory(velos_balance=50)
        cyclist.groups.set([leaf])
        entry = add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="4822",
            velos_cost=300,
            guest_label="Kid",
            source=MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM,
            cyclist=cyclist,
        )
        assign_player_from_waitlist(entry.pk, "Arena1")

        with pytest.raises(InsufficientVelosError):
            start_player_session("Arena1", ticket_count=2)
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 50
        assert mock_rcon.call_count == 0

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_ticket_count_clamped_to_max(
        self, mock_rcon, mock_player_rcon, mock_wait, play_account
    ):
        config = MinecraftIntegrationConfig.get_config()
        config.world_ticket_max = 3
        config.save(update_fields=["world_ticket_max"])
        session = start_player_session("Arena1", duration=15, ticket_count=99)
        assert session.world_ticket_count == 3
