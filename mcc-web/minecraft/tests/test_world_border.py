# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services.world_border import (
    WORLD_BORDER_DISABLED_SIZE,
    build_world_border_commands,
    parse_world_border_get,
    preview_half_extent,
    read_spawn_from_server_properties,
)


@pytest.mark.unit
class TestWorldBorderCommands:
    def test_build_enabled_1000(self):
        cmds = build_world_border_commands(
            center_x=10,
            center_z=-20,
            size=1000,
            warning_distance=5,
            damage_amount=0.2,
            enabled=True,
        )
        assert cmds == [
            "worldborder center 10 -20",
            "worldborder set 1000",
            "worldborder warning distance 5",
            "worldborder damage amount 0.2",
        ]

    def test_build_disabled_uses_max(self):
        cmds = build_world_border_commands(
            center_x=0,
            center_z=0,
            size=1000,
            enabled=False,
        )
        assert cmds[1] == f"worldborder set {WORLD_BORDER_DISABLED_SIZE}"

    def test_preview_half(self):
        assert preview_half_extent(1000) == 500.0

    def test_parse_get_english(self):
        parsed = parse_world_border_get("The world border is currently 1000.0 blocks wide")
        assert parsed["size"] == 1000.0
        assert parsed["enabled"] is True

    def test_parse_get_disabled(self):
        parsed = parse_world_border_get(f"The world border is currently {WORLD_BORDER_DISABLED_SIZE} blocks wide")
        assert parsed["enabled"] is False


@pytest.mark.unit
def test_read_spawn_from_server_properties(tmp_path: Path):
    props = tmp_path / "server.properties"
    props.write_text("spawn-x=128.5\nspawn-z=-64\n", encoding="utf-8")
    assert read_spawn_from_server_properties(str(tmp_path)) == (128.5, -64.0)


def _add_city_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(content_type=ct, codename="access_minecraft_city")
    user.user_permissions.add(perm)
    return type(user).objects.get(pk=user.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestWorldBorderCityView:
    @patch("minecraft.services.world_border.rcon_client.run_commands", return_value=(True, "ok"))
    def test_apply_saves_and_runs_rcon(self, mock_run):
        MinecraftIntegrationConfig.get_config()
        user = _add_city_perm(UserFactory(is_staff=True, is_superuser=False))
        client = Client()
        client.force_login(user)
        url = reverse("admin:minecraft_city")
        response = client.post(
            url,
            {
                "form_type": "world_border",
                "action": "apply",
                "world_border_center_x": "12",
                "world_border_center_z": "34",
                "world_border_size": "500",
                "world_border_warning_distance": "5",
                "world_border_damage_amount": "0.2",
            },
        )
        assert response.status_code == 302
        cfg = MinecraftIntegrationConfig.get_config()
        assert cfg.world_border_center_x == 12.0
        assert cfg.world_border_center_z == 34.0
        assert cfg.world_border_size == 500
        assert cfg.world_border_enabled is True
        assert mock_run.called
        assert mock_run.call_args[0][0][0] == "worldborder center 12 34"
        assert mock_run.call_args[0][0][1] == "worldborder set 500"
