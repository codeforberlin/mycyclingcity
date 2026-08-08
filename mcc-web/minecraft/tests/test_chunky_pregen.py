# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services.chunky_pregen import (
    border_size_to_chunky_radius,
    border_to_chunky_selection,
    build_chunky_start_commands,
)


@pytest.mark.unit
class TestChunkySelection:
    def test_radius_half_of_border_size(self):
        assert border_size_to_chunky_radius(1000) == 500
        assert border_size_to_chunky_radius(501) == 250

    @pytest.mark.django_db
    @override_settings(MCC_MINECRAFT_PAPER_WORLD="MyCyclingCity")
    def test_border_to_selection(self):
        cfg = MinecraftIntegrationConfig.get_config()
        cfg.world_border_center_x = 10
        cfg.world_border_center_z = -20
        cfg.world_border_size = 1000
        cfg.save()
        sel = border_to_chunky_selection(cfg)
        assert sel["world"] == "MyCyclingCity"
        assert sel["center_x"] == 10.0
        assert sel["center_z"] == -20.0
        assert sel["radius"] == 500
        assert sel["edge"] == 1000

    def test_build_start_commands_from_config(self):
        selection = {
            "world": "MyCyclingCity",
            "center_x": 0,
            "center_z": 0,
            "radius": 500,
        }
        cmds = build_chunky_start_commands(selection, quiet=30)
        assert cmds == [
            "chunky quiet 30",
            "chunky world MyCyclingCity",
            "chunky shape square",
            "chunky center 0 0",
            "chunky radius 500",
            "chunky start",
        ]

    def test_build_start_commands_live_border(self):
        selection = {"world": "MyCyclingCity", "center_x": 0, "center_z": 0, "radius": 500}
        cmds = build_chunky_start_commands(selection, use_live_worldborder=True)
        assert "chunky worldborder" in cmds
        assert "chunky center 0 0" not in cmds
        assert cmds[-1] == "chunky start"


def _add_city_perm(user):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(content_type=ct, codename="access_minecraft_city")
    user.user_permissions.add(perm)
    return type(user).objects.get(pk=user.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestChunkyCityView:
    @patch(
        "minecraft.services.chunky_pregen.rcon_client.run_commands",
        return_value=(True, "Task started"),
    )
    def test_start_calls_rcon(self, mock_run):
        cfg = MinecraftIntegrationConfig.get_config()
        cfg.world_border_size = 1000
        cfg.world_border_center_x = 0
        cfg.world_border_center_z = 0
        cfg.save()
        user = _add_city_perm(UserFactory(is_staff=True, is_superuser=False))
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "chunky_pregen",
                "action": "start",
                "chunky_radius": "500",
                "chunky_quiet": "30",
            },
        )
        assert response.status_code == 302
        assert mock_run.called
        cmds = mock_run.call_args[0][0]
        assert cmds[0] == "chunky quiet 30"
        assert "chunky radius 500" in cmds
        assert cmds[-1] == "chunky start"
