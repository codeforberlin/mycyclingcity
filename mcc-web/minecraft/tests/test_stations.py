# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftMsAllowlistEntry,
    MinecraftPlayAccount,
    MinecraftStation,
)
from minecraft.services.session_control import (
    MsAllowlistError,
    StationBusyError,
    start_player_session,
)
from minecraft.services.station_admin import (
    add_allowlist_entry,
    create_station,
    is_ms_login_allowed,
)


@pytest.fixture
def station_manager(db):
    user = UserFactory(username="station_mgr", is_staff=True)
    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(codename="manage_minecraft_stations", content_type=ct)
    user.user_permissions.add(perm)
    return user


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="Arena1",
        short_name="Arena1",
        display_name="PC 1",
        ms_username="DefaultPlayer",
        sort_order=1,
    )


@pytest.mark.django_db
class TestStationAdmin:
    def test_create_station_and_allowlist(self, station_manager):
        station = create_station({"name": "PC-Nord", "role": "both", "sort_order": 1})
        assert station.name == "PC-Nord"
        entry = add_allowlist_entry(ms_username="FezKid1", station_id=None, user=station_manager)
        assert entry.ms_username == "FezKid1"
        assert is_ms_login_allowed("FezKid1") is True
        assert is_ms_login_allowed("UnknownKid") is False

    def test_stations_view_requires_permission(self):
        user = UserFactory(is_staff=True)
        client = Client()
        client.force_login(user)
        response = client.get(reverse("admin:minecraft_stations"))
        assert response.status_code == 403

    def test_stations_view_ok(self, station_manager):
        create_station({"name": "PC-A", "role": "play"})
        client = Client()
        client.force_login(station_manager)
        response = client.get(reverse("admin:minecraft_stations"))
        assert response.status_code == 200
        assert b"PC-A" in response.content


@pytest.mark.django_db
class TestSessionMsOverride:
    @pytest.fixture(autouse=True)
    def _authme_offline(self, settings):
        # Online mode requires allowlist; use online for these tests.
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "online"

    @pytest.fixture(autouse=True)
    def _minimal_bootstrap(self, settings):
        settings.MCC_MINECRAFT_PLAYER_SESSION_BOOTSTRAP_ENABLED = False

    @patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams")
    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.session_control._transfer_player_to_game", return_value="ok")
    def test_override_must_be_allowlisted(
        self, _transfer, _rcon, _player_rcon, _wait, _arena, _sidebar, play_account
    ):
        MinecraftMsAllowlistEntry.objects.create(ms_username="AllowedKid", is_active=True)
        with pytest.raises(MsAllowlistError):
            start_player_session("Arena1", duration=15, ms_username="NotAllowed")

    @patch("minecraft.services.sidebar_visibility.ensure_sidebar_routing_teams")
    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    @patch("minecraft.services.session_control.wait_for_player_online", return_value=True)
    @patch(
        "minecraft.services.session_control.run_commands_require_player",
        return_value=(True, "ok"),
    )
    @patch("minecraft.services.session_control.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.session_control._transfer_player_to_game", return_value="ok")
    def test_override_and_station(
        self, _transfer, _rcon, _player_rcon, _wait, _arena, _sidebar, play_account
    ):
        MinecraftMsAllowlistEntry.objects.create(ms_username="AllowedKid", is_active=True)
        MinecraftMsAllowlistEntry.objects.create(ms_username="DefaultPlayer", is_active=True)
        station = MinecraftStation.objects.create(name="PC-Test", role="play", is_active=True)

        session = start_player_session(
            "Arena1",
            duration=15,
            ms_username="AllowedKid",
            station_id=station.pk,
        )
        assert session.ms_username == "AllowedKid"
        assert session.station_id == station.pk
        assert session.account_name == "Arena1"

        with pytest.raises(StationBusyError):
            start_player_session(
                "Arena1",
                duration=15,
                ms_username="AllowedKid",
                station_id=station.pk,
            )
