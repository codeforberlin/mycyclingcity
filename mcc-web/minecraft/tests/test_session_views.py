# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from api.tests.conftest import GroupFactory
from minecraft.models import MCSession, MinecraftIntegrationConfig, MinecraftPlayAccount
from minecraft.services.preset_permissions import (
    user_can_manage_builder_sessions,
    user_can_manage_player_sessions,
)
from minecraft.services.team_registration import register_group_for_minecraft


User = get_user_model()


def _add_perm(user, model, codename):
    content_type = ContentType.objects.get_for_model(model)
    perm = Permission.objects.get(content_type=content_type, codename=codename)
    user.user_permissions.add(perm)
    return User.objects.get(pk=user.pk)


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="Arena1",
        short_name="Arena1",
        display_name="Arena 1",
        sort_order=1,
        is_active=True,
    )


@pytest.fixture
def player_manager(db):
    user = User.objects.create_user(
        username="player_mgr",
        password="secret",
        is_staff=True,
    )
    return _add_perm(user, MinecraftIntegrationConfig, "manage_player_sessions")


@pytest.fixture
def builder_manager(db):
    user = User.objects.create_user(
        username="builder_mgr",
        password="secret",
        is_staff=True,
    )
    return _add_perm(user, MinecraftIntegrationConfig, "manage_builder_sessions")


@pytest.fixture
def builder_registration(db):
    group = GroupFactory(name="Team Alpha", mc_username="team_alpha")
    return register_group_for_minecraft(group)


@pytest.mark.unit
@pytest.mark.django_db
class TestSessionPermissionHelpers:
    def test_player_session_perm(self, player_manager):
        assert user_can_manage_player_sessions(player_manager)
        assert not user_can_manage_builder_sessions(player_manager)

    def test_builder_session_perm(self, builder_manager):
        assert user_can_manage_builder_sessions(builder_manager)
        assert not user_can_manage_player_sessions(builder_manager)

    def test_superuser_both(self, db):
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )
        assert user_can_manage_player_sessions(user)
        assert user_can_manage_builder_sessions(user)


@pytest.mark.django_db
class TestPlayerSessionDashboard:
    def test_list_play_accounts(self, client, player_manager, play_account):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Arena 1" in response.content or b"Arena1" in response.content

    def test_custom_session_hint_from_integration_config(self, client, player_manager, play_account):
        config = MinecraftIntegrationConfig.get_config()
        config.player_session_active_hint = "Pass zurueckgegeben?"
        config.save()
        client.force_login(player_manager)
        response = client.get(reverse("admin:minecraft_player_sessions"))
        assert response.status_code == 200
        assert b"Pass zurueckgegeben?" in response.content

    def test_default_proxy_presence_poll_seconds(self, client, player_manager, play_account):
        client.force_login(player_manager)
        response = client.get(reverse("admin:minecraft_player_sessions"))
        assert response.status_code == 200
        assert response.context["proxy_presence_poll_seconds"] == 10
        assert response.context["proxy_presence_poll_fast_seconds"] == 2
        assert b"data-proxy-presence-poll-seconds', '10'" in response.content
        assert b"data-proxy-presence-poll-fast-seconds', '2'" in response.content

    def test_custom_proxy_presence_poll_seconds(self, client, player_manager, play_account):
        config = MinecraftIntegrationConfig.get_config()
        config.proxy_presence_poll_seconds = 15
        config.save()
        client.force_login(player_manager)
        response = client.get(reverse("admin:minecraft_player_sessions"))
        assert response.status_code == 200
        assert response.context["proxy_presence_poll_seconds"] == 15
        assert b"'15'" in response.content

    def test_empty_session_hint_hidden(self, client, player_manager, play_account):
        config = MinecraftIntegrationConfig.get_config()
        config.player_session_active_hint = ""
        config.save()
        client.force_login(player_manager)
        response = client.get(reverse("admin:minecraft_player_sessions"))
        assert response.status_code == 200
        assert b'<div class="mc-pfand"' not in response.content

    def test_denied_without_perm(self, client, builder_manager, play_account):
        client.force_login(builder_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.get(url)
        assert response.status_code == 302

    @patch("minecraft.session_views.set_all_active_gamemodes", return_value=(2, []))
    def test_set_all_gamemode_ajax(self, mock_bulk, client, player_manager, play_account):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(
            url,
            {"action": "set_all_gamemode", "mode": "spectator"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        mock_bulk.assert_called_once_with("spectator", account_type="PLAYER")
        assert b"Alle Sessions" in client.get(url).content

    @patch("minecraft.session_views.end_all_active_sessions", return_value=(2, []))
    def test_kick_all_ajax(self, mock_kick, client, player_manager, play_account):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(
            url,
            {"action": "kick_all"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        mock_kick.assert_called_once_with(account_type="PLAYER")
        assert b"Alle kicken" in client.get(url).content

    @patch("minecraft.session_views.start_all_idle_sessions", return_value=(2, []))
    def test_start_all_ajax(self, mock_start_all, client, player_manager, play_account):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(
            url,
            {"action": "start_all"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        mock_start_all.assert_called_once()
        assert mock_start_all.call_args.kwargs["account_type"] == "PLAYER"
        assert b"Alle starten" in client.get(url).content

    @patch("minecraft.session_views.start_player_session")
    def test_start_action_ajax_returns_json(self, mock_start, client, player_manager, play_account):
        mock_start.return_value = MagicMock(
            account_name="Arena1",
            duration_minutes=15,
            status="ACTIVE",
            remaining_seconds=900,
            ends_at=timezone.now() + timedelta(minutes=15),
            gamemode_spectator=False,
            play_gamemode="adventure",
            ms_username="mccpc01",
        )
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(
            url,
            {"action": "start", "account": "Arena1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "accounts" in data
        mock_start.assert_called_once()

    @patch("minecraft.session_views.end_session")
    def test_kick_action(self, mock_end, client, player_manager, play_account):
        mock_end.return_value = MagicMock(account_name="Arena1")
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(url, {"action": "kick", "account": "Arena1"})
        assert response.status_code == 302
        mock_end.assert_called_once_with("Arena1")

    @patch("minecraft.session_views.add_session_time")
    def test_add_time_action(self, mock_add, client, player_manager, play_account):
        mock_add.return_value = MagicMock(
            account_name="Arena1",
            ends_at=timezone.now() + timedelta(minutes=30),
        )
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.post(url, {"action": "add_time", "account": "Arena1"})
        assert response.status_code == 302
        mock_add.assert_called_once_with("Arena1")

    @patch("minecraft.session_views.expire_due_sessions")
    def test_dashboard_expires_due_sessions(self, mock_expire, client, player_manager, play_account):
        client.force_login(player_manager)
        response = client.get(reverse("admin:minecraft_player_sessions"))
        assert response.status_code == 200
        mock_expire.assert_called_once()

    def test_json_poll(self, client, player_manager, play_account):
        now = timezone.now()
        MCSession.objects.create(
            account_name="Arena1",
            account_type=MCSession.ACCOUNT_PLAYER,
            timestamp_start=now,
            duration_minutes=15,
            ends_at=now + timedelta(minutes=15),
            status=MCSession.STATUS_ACTIVE,
        )
        client.force_login(player_manager)
        url = reverse("admin:minecraft_player_sessions")
        response = client.get(url, {"format": "json"})
        assert response.status_code == 200
        data = response.json()
        assert data["accounts"][0]["account_name"] == "Arena1"
        assert data["accounts"][0]["status"] == MCSession.STATUS_ACTIVE
        assert data["accounts"][0]["remaining_seconds"] > 0


@pytest.mark.django_db
class TestBuilderSessionDashboard:
    def test_list_builders(self, client, builder_manager, builder_registration):
        client.force_login(builder_manager)
        url = reverse("admin:minecraft_builder_sessions")
        response = client.get(url)
        assert response.status_code == 200
        assert b"team_alpha" in response.content

    def test_default_session_hint(self, client, builder_manager, builder_registration):
        client.force_login(builder_manager)
        response = client.get(reverse("admin:minecraft_builder_sessions"))
        assert response.status_code == 200
        assert "Session ist aktiv!".encode("utf-8") in response.content

    def test_custom_session_hint_from_integration_config(
        self, client, builder_manager, builder_registration
    ):
        config = MinecraftIntegrationConfig.get_config()
        config.builder_session_active_hint = "Werkzeug zurueck?"
        config.save()
        client.force_login(builder_manager)
        response = client.get(reverse("admin:minecraft_builder_sessions"))
        assert response.status_code == 200
        assert b"Werkzeug zurueck?" in response.content

    def test_empty_session_hint_hidden(self, client, builder_manager, builder_registration):
        config = MinecraftIntegrationConfig.get_config()
        config.builder_session_active_hint = ""
        config.save()
        client.force_login(builder_manager)
        response = client.get(reverse("admin:minecraft_builder_sessions"))
        assert response.status_code == 200
        assert b'<div class="mc-pfand"' not in response.content

    def test_denied_without_perm(self, client, player_manager, builder_registration):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_builder_sessions")
        response = client.get(url)
        assert response.status_code == 302

    @patch("minecraft.session_views.start_builder_session")
    def test_start_action(self, mock_start, client, builder_manager, builder_registration):
        mock_start.return_value = MagicMock(
            account_name="team_alpha",
            duration_minutes=90,
        )
        client.force_login(builder_manager)
        url = reverse("admin:minecraft_builder_sessions")
        response = client.post(url, {"action": "start", "account": "team_alpha"})
        assert response.status_code == 302
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0] == "team_alpha"

    @patch("minecraft.session_views.end_session")
    def test_kick_action(self, mock_end, client, builder_manager, builder_registration):
        mock_end.return_value = MagicMock(account_name="team_alpha")
        client.force_login(builder_manager)
        url = reverse("admin:minecraft_builder_sessions")
        response = client.post(url, {"action": "kick", "account": "team_alpha"})
        assert response.status_code == 302
        mock_end.assert_called_once_with("team_alpha")


@pytest.mark.django_db
class TestSessionWorkerCommand:
    @patch("minecraft.management.commands.minecraft_session_worker.expire_due_sessions")
    @patch("minecraft.management.commands.minecraft_session_worker.time.sleep", side_effect=KeyboardInterrupt)
    def test_worker_calls_expire(self, _mock_sleep, mock_expire):
        mock_expire.return_value = []
        call_command("minecraft_session_worker")
        mock_expire.assert_called()


@pytest.mark.django_db
class TestSessionDashboardAjaxErrors:
    @patch("minecraft.session_views.start_builder_session", side_effect=RuntimeError("boom-rcon"))
    def test_start_action_ajax_unexpected_error_returns_json(
        self, mock_start, client, builder_manager, builder_registration
    ):
        client.force_login(builder_manager)
        url = reverse("admin:minecraft_builder_sessions")
        response = client.post(
            url + "?format=json",
            {"action": "start", "account": "team_alpha"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 500
        data = response.json()
        assert data["ok"] is False
        assert "boom-rcon" in data["message"]

