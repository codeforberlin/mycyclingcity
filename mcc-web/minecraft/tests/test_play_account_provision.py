# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.test import override_settings

from minecraft.models import MinecraftPlayAccount
from minecraft.services.play_account_provision import register_play_account_on_minecraft
from minecraft.services.session_control import RconSequenceError, SessionControlError


@pytest.mark.unit
@pytest.mark.django_db
class TestPlayAccountProvision:
    @override_settings(MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="ArenaSecret")
    @patch("minecraft.services.authme_provision.run_commands", return_value=(True, "ok"))
    def test_register_sends_authme_register(self, mock_rcon):
        account = MinecraftPlayAccount.objects.create(id_tag="Arena1", short_name="Arena1")
        log = register_play_account_on_minecraft(account)
        assert log == "ok"
        mock_rcon.assert_called_once_with(
            ["authme register Arena1 ArenaSecret"],
            stop_on_error=True,
        )
        account.refresh_from_db()
        assert account.authme_is_registered is True
        assert account.authme_registered_at is not None
        assert account.authme_last_error == ""

    @override_settings(MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="ArenaSecret")
    @patch(
        "minecraft.services.authme_provision.run_commands",
        return_value=(False, "authme register Arena1 *** -> FEHLER: already registered"),
    )
    def test_already_registered_treated_as_ok(self, mock_rcon):
        account = MinecraftPlayAccount.objects.create(id_tag="Arena2", short_name="Arena2")
        register_play_account_on_minecraft(account)
        account.refresh_from_db()
        assert account.authme_is_registered is True

    @override_settings(MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="")
    def test_missing_password_raises(self):
        account = MinecraftPlayAccount.objects.create(id_tag="Arena3", short_name="Arena3")
        with pytest.raises(SessionControlError) as exc:
            register_play_account_on_minecraft(account)
        assert exc.value.code == "password_not_configured"

    @override_settings(MCC_MINECRAFT_PLAY_ACCOUNT_PASSWORD="ArenaSecret")
    @patch(
        "minecraft.services.authme_provision.run_commands",
        return_value=(False, "authme register Arena1 x -> FEHLER: boom"),
    )
    def test_rcon_failure(self, mock_rcon):
        account = MinecraftPlayAccount.objects.create(id_tag="Arena4", short_name="Arena4")
        with pytest.raises(RconSequenceError):
            register_play_account_on_minecraft(account)
        account.refresh_from_db()
        assert account.authme_is_registered is False
        assert "boom" in account.authme_last_error
