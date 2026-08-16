# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from minecraft.models import (
    MCSession,
    MinecraftGrantCatalogItem,
    MinecraftGrantRecord,
    MinecraftPlayAccount,
)
from minecraft.services.grant_catalog import (
    build_grant_commands,
    clear_active_grants_for_account,
    ensure_default_catalog_items,
    normalize_grant_slugs,
    render_rcon_template,
    summarize_active_grants,
)
from minecraft.services.player_session_bootstrap import build_player_post_login_commands
from minecraft.services.session_control import start_player_session


@pytest.mark.unit
@pytest.mark.django_db
class TestGrantCatalogHelpers:
    def test_ensure_default_and_normalize(self):
        ensure_default_catalog_items()
        item = MinecraftGrantCatalogItem.objects.get(slug="example-bike")
        assert item.model_id == "ExampleBike"
        slugs = normalize_grant_slugs(
            ["example-bike", "missing", "example-bike"],
            account_type=MCSession.ACCOUNT_PLAYER,
        )
        assert slugs == ["example-bike"]

    def test_render_and_build_commands(self):
        ensure_default_catalog_items()
        item = MinecraftGrantCatalogItem.objects.get(slug="example-bike")
        cmd = render_rcon_template(
            item.rcon_grant_template,
            player="Arena1",
            item=item,
        )
        assert cmd == "v give Arena1 ExampleBike"
        assert build_grant_commands(
            "Arena1",
            ["example-bike"],
            account_type=MCSession.ACCOUNT_PLAYER,
        ) == ["v give Arena1 ExampleBike"]

    @patch("minecraft.services.sidebar_visibility.ensure_arena_station_team")
    def test_post_login_includes_grants(self, _mock_team):
        ensure_default_catalog_items()
        commands = build_player_post_login_commands(
            "Arena1",
            emerald_count=0,
            grant_catalog_slugs=["example-bike"],
        )
        assert "v give Arena1 ExampleBike" in commands

    def test_clear_and_summary(self):
        ensure_default_catalog_items()
        item = MinecraftGrantCatalogItem.objects.get(slug="example-bike")
        MinecraftGrantRecord.objects.create(
            catalog_item=item,
            account_name="Arena1",
            account_type=MCSession.ACCOUNT_PLAYER,
            source=MinecraftGrantRecord.SOURCE_SESSION,
            status=MinecraftGrantRecord.STATUS_ACTIVE,
        )
        MinecraftGrantRecord.objects.create(
            catalog_item=item,
            account_name="Arena1",
            account_type=MCSession.ACCOUNT_PLAYER,
            source=MinecraftGrantRecord.SOURCE_VELOS,
            status=MinecraftGrantRecord.STATUS_ACTIVE,
            velos_charged=1000,
        )
        summary = summarize_active_grants("Arena1")
        assert summary.total_active == 2
        assert summary.session_grants == 1
        assert summary.velos_redeems == 1
        count, cmds = clear_active_grants_for_account("Arena1")
        assert count == 2
        assert cmds[0] == "mccbridge vpremove Arena1 *"
        assert summarize_active_grants("Arena1").total_active == 0

    def test_clear_wipes_garage_without_active_rows(self):
        ensure_default_catalog_items()
        MinecraftPlayAccount.objects.create(
            id_tag="Arena1",
            short_name="Arena1",
            ms_username="Tandemino",
        )
        count, cmds = clear_active_grants_for_account("Arena1", commit=True)
        assert count == 0
        assert cmds == ["mccbridge vpremove Tandemino *"]


@pytest.mark.unit
@pytest.mark.django_db
class TestGrantOnSessionStart:
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
            is_active=True,
        )

    @patch("minecraft.services.session_control._apply_effects_when_online")
    @patch("minecraft.services.session_control._transfer_player_to_game")
    @patch("minecraft.services.session_control.is_player_online", return_value=True)
    def test_start_with_grant_slug(
        self,
        _online,
        _transfer,
        mock_effects,
        play_account,
    ):
        ensure_default_catalog_items()
        mock_effects.return_value = (True, "")
        session = start_player_session(
            "Arena1",
            grant_catalog_slugs=["example-bike"],
        )
        assert session.grant_catalog_slugs == ["example-bike"]
        post_cmds = mock_effects.call_args[0][1]
        assert "v give Arena1 ExampleBike" in post_cmds
        assert MinecraftGrantRecord.objects.filter(
            account_name="Arena1",
            status=MinecraftGrantRecord.STATUS_ACTIVE,
            catalog_item__slug="example-bike",
        ).exists()
