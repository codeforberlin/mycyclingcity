# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from api.models import Group, GroupType
from luanti.models import LuantiAccount
from luanti.services.permissions import (
    account_in_operator_session_scope,
    operator_session_top_ids,
)
from luanti.services.session_control import join_payload, privs_for_account, start_session


@pytest.fixture
def tops(db):
    gtype, _ = GroupType.objects.get_or_create(name="SessionTopType")
    a = Group.objects.create(name="TOP-A", parent=None, is_visible=True, group_type=gtype)
    b = Group.objects.create(name="TOP-B", parent=None, is_visible=True, group_type=gtype)
    return a, b


@pytest.mark.django_db
def test_privs_for_account_server_op_merges(db):
    acc = LuantiAccount.objects.create(login_name="Op1", id_tag="Op1", server_op=False)
    base = privs_for_account(acc, "play")
    assert "server" not in base
    assert "interact" in base
    acc.server_op = True
    acc.save(update_fields=["server_op"])
    op = privs_for_account(acc, "play")
    assert "server" in op
    assert "privs" in op
    assert "protection_bypass" in op
    assert "interact" in op


@pytest.mark.django_db
def test_join_payload_includes_server_op_privs(db):
    acc = LuantiAccount.objects.create(
        login_name="OpJoin", id_tag="OpJoin", server_op=True
    )
    start_session(account=acc, mode="play", duration=10)
    payload = join_payload(acc.login_name)
    assert payload["ok"] is True
    assert "server" in payload["privs"]
    assert "kick" in payload["privs"]


@pytest.mark.django_db
def test_operator_session_top_scope(tops):
    top_a, top_b = tops
    User = get_user_model()
    op = User.objects.create_user(username="lt_op", password="x", is_staff=True)
    perm = Permission.objects.get(codename="manage_luanti_sessions")
    op.user_permissions.add(perm)
    op.managed_groups.add(top_a)

    acc_a = LuantiAccount.objects.create(
        login_name="A1", id_tag="A1", assigned_to_group=top_a, is_active=True
    )
    acc_b = LuantiAccount.objects.create(
        login_name="B1", id_tag="B1", assigned_to_group=top_b, is_active=True
    )
    acc_none = LuantiAccount.objects.create(
        login_name="N1", id_tag="N1", assigned_to_group=None, is_active=True
    )

    assert operator_session_top_ids(op) == {top_a.pk}
    assert account_in_operator_session_scope(op, acc_a) is True
    assert account_in_operator_session_scope(op, acc_b) is False
    assert account_in_operator_session_scope(op, acc_none) is False

    superuser = User.objects.create_superuser(
        username="lt_su", password="x", email="su@example.com"
    )
    assert operator_session_top_ids(superuser) is None
    assert account_in_operator_session_scope(superuser, acc_none) is True
