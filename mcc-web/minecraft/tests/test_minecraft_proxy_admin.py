# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import MinecraftIntegrationConfig
from minecraft.services.preset_permissions import user_can_manage_minecraft_proxy


def _add_perm(user, model, codename: str):
    ct = ContentType.objects.get_for_model(model)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    user.user_permissions.add(perm)
    user = type(user).objects.get(pk=user.pk)
    return user


@pytest.mark.unit
@pytest.mark.django_db
class TestManageMinecraftProxyPermission:
    def test_superuser(self, django_user_model):
        user = UserFactory(is_staff=True, is_superuser=True)
        assert user_can_manage_minecraft_proxy(user)

    def test_explicit_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, MinecraftIntegrationConfig, "manage_minecraft_proxy")
        assert user_can_manage_minecraft_proxy(user)

    def test_control_perm_alone_not_enough(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")
        assert not user_can_manage_minecraft_proxy(user)


@pytest.mark.unit
@pytest.mark.django_db
class TestProxyAdminActions:
    @pytest.fixture
    def proxy_manager(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")
        user = _add_perm(user, MinecraftIntegrationConfig, "manage_minecraft_proxy")
        return user

    def test_velocity_status_uses_proxy_script(self, proxy_manager):
        client = Client()
        client.force_login(proxy_manager)
        with (
            patch("minecraft.admin_views._get_proxy_script_path") as mock_path,
            patch("minecraft.admin_views.subprocess.run") as mock_run,
            patch("minecraft.admin_views.os.access", return_value=True),
        ):
            script = Path("/tmp/minecraft_proxy.sh")
            mock_path.return_value = script
            with patch.object(Path, "exists", return_value=True):
                mock_run.return_value = MagicMock(returncode=1, stdout="Velocity stopped\n", stderr="")
                url = reverse("admin:minecraft_action", kwargs={"action": "velocity-status"})
                response = client.post(url)

        assert response.status_code in (200, 500)
        assert mock_run.called
        args, kwargs = mock_run.call_args
        assert args[0][1] == "velocity-status"
        assert "MCC_MINECRAFT_VELOCITY_DIR" in (kwargs.get("env") or {})

    def test_paper_status_uses_paper_script(self, proxy_manager):
        client = Client()
        client.force_login(proxy_manager)
        with (
            patch("minecraft.admin_views._get_paper_script_path") as mock_path,
            patch("minecraft.admin_views.subprocess.run") as mock_run,
            patch("minecraft.admin_views.os.access", return_value=True),
        ):
            script = Path("/tmp/minecraft_paper.sh")
            mock_path.return_value = script
            with patch.object(Path, "exists", return_value=True):
                mock_run.return_value = MagicMock(returncode=1, stdout="Paper stopped\n", stderr="")
                url = reverse("admin:minecraft_action", kwargs={"action": "paper-status"})
                response = client.post(url)

        assert response.status_code in (200, 500)
        assert mock_run.called
        args, kwargs = mock_run.call_args
        assert args[0][1] == "status"
        env = kwargs.get("env") or {}
        assert "MCC_MINECRAFT_PAPER_DIR" in env
        assert "MCC_MINECRAFT_RCON_PASSWORD" in env

    def test_proxy_action_denied_without_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")
        client = Client()
        client.force_login(user)
        url = reverse("admin:minecraft_action", kwargs={"action": "velocity-start"})
        response = client.post(url)
        assert response.status_code == 403

    def test_paper_action_denied_without_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, MinecraftIntegrationConfig, "access_minecraft_control")
        client = Client()
        client.force_login(user)
        url = reverse("admin:minecraft_action", kwargs={"action": "paper-start"})
        response = client.post(url)
        assert response.status_code == 403

    @patch("minecraft.services.velocity_rcon.check_connection", return_value=(True, "", "auth"))
    @patch("minecraft.admin_views.check_connection", return_value=(True, "", "auth"))
    def test_control_page_shows_velocity_rcon(self, _paper_rcon, _vel_rcon, proxy_manager):
        client = Client()
        client.force_login(proxy_manager)
        with (
            patch("minecraft.admin_views._get_worker_status", return_value={"running": False}),
            patch("minecraft.admin_views._get_snapshot_status", return_value={"running": False}),
            patch("minecraft.admin_views._get_session_status", return_value={"running": False}),
            patch("minecraft.admin_views._get_arena_status", return_value={"running": False}),
            patch("minecraft.admin_views._get_ws_status", return_value={"running": False}),
            patch(
                "minecraft.admin_views._get_velocity_status",
                return_value={"running": True, "output": "Velocity running"},
            ),
            patch("minecraft.admin_views._get_limbo_status", return_value={"running": False}),
            patch("minecraft.admin_views._get_paper_status", return_value={"running": False}),
        ):
            response = client.get(reverse("admin:minecraft_control"))
        assert response.status_code == 200
        assert response.context["velocity_rcon_ok"] is True
        content = response.content.decode()
        assert "Proxy-RCON" in content
        assert "Velocircon" in content
        assert "Verbunden" in content


@pytest.mark.unit
class TestVelocityRconCheck:
    @patch("minecraft.services.velocity_rcon.send_velocity_command", return_value="ok")
    def test_check_connection_ok(self, mock_cmd):
        from minecraft.services.velocity_rcon import check_connection

        ok, err, mode = check_connection()
        assert ok is True
        assert err == ""
        assert mode == "auth"
        mock_cmd.assert_called_once_with("glist")

    @patch(
        "minecraft.services.velocity_rcon.send_velocity_command",
        side_effect=Exception("connection refused"),
    )
    def test_check_connection_fail(self, _mock_cmd):
        from minecraft.services.velocity_rcon import check_connection

        ok, err, mode = check_connection()
        assert ok is False
        assert "connection refused" in err
        assert mode == "auth"
