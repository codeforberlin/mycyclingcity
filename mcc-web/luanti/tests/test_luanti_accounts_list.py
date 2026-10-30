# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import LuantiAccount


@pytest.fixture
def tops(db):
    gtype, _ = GroupType.objects.get_or_create(name="LuantiListTopType")
    a = Group.objects.create(name="TOP-LIST-A", parent=None, is_visible=True, group_type=gtype)
    b = Group.objects.create(name="TOP-LIST-B", parent=None, is_visible=True, group_type=gtype)
    return a, b


@pytest.fixture
def scoped_operator(db, tops):
    top_a, _ = tops
    User = get_user_model()
    user = User.objects.create_user(username="lt_list_op", password="x", is_staff=True)
    perm = Permission.objects.get(
        codename="manage_luanti_accounts", content_type__app_label="luanti"
    )
    user.user_permissions.add(perm)
    user.managed_groups.add(top_a)
    return user, top_a


@pytest.mark.django_db
def test_list_filter_by_top(client, scoped_operator, tops):
    user, top_a = scoped_operator
    top_b = tops[1]
    LuantiAccount.objects.create(
        login_name="list_a", id_tag="list_a", assigned_to_group=top_a
    )
    LuantiAccount.objects.create(
        login_name="list_b", id_tag="list_b", assigned_to_group=top_b
    )
    client.force_login(user)
    url = reverse("admin:luanti_accounts")
    response = client.get(url, {"top": top_a.pk})
    content = response.content.decode()
    assert response.status_code == 200
    assert "list_a" in content
    assert "list_b" not in content


@pytest.mark.django_db
def test_list_search_q(client, scoped_operator, tops):
    user, top_a = scoped_operator
    LuantiAccount.objects.create(
        login_name="findme", id_tag="rfid_x", assigned_to_group=top_a
    )
    LuantiAccount.objects.create(
        login_name="other", id_tag="other", assigned_to_group=top_a
    )
    client.force_login(user)
    url = reverse("admin:luanti_accounts")
    response = client.get(url, {"q": "findme"})
    content = response.content.decode()
    assert "findme" in content
    assert "other" not in content or response.context["search_q"] == "findme"


@pytest.mark.django_db
def test_detail_foreign_top_404(client, scoped_operator, tops):
    user, _top_a = scoped_operator
    top_b = tops[1]
    acc = LuantiAccount.objects.create(
        login_name="foreign", id_tag="foreign", assigned_to_group=top_b
    )
    client.force_login(user)
    url = reverse("admin:luanti_account_detail", args=[acc.pk])
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_set_wallet_on_detail_idor(client, scoped_operator, tops):
    user, _top_a = scoped_operator
    top_b = tops[1]
    acc = LuantiAccount.objects.create(
        login_name="wallet_idor", id_tag="wallet_idor", assigned_to_group=top_b
    )
    client.force_login(user)
    url = reverse("admin:luanti_account_detail", args=[acc.pk])
    assert client.post(url, {"action": "set_wallet", "assigned_to_group": str(top_b.pk)}).status_code == 404


@pytest.mark.django_db
def test_pagination(client, scoped_operator, tops):
    user, top_a = scoped_operator
    for i in range(30):
        LuantiAccount.objects.create(
            login_name=f"pag_{i:02d}",
            id_tag=f"pag_{i:02d}",
            assigned_to_group=top_a,
        )
    client.force_login(user)
    url = reverse("admin:luanti_accounts")
    page1 = client.get(url, {"top": top_a.pk})
    assert page1.status_code == 200
    assert page1.context["page_obj"].paginator.num_pages == 2
    page2 = client.get(url, {"top": top_a.pk, "page": "2"})
    assert page2.status_code == 200
    assert page2.context["page_obj"].number == 2
