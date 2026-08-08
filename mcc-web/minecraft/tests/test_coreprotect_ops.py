# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services.coreprotect_ops import (
    build_co_command,
    build_co_lookup_count_command,
    normalize_time_spec,
)
from minecraft.services.preset_permissions import user_can_manage_coreprotect


@pytest.mark.unit
class TestCoreProtectCommands:
    def test_rollback_always_has_radius(self):
        cmd = build_co_command("rollback", "mccpc01", "2h", radius="#global")
        assert cmd == "co rollback u:mccpc01 t:2h r:#global a:block"

    def test_preview_hashtag(self):
        cmd = build_co_command(
            "rollback", "mccpc01", "30m", radius="#global", preview=True
        )
        assert "#preview" in cmd

    def test_lookup_count(self):
        cmd = build_co_lookup_count_command("Arena1", "1h")
        assert cmd.endswith("#count")
        assert "r:#global" in cmd

    def test_rejects_bad_time(self):
        with pytest.raises(ValueError):
            normalize_time_spec("drop table")

    def test_rejects_bad_radius(self):
        with pytest.raises(ValueError):
            build_co_command("rollback", "mccpc01", "1h", radius="#nether")


def _add_perm(user, codename: str):
    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    user.user_permissions.add(perm)
    return type(user).objects.get(pk=user.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestCoreProtectPermission:
    def test_explicit_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "manage_coreprotect")
        assert user_can_manage_coreprotect(user)

    def test_city_alone_not_enough(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        assert not user_can_manage_coreprotect(user)


@pytest.mark.unit
@pytest.mark.django_db
class TestCoreProtectCityView:
    @patch(
        "minecraft.services.coreprotect_ops.rcon_client.run_command",
        return_value="ok",
    )
    def test_apply_rollback(self, mock_run):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        user = _add_perm(user, "manage_coreprotect")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "coreprotect",
                "action": "apply",
                "co_user": "mccpc01",
                "co_time_preset": "30m",
                "co_radius": "#global",
                "co_action": "rollback",
                "co_blocks_only": "on",
            },
        )
        assert response.status_code == 200
        assert mock_run.called
        assert mock_run.call_args[0][0].startswith("co rollback u:mccpc01 t:30m r:#global")

    def test_denied_without_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "coreprotect",
                "action": "apply",
                "co_user": "mccpc01",
                "co_time_preset": "15m",
                "co_radius": "#global",
                "co_action": "rollback",
            },
        )
        assert response.status_code == 302
