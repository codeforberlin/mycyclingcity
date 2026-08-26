# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from api.models import Group, GroupType, GroupVeloTransfer
from api.services.velo_consolidate import (
    ConsolidateError,
    consolidate_spendable,
    consolidate_top_leaves_to_top,
)

User = get_user_model()


@pytest.mark.django_db
def test_consolidate_spendable_moves_only_spendable():
    gtype, _ = GroupType.objects.get_or_create(name="ConsType")
    top = Group.objects.create(name="EventTOP", group_type=gtype, velos_total=1000, velos_spendable=5)
    leaf_a = Group.objects.create(
        name="Speiche", group_type=gtype, parent=top, velos_total=400, velos_spendable=40
    )
    leaf_b = Group.objects.create(
        name="Kurbel", group_type=gtype, parent=top, velos_total=300, velos_spendable=25
    )
    user = User.objects.create_user(username="cons-op", password="x", is_staff=True)

    result = consolidate_spendable(
        source_ids=[leaf_a.pk, leaf_b.pk],
        target_id=top.pk,
        reason="FEZitty Abschluss",
        user=user,
    )
    assert result["ok"] is True
    assert result["transferred"] == 65

    leaf_a.refresh_from_db()
    leaf_b.refresh_from_db()
    top.refresh_from_db()
    assert leaf_a.velos_spendable == 0
    assert leaf_b.velos_spendable == 0
    assert top.velos_spendable == 70  # 5 + 65
    assert leaf_a.velos_total == 400
    assert leaf_b.velos_total == 300
    assert top.velos_total == 1000
    assert GroupVeloTransfer.objects.filter(batch_id=result["batch_id"]).count() == 2


@pytest.mark.django_db
def test_consolidate_top_leaves_shortcut():
    gtype, _ = GroupType.objects.get_or_create(name="ConsType2")
    top = Group.objects.create(name="TOP2", group_type=gtype, velos_spendable=0)
    Group.objects.create(name="L1", group_type=gtype, parent=top, velos_spendable=10)
    Group.objects.create(name="L2", group_type=gtype, parent=top, velos_spendable=15)
    result = consolidate_top_leaves_to_top(top_id=top.pk, reason="Event Ende")
    assert result["transferred"] == 25
    top.refresh_from_db()
    assert top.velos_spendable == 25


@pytest.mark.django_db
def test_zero_spendable():
    gtype, _ = GroupType.objects.get_or_create(name="ConsType3")
    leaf = Group.objects.create(name="ResetMe", group_type=gtype, velos_total=50, velos_spendable=12)
    result = consolidate_spendable(
        source_ids=[leaf.pk],
        target_id=None,
        reason="Jahresabschluss",
        action=GroupVeloTransfer.ACTION_ZERO,
    )
    leaf.refresh_from_db()
    assert leaf.velos_spendable == 0
    assert leaf.velos_total == 50
    assert result["transferred"] == 12


@pytest.mark.django_db
def test_consolidate_rejects_target_in_sources():
    gtype, _ = GroupType.objects.get_or_create(name="ConsType4")
    g = Group.objects.create(name="Self", group_type=gtype, velos_spendable=9)
    with pytest.raises(ConsolidateError):
        consolidate_spendable(source_ids=[g.pk], target_id=g.pk, reason="x")


@pytest.mark.django_db
def test_admin_consolidate_page_requires_perm():
    user = User.objects.create_user(username="noperm", password="x", is_staff=True)
    client = Client()
    client.force_login(user)
    resp = client.get(reverse("admin:api_group_velo_consolidate"))
    assert resp.status_code == 403
    perm = Permission.objects.get(
        codename="transfer_group_velos", content_type__app_label="api"
    )
    user.user_permissions.add(perm)
    user = User.objects.get(pk=user.pk)
    client.force_login(user)
    resp = client.get(reverse("admin:api_group_velo_consolidate"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_operator_sees_only_managed_top_groups():
    gtype, _ = GroupType.objects.get_or_create(name="ScopeType")
    own = Group.objects.create(name="FEZitty", group_type=gtype, parent=None, is_visible=True)
    other = Group.objects.create(name="OtherTOP", group_type=gtype, parent=None, is_visible=True)
    Group.objects.create(name="OwnLeaf", group_type=gtype, parent=own, is_visible=True, velos_spendable=3)
    Group.objects.create(name="OtherLeaf", group_type=gtype, parent=other, is_visible=True, velos_spendable=7)

    op = User.objects.create_user(username="fez-op", password="x", is_staff=True)
    perm = Permission.objects.get(
        codename="transfer_group_velos", content_type__app_label="api"
    )
    op.user_permissions.add(perm)
    own.managers.add(op)

    client = Client()
    client.force_login(op)
    resp = client.get(reverse("admin:api_group_velo_consolidate"))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "FEZitty" in body
    assert "OwnLeaf" in body
    assert "OtherTOP" not in body
    assert "OtherLeaf" not in body


@pytest.mark.django_db
def test_operator_post_rejects_foreign_group():
    gtype, _ = GroupType.objects.get_or_create(name="ScopeType2")
    own = Group.objects.create(name="OwnTOP", group_type=gtype, parent=None, is_visible=True)
    foreign = Group.objects.create(
        name="ForeignLeaf", group_type=gtype, parent=None, is_visible=True, velos_spendable=20
    )
    op = User.objects.create_user(username="fez-op2", password="x", is_staff=True)
    perm = Permission.objects.get(
        codename="transfer_group_velos", content_type__app_label="api"
    )
    op.user_permissions.add(perm)
    own.managers.add(op)

    client = Client()
    client.force_login(op)
    resp = client.post(
        reverse("admin:api_group_velo_consolidate"),
        {
            "action": "zero",
            "source_ids": [str(foreign.pk)],
            "reason": "sollte scheitern",
        },
    )
    assert resp.status_code == 302
    foreign.refresh_from_db()
    assert foreign.velos_spendable == 20


@pytest.mark.django_db
def test_operator_can_preview_hidden_leaf_under_managed_top():
    """Invisible leaves still appear in wallet candidates and must be in scope."""
    gtype, _ = GroupType.objects.get_or_create(name="ScopeHidden")
    own = Group.objects.create(name="FEZOwn", group_type=gtype, parent=None, is_visible=True)
    hidden = Group.objects.create(
        name="HiddenLeaf",
        group_type=gtype,
        parent=own,
        is_visible=False,
        velos_spendable=50,
    )
    op = User.objects.create_user(username="fez-hid", password="x", is_staff=True)
    perm = Permission.objects.get(
        codename="transfer_group_velos", content_type__app_label="api"
    )
    op.user_permissions.add(perm)
    own.managers.add(op)

    client = Client()
    client.force_login(op)
    resp = client.post(
        reverse("admin:api_group_velo_consolidate"),
        {
            "action": "consolidate",
            "source_ids": [str(hidden.pk)],
            "target_id": str(own.pk),
            "reason": "Event Reset",
        },
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "group_out_of_scope" not in body
    assert "Vorschau" in body or "HiddenLeaf" in body


@pytest.mark.django_db
def test_superuser_sees_all_top_groups():
    gtype, _ = GroupType.objects.get_or_create(name="ScopeType3")
    Group.objects.create(name="AlphaSU", group_type=gtype, parent=None, is_visible=True)
    Group.objects.create(name="BetaSU", group_type=gtype, parent=None, is_visible=True)
    su = User.objects.create_superuser(username="su-cons", password="x", email="su@ex.com")
    client = Client()
    client.force_login(su)
    resp = client.get(reverse("admin:api_group_velo_consolidate"))
    body = resp.content.decode("utf-8")
    assert "AlphaSU" in body
    assert "BetaSU" in body
