# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from unittest.mock import patch

from minecraft.models import MinecraftIntegrationConfig, MinecraftRconPreset
from minecraft.services.preset_permissions import (
    user_can_access_minecraft_city,
    user_can_access_minecraft_control,
    user_can_access_minecraft_shop,
    user_can_delete_preset,
    user_can_edit_preset,
    user_can_manage_player_sessions,
    user_can_run_arena_sim,
    user_can_run_free_rcon,
    user_can_run_preset,
)


User = get_user_model()


def _add_perm(user, model, codename):
    content_type = ContentType.objects.get_for_model(model)
    perm = Permission.objects.get(content_type=content_type, codename=codename)
    user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    return user


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff",
        password="secret",
        is_staff=True,
    )


@pytest.fixture
def moderator_user(db, staff_user):
    return _add_perm(staff_user, MinecraftRconPreset, "run_rconpreset")


@pytest.mark.unit
@pytest.mark.django_db
class TestPresetPermissions:
    def test_moderator_can_run_world_preset(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="day",
            name="Tag",
            category=MinecraftRconPreset.CATEGORY_WORLD,
            commands=["time set day"],
        )
        assert user_can_run_preset(moderator_user, preset)

    def test_moderator_cannot_run_gamerule_without_flag(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="city",
            name="Stadt",
            category=MinecraftRconPreset.CATEGORY_GAMERULE,
            commands=["gamerule pvp false"],
        )
        assert not user_can_run_preset(moderator_user, preset)

    def test_moderator_can_run_flagged_gamerule(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="city",
            name="Stadt",
            category=MinecraftRconPreset.CATEGORY_GAMERULE,
            commands=["gamerule pvp false"],
            moderator_can_run=True,
        )
        assert user_can_run_preset(moderator_user, preset)

    def test_system_preset_delete_requires_special_perm(self, staff_user):
        preset = MinecraftRconPreset.objects.create(
            slug="sys",
            name="System",
            commands=["time set day"],
            is_system=True,
        )
        assert not user_can_delete_preset(staff_user, preset)

    def test_system_preset_edit_requires_special_perm(self, staff_user):
        preset = MinecraftRconPreset.objects.create(
            slug="sys",
            name="System",
            commands=["time set day"],
            is_system=True,
        )
        assert not user_can_edit_preset(staff_user, preset)


@pytest.mark.unit
@pytest.mark.django_db
class TestModuleAccessPermissions:
    def test_legacy_moderator_can_access_control_and_city(self, moderator_user):
        assert user_can_access_minecraft_control(moderator_user)
        assert user_can_access_minecraft_city(moderator_user)
        assert not user_can_access_minecraft_shop(moderator_user)
        assert not user_can_run_free_rcon(moderator_user)

    def test_explicit_control_perm(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "access_minecraft_control")
        assert user_can_access_minecraft_control(user)
        assert not user_can_access_minecraft_city(user)

    def test_explicit_city_perm(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "access_minecraft_city")
        assert user_can_access_minecraft_city(user)
        assert not user_can_access_minecraft_control(user)

    def test_explicit_shop_perm(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "access_minecraft_shop")
        assert user_can_access_minecraft_shop(user)
        assert not user_can_access_minecraft_control(user)

    def test_free_rcon_perm(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "run_free_rcon")
        assert user_can_run_free_rcon(user)

    def test_arena_sim_perm(self, staff_user, client):
        assert not user_can_run_arena_sim(staff_user)
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "run_arena_sim")
        assert user_can_run_arena_sim(user)
        client.force_login(user)
        response = client.get(reverse("admin:minecraft_arena_sim"))
        assert response.status_code == 200

    def test_player_sessions_perm_does_not_grant_arena_sim(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "manage_player_sessions")
        assert user_can_manage_player_sessions(user)
        assert not user_can_run_arena_sim(user)

    def test_superuser_has_all_access(self, db):
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )
        assert user_can_access_minecraft_control(user)
        assert user_can_access_minecraft_city(user)
        assert user_can_access_minecraft_shop(user)
        assert user_can_run_free_rcon(user)

    def test_inactive_staff_denied(self, staff_user):
        user = _add_perm(staff_user, MinecraftIntegrationConfig, "access_minecraft_control")
        user.is_active = False
        user.save()
        assert not user_can_access_minecraft_control(user)


@pytest.mark.django_db
class TestFreeRconView:
    @pytest.fixture
    def operator(self, db):
        user = User.objects.create_user(
            username="operator",
            password="secret",
            is_staff=True,
        )
        user = _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")
        return _add_perm(user, MinecraftIntegrationConfig, "run_free_rcon")

    @pytest.fixture
    def control_only(self, db):
        user = User.objects.create_user(
            username="control",
            password="secret",
            is_staff=True,
        )
        return _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")

    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    @patch("minecraft.admin_views.run_command", return_value="There are 0 of a max of 20 players online")
    def test_free_rcon_success(self, mock_run, _mock_check, client, operator):
        client.force_login(operator)
        url = reverse("admin:minecraft_control")
        response = client.post(
            url,
            {"form_type": "free_rcon", "rcon_command": "  list  "},
        )
        assert response.status_code == 302
        mock_run.assert_called_once_with("list")

    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    @patch("minecraft.admin_views.run_command")
    def test_free_rcon_empty_rejected(self, mock_run, _mock_check, client, operator):
        client.force_login(operator)
        url = reverse("admin:minecraft_control")
        response = client.post(
            url,
            {"form_type": "free_rcon", "rcon_command": "   "},
        )
        assert response.status_code == 302
        mock_run.assert_not_called()

    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    @patch("minecraft.admin_views.run_command")
    def test_free_rcon_denied_without_perm(self, mock_run, _mock_check, client, control_only):
        client.force_login(control_only)
        url = reverse("admin:minecraft_control")
        response = client.post(
            url,
            {"form_type": "free_rcon", "rcon_command": "list"},
        )
        assert response.status_code == 302
        mock_run.assert_not_called()

    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    def test_city_page_denied_without_perm(self, _mock_check, client, control_only):
        client.force_login(control_only)
        url = reverse("admin:minecraft_city")
        response = client.get(url)
        assert response.status_code == 302

    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    def test_shop_ops_denied_without_perm(self, _mock_check, client, control_only):
        client.force_login(control_only)
        url = reverse("admin:minecraft_shop_ops")
        response = client.get(url)
        assert response.status_code == 302
