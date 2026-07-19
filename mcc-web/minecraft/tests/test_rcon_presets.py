# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from minecraft.models import MinecraftRconPreset
from minecraft.services.rcon_presets import presets_grouped, run_preset


User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestRconPresetsService:
    def test_presets_grouped_only_enabled(self):
        MinecraftRconPreset.objects.create(
            slug="enabled-world",
            name="Enabled",
            category=MinecraftRconPreset.CATEGORY_WORLD,
            commands=["time set day"],
            enabled=True,
        )
        MinecraftRconPreset.objects.create(
            slug="disabled-world",
            name="Disabled",
            category=MinecraftRconPreset.CATEGORY_WORLD,
            commands=["time set night"],
            enabled=False,
        )

        groups = presets_grouped()
        names = [preset.name for group in groups for preset in group["presets"]]

        assert "Enabled" in names
        assert "Disabled" not in names

    @patch("minecraft.services.rcon_presets.rcon_client.run_commands")
    def test_run_preset_success(self, mock_run_commands):
        preset = MinecraftRconPreset.objects.create(
            slug="day",
            name="Tag",
            commands=["time set day", "weather clear"],
        )
        mock_run_commands.return_value = (True, "time set day -> (ok)")

        success, message = run_preset(preset.id)

        assert success is True
        assert "Tag" in message
        mock_run_commands.assert_called_once_with(["time set day", "weather clear"])

    @patch("minecraft.services.rcon_presets.rcon_client.run_commands")
    def test_run_preset_failure(self, mock_run_commands):
        preset = MinecraftRconPreset.objects.create(
            slug="broken",
            name="Broken",
            commands=["not-a-command"],
        )
        mock_run_commands.return_value = (False, "not-a-command -> FEHLER: bad")

        success, message = run_preset(preset.id)

        assert success is False
        assert "Broken" in message
        assert "FEHLER" in message


@pytest.mark.unit
@pytest.mark.django_db
class TestRconClientRunCommands:
    @patch("minecraft.services.rcon_client._send_command")
    def test_run_commands_stops_on_error(self, mock_send):
        from mcrcon import MCRconException

        from minecraft.services.rcon_client import run_commands

        mock_send.side_effect = ["ok", MCRconException("boom")]

        success, output = run_commands(["time set day", "bad cmd"])

        assert success is False
        assert "FEHLER" in output
        assert mock_send.call_count == 2


@pytest.mark.django_db
class TestMinecraftRunPresetView:
    @pytest.fixture
    def superuser(self):
        return User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )

    @pytest.fixture
    def preset(self):
        return MinecraftRconPreset.objects.create(
            slug="night",
            name="Nacht",
            commands=["time set night"],
        )

    @patch("minecraft.preset_views.run_preset")
    def test_run_preset_requires_superuser(self, mock_run_preset, client, preset):
        mock_run_preset.return_value = (True, "ok")
        url = reverse("admin:minecraft_run_preset", args=[preset.id])

        response = client.post(url)

        assert response.status_code in (302, 403)

    @patch("minecraft.preset_views.run_preset")
    def test_run_preset_success(self, mock_run_preset, client, superuser, preset):
        mock_run_preset.return_value = (True, "Preset „Nacht“:\ntime set night -> (ok)")
        client.force_login(superuser)
        url = reverse("admin:minecraft_run_preset", args=[preset.id])

        response = client.post(url)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_run_preset.assert_called_once()
        assert mock_run_preset.call_args.kwargs.get("user") == superuser
