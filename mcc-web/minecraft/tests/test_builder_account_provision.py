# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.test import override_settings

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftTeamRegistration
from minecraft.services.builder_account_provision import register_builder_account_on_minecraft
from minecraft.services.session_control import RconSequenceError, SessionControlError
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
@pytest.mark.django_db
class TestBuilderAccountProvision:
    @override_settings(
        MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret",
        MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="ArenaSecret",
    )
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    def test_register_uses_builder_password(self, mock_rcon):
        group = GroupFactory(name="Team A", mc_username="team_a")
        registration = register_group_for_minecraft(group)
        log = register_builder_account_on_minecraft(registration)
        assert log == "ok"
        mock_rcon.assert_called_once_with(
            ["authme register team_a BuilderSecret"],
            stop_on_error=True,
        )
        registration.refresh_from_db()
        assert registration.authme_is_registered is True
        assert registration.authme_registered_at is not None

    @override_settings(
        MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="",
        MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="ArenaSecret",
    )
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    def test_register_falls_back_to_play_password(self, mock_rcon):
        group = GroupFactory(name="Team B", mc_username="team_b")
        registration = register_group_for_minecraft(group)
        register_builder_account_on_minecraft(registration)
        mock_rcon.assert_called_once_with(
            ["authme register team_b ArenaSecret"],
            stop_on_error=True,
        )

    @override_settings(
        MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="",
        MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="",
    )
    def test_missing_password_raises(self):
        registration = MinecraftTeamRegistration.objects.create(
            group=GroupFactory(name="Team C", mc_username="team_c"),
            mc_username="team_c",
        )
        with pytest.raises(SessionControlError) as exc:
            register_builder_account_on_minecraft(registration)
        assert exc.value.code == "password_not_configured"

    @override_settings(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret")
    @patch(
        "minecraft.services.authme_provision.run_commands",
        return_value=(False, "authme register team_a *** -> FEHLER: already registered"),
    )
    def test_already_registered_treated_as_ok(self, mock_rcon):
        group = GroupFactory(name="Team D", mc_username="team_d")
        registration = register_group_for_minecraft(group)
        register_builder_account_on_minecraft(registration)
        registration.refresh_from_db()
        assert registration.authme_is_registered is True

    @override_settings(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret")
    @patch(
        "minecraft.services.authme_provision.run_commands",
        return_value=(False, "authme register team_e x -> FEHLER: boom"),
    )
    def test_rcon_failure(self, mock_rcon):
        group = GroupFactory(name="Team E", mc_username="team_e")
        registration = register_group_for_minecraft(group)
        with pytest.raises(RconSequenceError):
            register_builder_account_on_minecraft(registration)
        registration.refresh_from_db()
        assert registration.authme_is_registered is False
        assert "boom" in registration.authme_last_error


@pytest.mark.unit
@pytest.mark.django_db
class TestRegisterTeamOnServerAuthMe:
    @pytest.fixture(autouse=True)
    def _legacy_auth(self, settings):
        settings.MCC_MINECRAFT_SESSION_AUTH_MODE = "authme"
        settings.MCC_MINECRAFT_LP_SYNC_ENABLED = True

    @override_settings(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret")
    @patch("minecraft.services.bridge_team_mapping.push_team_mapping_to_bridge")
    @patch("minecraft.services.luckperms_sync.rcon_client.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.team_scoreboard.set_team_spendable_score")
    @patch("minecraft.services.team_scoreboard.ensure_team_scoreboard_objective", return_value="obj")
    def test_register_team_provisions_authme(
        self,
        mock_ensure,
        mock_set_score,
        mock_authme_rcon,
        mock_lp_rcon,
        mock_bridge,
    ):
        from minecraft.services.team_scoreboard import register_team_on_server

        group = GroupFactory(name="Kette", mc_username="Kette", velos_spendable=100)
        registration = register_group_for_minecraft(group)
        assert registration.authme_is_registered is False

        register_team_on_server(registration)

        mock_authme_rcon.assert_called_once_with(
            ["authme register Kette BuilderSecret"],
            stop_on_error=True,
        )
        mock_bridge.assert_called_once_with("Kette")
        registration.refresh_from_db()
        assert registration.authme_is_registered is True

    @override_settings(MCC_MINECRAFT_BUILDER_ACCOUNT_PASSWORD="BuilderSecret")
    @patch("minecraft.services.bridge_team_mapping.push_team_mapping_to_bridge")
    @patch("minecraft.services.luckperms_sync.rcon_client.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    @patch("minecraft.services.team_scoreboard.set_team_spendable_score")
    @patch("minecraft.services.team_scoreboard.ensure_team_scoreboard_objective", return_value="obj")
    def test_register_team_skips_authme_when_already_registered(
        self,
        mock_ensure,
        mock_set_score,
        mock_authme_rcon,
        mock_lp_rcon,
        mock_bridge,
    ):
        from minecraft.services.team_scoreboard import register_team_on_server

        group = GroupFactory(name="Kette", mc_username="Kette", velos_spendable=100)
        registration = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=registration.pk).update(
            authme_is_registered=True,
        )
        registration.refresh_from_db()

        register_team_on_server(registration)

        mock_authme_rcon.assert_not_called()
        mock_bridge.assert_called_once_with("Kette")
