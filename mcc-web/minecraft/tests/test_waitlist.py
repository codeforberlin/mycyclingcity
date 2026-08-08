# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from datetime import timedelta
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from api.tests.conftest import GroupFactory, UserFactory
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftPlayAccount,
    MinecraftSessionWaitlistEntry,
)
from minecraft.services.waitlist_service import (
    WaitlistError,
    add_waitlist_entry,
    build_display_payload,
    cancel_waitlist_entry,
    duration_from_velos,
)


@pytest.fixture
def waitlist_config(db):
    config = MinecraftIntegrationConfig.get_config()
    config.player_velos_per_minute = 20
    config.player_min_velos = 300
    config.waitlist_public_enabled = True
    config.waitlist_public_token = "test-public-token"
    config.save()
    return config


@pytest.fixture
def player_manager(db):
    user = UserFactory(username="waitlist_mgr", is_staff=True)
    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(codename="manage_player_sessions", content_type=ct)
    user.user_permissions.add(perm)
    return user


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="Arena1",
        short_name="Arena1",
        display_name="PC 1",
        sort_order=1,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestWaitlistService:
    def test_duration_from_velos(self, waitlist_config):
        assert duration_from_velos(300, config=waitlist_config) == 15

    def test_add_player_entry(self, waitlist_config, player_manager):
        entry = add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="4827",
            guest_label="Lisa M.",
            velos_cost=300,
            user=player_manager,
        )
        assert entry.ticket_number == "4827"
        assert entry.duration_minutes == 15
        assert entry.status == MinecraftSessionWaitlistEntry.STATUS_WAITING

    def test_reject_duplicate_ticket(self, waitlist_config, player_manager):
        add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="4827",
            velos_cost=300,
            user=player_manager,
        )
        with pytest.raises(WaitlistError) as exc:
            add_waitlist_entry(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                ticket_number="4827",
                velos_cost=300,
            )
        assert exc.value.code == "ticket_duplicate"

    def test_reject_low_velos(self, waitlist_config):
        with pytest.raises(WaitlistError) as exc:
            add_waitlist_entry(
                queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
                ticket_number="1111",
                velos_cost=100,
            )
        assert exc.value.code == "velos_too_low"

    def test_assign_player_from_waitlist(self, waitlist_config, player_manager, play_account):
        from minecraft.services.waitlist_service import assign_player_from_waitlist

        entry = add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="9001",
            velos_cost=300,
            user=player_manager,
        )
        updated = assign_player_from_waitlist(entry.pk, "Arena1", user=player_manager)
        assert updated.status == MinecraftSessionWaitlistEntry.STATUS_ASSIGNED
        assert updated.assigned_play_account_id == play_account.pk
        assert updated.mc_session_id is None

    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    def test_session_start_activates_assigned_waitlist(
        self, _rcon, _player_rcon, _wait, waitlist_config, player_manager, play_account
    ):
        from minecraft.services.session_control import start_player_session
        from minecraft.services.waitlist_service import assign_player_from_waitlist

        entry = add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="9002",
            velos_cost=600,
            user=player_manager,
        )
        assign_player_from_waitlist(entry.pk, "Arena1", user=player_manager)
        session = start_player_session("Arena1", user=player_manager)
        entry.refresh_from_db()
        assert session.duration_minutes == 30
        assert entry.status == MinecraftSessionWaitlistEntry.STATUS_ACTIVE
        assert entry.mc_session_id == session.pk

    def test_public_payload_hides_private_fields(self, waitlist_config, player_manager):
        add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="5555",
            guest_label="Secret Name",
            velos_cost=300,
            user=player_manager,
        )
        public = build_display_payload(include_private=False)
        assert public["player_queue"][0]["ticket_number"] == "5555"
        assert "guest_label" not in public["player_queue"][0]

        staff = build_display_payload(include_private=True)
        assert staff["player_queue"][0]["guest_label"] == "Secret Name"

    def test_generate_ticket_numbers_unique(self, waitlist_config):
        from minecraft.services.waitlist_service import generate_ticket_numbers

        tickets = generate_ticket_numbers(10)
        assert len(tickets) == 10
        assert len(set(tickets)) == 10
        for ticket in tickets:
            assert ticket.isdigit()
            assert 1000 <= int(ticket) <= 9999


@pytest.mark.unit
@pytest.mark.django_db
class TestWaitlistViews:
    def test_public_display_disabled_returns_404(self, waitlist_config):
        waitlist_config.waitlist_public_enabled = False
        waitlist_config.save()
        client = Client()
        url = reverse(
            "minecraft_waitlist_public_display",
            kwargs={"token": waitlist_config.waitlist_public_token},
        )
        response = client.get(url)
        assert response.status_code == 404

    def test_public_display_anonymous(self, waitlist_config, player_manager):
        add_waitlist_entry(
            queue_type=MinecraftSessionWaitlistEntry.QUEUE_PLAYER,
            ticket_number="1234",
            guest_label="Hidden",
            velos_cost=300,
            user=player_manager,
        )
        client = Client()
        url = reverse(
            "minecraft_waitlist_public_display",
            kwargs={"token": waitlist_config.waitlist_public_token},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "1234" in response.content.decode()
        assert "Hidden" not in response.content.decode()

    def test_staff_display_requires_login(self, waitlist_config):
        client = Client()
        url = reverse("admin:minecraft_waitlist_display")
        response = client.get(url)
        assert response.status_code in (302, 403)

    def test_manage_requires_permission(self, db):
        user = UserFactory(username="waitlist_no_perm", is_staff=True)
        client = Client()
        client.force_login(user)
        url = reverse("admin:minecraft_waitlist_manage")
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_manage_access(self, waitlist_config, player_manager):
        client = Client()
        client.force_login(player_manager)
        url = reverse("admin:minecraft_waitlist_manage")
        response = client.get(url)
        assert response.status_code == 200
