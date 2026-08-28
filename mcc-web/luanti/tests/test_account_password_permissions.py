# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from luanti.models import LuantiAccount
from luanti.services.permissions import (
    user_can_set_luanti_account_password,
    user_can_view_luanti_account_password,
)


@pytest.fixture
def account_with_password(db):
    return LuantiAccount.objects.create(
        login_name="pw_test",
        id_tag="pw_test",
        login_password="Secret99",
    )


@pytest.fixture
def operator_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="lt_acc_op", password="x", is_staff=True)
    perm = Permission.objects.get(codename="manage_luanti_accounts")
    user.user_permissions.add(perm)
    return user


@pytest.fixture
def superuser(db):
    User = get_user_model()
    return User.objects.create_superuser(
        username="lt_acc_su",
        password="x",
        email="su@example.com",
    )


@pytest.mark.django_db
def test_password_permission_helpers(operator_user, superuser):
    assert user_can_view_luanti_account_password(operator_user) is False
    assert user_can_set_luanti_account_password(operator_user) is False
    assert user_can_view_luanti_account_password(superuser) is True
    assert user_can_set_luanti_account_password(superuser) is True


@pytest.mark.django_db
def test_accounts_page_masks_password_for_operator(client, operator_user, account_with_password):
    client.force_login(operator_user)
    url = reverse("admin:luanti_accounts")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret99" not in content
    assert "********" in content
    assert "Passwort neu setzen" not in content


@pytest.mark.django_db
def test_accounts_page_shows_password_for_superuser(client, superuser, account_with_password):
    client.force_login(superuser)
    url = reverse("admin:luanti_accounts")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret99" in content
    assert "Passwort neu setzen" in content


@pytest.mark.django_db
def test_operator_reset_password_rejected(client, operator_user, account_with_password):
    client.force_login(operator_user)
    url = reverse("admin:luanti_accounts")
    response = client.post(
        url,
        {
            "action": "reset_password",
            "account_id": account_with_password.pk,
            "login_password": "NewPass1",
        },
    )
    assert response.status_code == 302
    account_with_password.refresh_from_db()
    assert account_with_password.login_password == "Secret99"


@pytest.mark.django_db
def test_operator_create_account_auto_password(client, operator_user):
    client.force_login(operator_user)
    url = reverse("admin:luanti_accounts")
    response = client.post(
        url,
        {
            "action": "create",
            "login_name": "auto_pw_user",
            "id_tag": "auto_pw_user",
            "login_password": "IgnoredByOp",
            "is_active": "1",
        },
    )
    assert response.status_code == 302
    account = LuantiAccount.objects.get(login_name="auto_pw_user")
    assert account.login_password
    assert account.login_password != "IgnoredByOp"
