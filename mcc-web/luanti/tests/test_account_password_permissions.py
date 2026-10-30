# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import LuantiAccount
from luanti.services.permissions import (
    user_can_set_luanti_account_password,
    user_can_set_luanti_account_password_for,
    user_can_view_luanti_account_password,
    user_can_view_luanti_account_password_for,
)


@pytest.fixture
def account_with_password(db):
    return LuantiAccount.objects.create(
        login_name="pw_test",
        id_tag="pw_test",
        login_password="Secret99",
    )


@pytest.fixture
def tops(db):
    gtype, _ = GroupType.objects.get_or_create(name="LuantiPwTopType")
    a = Group.objects.create(name="TOP-PW-A", parent=None, is_visible=True, group_type=gtype)
    b = Group.objects.create(name="TOP-PW-B", parent=None, is_visible=True, group_type=gtype)
    return a, b


@pytest.fixture
def operator_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="lt_acc_op", password="x", is_staff=True)
    perm = Permission.objects.get(
        codename="manage_luanti_accounts", content_type__app_label="luanti"
    )
    user.user_permissions.add(perm)
    return user


@pytest.fixture
def luanti_admin_operator(db, tops):
    top_a, _ = tops
    User = get_user_model()
    user = User.objects.create_user(username="lt_luanti_admin", password="x", is_staff=True)
    for codename in (
        "manage_luanti_accounts",
        "view_luanti_login_password",
        "set_luanti_login_password",
    ):
        perm = Permission.objects.get(codename=codename, content_type__app_label="luanti")
        user.user_permissions.add(perm)
    user.managed_groups.add(top_a)
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
def test_password_permission_helpers(operator_user, superuser, luanti_admin_operator):
    assert user_can_view_luanti_account_password(operator_user) is False
    assert user_can_set_luanti_account_password(operator_user) is False
    assert user_can_view_luanti_account_password(superuser) is True
    assert user_can_set_luanti_account_password(superuser) is True
    assert user_can_view_luanti_account_password(luanti_admin_operator) is True
    assert user_can_set_luanti_account_password(luanti_admin_operator) is True


@pytest.mark.django_db
def test_accounts_list_masks_password_for_operator(client, operator_user, account_with_password):
    client.force_login(operator_user)
    url = reverse("admin:luanti_accounts")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret99" not in content
    assert "Passwort neu setzen" not in content
    assert 'class="info pw-reveal-btn"' not in content


@pytest.mark.django_db
def test_accounts_list_no_password_ui(client, superuser, account_with_password):
    client.force_login(superuser)
    url = reverse("admin:luanti_accounts")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret99" not in content
    assert "Passwort neu setzen" not in content
    assert 'class="info pw-reveal-btn"' not in content
    assert "Bearbeiten" in content


@pytest.mark.django_db
def test_account_detail_password_ui_for_superuser(client, superuser, account_with_password):
    client.force_login(superuser)
    url = reverse("admin:luanti_account_detail", args=[account_with_password.pk])
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Secret99" not in content
    assert "********" in content
    assert "Anzeigen" in content
    assert "Passwort neu setzen" in content


@pytest.mark.django_db
def test_superuser_reveal_password_endpoint(client, superuser, account_with_password):
    client.force_login(superuser)
    url = reverse(
        "admin:luanti_account_reveal_password",
        args=[account_with_password.pk],
    )
    response = client.post(url)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "password": "Secret99"}


@pytest.mark.django_db
def test_operator_reveal_password_forbidden(client, operator_user, account_with_password):
    client.force_login(operator_user)
    url = reverse(
        "admin:luanti_account_reveal_password",
        args=[account_with_password.pk],
    )
    response = client.post(url)
    assert response.status_code == 302


@pytest.mark.django_db
def test_luanti_admin_reveal_scoped(client, luanti_admin_operator, tops):
    top_a, top_b = tops
    acc_a = LuantiAccount.objects.create(
        login_name="scoped_a",
        id_tag="scoped_a",
        login_password="PassA123",
        assigned_to_group=top_a,
    )
    acc_b = LuantiAccount.objects.create(
        login_name="scoped_b",
        id_tag="scoped_b",
        login_password="PassB123",
        assigned_to_group=top_b,
    )
    client.force_login(luanti_admin_operator)
    url_a = reverse("admin:luanti_account_reveal_password", args=[acc_a.pk])
    url_b = reverse("admin:luanti_account_reveal_password", args=[acc_b.pk])
    assert client.post(url_a).json() == {"ok": True, "password": "PassA123"}
    assert client.post(url_b).status_code == 403


@pytest.mark.django_db
def test_luanti_admin_reset_scoped(client, luanti_admin_operator, tops):
    top_a, top_b = tops
    acc_a = LuantiAccount.objects.create(
        login_name="reset_a",
        id_tag="reset_a",
        login_password="OldA",
        assigned_to_group=top_a,
    )
    acc_b = LuantiAccount.objects.create(
        login_name="reset_b",
        id_tag="reset_b",
        login_password="OldB",
        assigned_to_group=top_b,
    )
    client.force_login(luanti_admin_operator)
    url = reverse("admin:luanti_accounts")
    client.post(
        url,
        {
            "action": "reset_password",
            "account_id": acc_a.pk,
            "login_password": "NewA99",
        },
    )
    acc_a.refresh_from_db()
    assert acc_a.login_password == "NewA99"
    client.post(
        url,
        {
            "action": "reset_password",
            "account_id": acc_b.pk,
            "login_password": "HackB",
        },
    )
    acc_b.refresh_from_db()
    assert acc_b.login_password == "OldB"


@pytest.mark.django_db
def test_luanti_admin_set_wallet_idor(client, luanti_admin_operator, tops):
    top_a, top_b = tops
    acc_b = LuantiAccount.objects.create(
        login_name="wallet_b",
        id_tag="wallet_b",
        assigned_to_group=top_b,
    )
    client.force_login(luanti_admin_operator)
    url = reverse("admin:luanti_accounts")
    response = client.post(
        url,
        {
            "action": "set_wallet",
            "account_id": acc_b.pk,
            "assigned_to_group": str(top_b.pk),
        },
    )
    assert response.status_code == 404


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
    assert response.status_code == 404
    account_with_password.refresh_from_db()
    assert account_with_password.login_password == "Secret99"


@pytest.mark.django_db
def test_operator_create_account_auto_password(client, operator_user, tops):
    top_a, _ = tops
    operator_user.managed_groups.add(top_a)
    client.force_login(operator_user)
    url = reverse("admin:luanti_accounts")
    response = client.post(
        url,
        {
            "action": "create",
            "login_name": "auto_pw_user",
            "id_tag": "auto_pw_user",
            "login_password": "IgnoredByOp",
            "assigned_to_group": str(top_a.pk),
            "is_active": "1",
        },
    )
    assert response.status_code == 302
    account = LuantiAccount.objects.get(login_name="auto_pw_user")
    assert account.login_password
    assert account.login_password != "IgnoredByOp"


@pytest.mark.django_db
def test_luanti_admin_create_requires_home(client, luanti_admin_operator):
    client.force_login(luanti_admin_operator)
    url = reverse("admin:luanti_accounts")
    client.post(
        url,
        {
            "action": "create",
            "login_name": "no_home",
            "id_tag": "no_home",
            "is_active": "1",
        },
    )
    assert not LuantiAccount.objects.filter(login_name="no_home").exists()


@pytest.mark.django_db
def test_scoped_helpers(tops, luanti_admin_operator):
    top_a, top_b = tops
    acc_a = LuantiAccount.objects.create(
        login_name="h_a", id_tag="h_a", assigned_to_group=top_a
    )
    acc_b = LuantiAccount.objects.create(
        login_name="h_b", id_tag="h_b", assigned_to_group=top_b
    )
    assert user_can_view_luanti_account_password_for(luanti_admin_operator, acc_a)
    assert user_can_set_luanti_account_password_for(luanti_admin_operator, acc_a)
    assert not user_can_view_luanti_account_password_for(luanti_admin_operator, acc_b)
    assert not user_can_set_luanti_account_password_for(luanti_admin_operator, acc_b)
