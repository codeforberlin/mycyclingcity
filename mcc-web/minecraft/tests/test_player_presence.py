# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from api.tests.conftest import GroupFactory
from minecraft.models import MCSession, MinecraftTeamRegistration
from minecraft.services.player_presence import (
    PRESENCE_LIMBO,
    PRESENCE_OFFLINE,
    PRESENCE_PAPER,
    parse_glist_players,
    presence_from_server_map,
    strip_mc_colors,
)
from minecraft.services.session_control import reconcile_abandoned_sessions
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
class TestGlistParsing:
    def test_strip_colors(self):
        assert strip_mc_colors("§3[mycyclingcity] §7(1)§r: §amccpc01§r") == "[mycyclingcity] (1): mccpc01"

    def test_parse_glist_players(self):
        raw = "§3[mycyclingcity] §7(2)§r: §rmccpc01, mccpc02§r"
        assert parse_glist_players(raw) == ["mccpc01", "mccpc02"]

    def test_parse_glist_empty(self):
        assert parse_glist_players("§3[limbo] §7(0)§r: §r") == []

    def test_presence_from_map(self):
        mapping = {"mccpc01": "mycyclingcity", "mccpc02": "limbo"}
        paper = presence_from_server_map("mccpc01", mapping)
        limbo = presence_from_server_map("mccpc02", mapping)
        assert paper.state == PRESENCE_PAPER
        assert paper.waiting_in_lobby is False
        assert limbo.state == PRESENCE_LIMBO
        assert limbo.waiting_in_lobby is True
        assert limbo.label_de == "Wartet im Warteraum"
        assert presence_from_server_map("gone", mapping).state == PRESENCE_OFFLINE

    @patch(
        "minecraft.services.player_presence.fetch_paper_online_names",
        return_value={"mccpc01"},
    )
    @patch(
        "minecraft.services.player_presence.fetch_proxy_players_by_server",
        return_value={"mccpc01": "limbo"},
    )
    def test_paper_list_overrides_stale_glist_limbo(self, _glist, _paper):
        from minecraft.services.player_presence import resolve_presences_for_logins

        result = resolve_presences_for_logins(["mccpc01"])
        assert result["mccpc01"].state == PRESENCE_PAPER


@pytest.mark.unit
@pytest.mark.django_db
class TestReconcileAbandonedSessions:
    @pytest.fixture(autouse=True)
    def _online_mode(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "online"
        settings.MCC_MINECRAFT_SESSION_PRESENCE_GRACE_SECONDS = 0

    def _active_builder(self, ms="mccpc01"):
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(ms_username=ms)
        now = timezone.now()
        return MCSession.objects.create(
            account_name="Kette",
            ms_username=ms,
            account_type=MCSession.ACCOUNT_BUILDER,
            timestamp_start=now - timedelta(minutes=5),
            duration_minutes=90,
            ends_at=now + timedelta(minutes=85),
            status=MCSession.STATUS_ACTIVE,
            play_gamemode=MCSession.GAMEMODE_SURVIVAL,
        )

    @patch("minecraft.services.session_control.is_player_online", return_value=False)
    @patch("minecraft.services.session_control.end_session")
    @patch("minecraft.services.player_presence.resolve_presences_for_logins")
    def test_ends_when_player_in_limbo(self, mock_presence, mock_end, _paper):
        from minecraft.services.player_presence import PlayerPresence

        session = self._active_builder()
        mock_presence.return_value = {
            "mccpc01": PlayerPresence(
                ms_username="mccpc01",
                state=PRESENCE_LIMBO,
                server="limbo",
            )
        }
        ended = MCSession.objects.get(pk=session.pk)
        ended.status = MCSession.STATUS_FINISHED
        ended.last_error = ""
        mock_end.return_value = ended

        result = reconcile_abandoned_sessions()
        mock_end.assert_called_once_with("Kette", send_rcon=False)
        assert len(result) == 1

    @patch("minecraft.services.session_control.is_player_online", return_value=True)
    @patch("minecraft.services.session_control.end_session")
    @patch("minecraft.services.player_presence.resolve_presences_for_logins")
    def test_keeps_session_when_glist_limbo_but_paper_online(
        self, mock_presence, mock_end, _paper
    ):
        from minecraft.services.player_presence import PlayerPresence

        self._active_builder()
        mock_presence.return_value = {
            "mccpc01": PlayerPresence(
                ms_username="mccpc01",
                state=PRESENCE_LIMBO,
                server="limbo",
            )
        }
        assert reconcile_abandoned_sessions() == []
        mock_end.assert_not_called()

    @patch("minecraft.services.session_control.end_session")
    @patch("minecraft.services.player_presence.resolve_presences_for_logins")
    def test_keeps_session_when_on_paper(self, mock_presence, mock_end):
        from minecraft.services.player_presence import PlayerPresence

        self._active_builder()
        mock_presence.return_value = {
            "mccpc01": PlayerPresence(
                ms_username="mccpc01",
                state=PRESENCE_PAPER,
                server="mycyclingcity",
            )
        }
        assert reconcile_abandoned_sessions() == []
        mock_end.assert_not_called()

    @patch("minecraft.services.session_control.end_session")
    @patch("minecraft.services.player_presence.resolve_presences_for_logins")
    def test_respects_grace_period(self, mock_presence, mock_end, settings):
        settings.MCC_MINECRAFT_SESSION_PRESENCE_GRACE_SECONDS = 60
        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(ms_username="mccpc01")
        now = timezone.now()
        MCSession.objects.create(
            account_name="Kette",
            ms_username="mccpc01",
            account_type=MCSession.ACCOUNT_BUILDER,
            timestamp_start=now - timedelta(seconds=5),
            duration_minutes=90,
            ends_at=now + timedelta(minutes=90),
            status=MCSession.STATUS_ACTIVE,
            play_gamemode=MCSession.GAMEMODE_SURVIVAL,
        )
        assert reconcile_abandoned_sessions() == []
        mock_presence.assert_not_called()
        mock_end.assert_not_called()
