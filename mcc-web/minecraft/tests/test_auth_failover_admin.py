# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from minecraft.models import MinecraftIntegrationConfig


User = get_user_model()


def _add_perm(user, model, codename):
    ct = ContentType.objects.get_for_model(model)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    user.user_permissions.add(perm)
    return user


@pytest.mark.django_db
class TestAuthFailoverAdmin:
    @pytest.fixture
    def operator(self, db):
        user = User.objects.create_user(
            username="failover_op",
            password="x",
            is_staff=True,
            is_active=True,
        )
        return _add_perm(user, MinecraftIntegrationConfig, "manage_auth_failover")

    def test_page_requires_permission(self, client, db):
        user = User.objects.create_user(
            username="no_failover",
            password="x",
            is_staff=True,
            is_active=True,
        )
        client.force_login(user)
        url = reverse("admin:minecraft_auth_failover")
        response = client.get(url)
        assert response.status_code in (302, 403)

    def test_page_ok_with_permission(self, client, operator):
        client.force_login(operator)
        url = reverse("admin:minecraft_auth_failover")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Auth-Failover" in response.content
        assert b"Legacy" in response.content

    def test_set_mode(self, client, operator):
        client.force_login(operator)
        url = reverse("admin:minecraft_auth_failover")
        response = client.post(
            url,
            {"action": "set_mode", "auth_ops_mode": "failover"},
        )
        assert response.status_code == 302
        config = MinecraftIntegrationConfig.get_config()
        assert config.auth_ops_mode == "failover"
