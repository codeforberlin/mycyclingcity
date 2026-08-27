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
def test_consolidate_partial_amount():
    gtype, _ = GroupType.objects.get_or_create(name="ConsPartial")
    top = Group.objects.create(name="PoolTOP", group_type=gtype, velos_spendable=100)
    leaf = Group.objects.create(name="Klasse2b", group_type=gtype, parent=top, velos_spendable=5)

    result = consolidate_spendable(
        source_ids=[top.pk],
        target_id=leaf.pk,
        reason="Rückgabe an Klasse 2b",
        amount=40,
    )
    assert result["transferred"] == 40
    assert result["partial"] is True
    top.refresh_from_db()
    leaf.refresh_from_db()
    assert top.velos_spendable == 60
    assert leaf.velos_spendable == 45


@pytest.mark.django_db
def test_consolidate_partial_rejects_multi_source():
    gtype, _ = GroupType.objects.get_or_create(name="ConsPartial2")
    top = Group.objects.create(name="T", group_type=gtype, velos_spendable=50)
    a = Group.objects.create(name="A", group_type=gtype, parent=top, velos_spendable=10)
    b = Group.objects.create(name="B", group_type=gtype, parent=top, velos_spendable=10)
    with pytest.raises(ConsolidateError) as exc:
        consolidate_spendable(
            source_ids=[a.pk, b.pk],
            target_id=top.pk,
            reason="x",
            amount=5,
        )
    assert exc.value.code == "partial_requires_single_source"


@pytest.mark.django_db
def test_consolidate_partial_rejects_over_available():
    gtype, _ = GroupType.objects.get_or_create(name="ConsPartial3")
    src = Group.objects.create(name="Src", group_type=gtype, velos_spendable=10)
    dst = Group.objects.create(name="Dst", group_type=gtype, velos_spendable=0)
    with pytest.raises(ConsolidateError) as exc:
        consolidate_spendable(
            source_ids=[src.pk],
            target_id=dst.pk,
            reason="x",
            amount=11,
        )
    assert exc.value.code == "amount_exceeds_spendable"


@pytest.mark.django_db
def test_year_end_snapshot_stores_spendable():
    from decimal import Decimal

    from django.utils import timezone

    from api.models import YearEndSnapshot, YearEndSnapshotDetail

    gtype, _ = GroupType.objects.get_or_create(name="YESpend")
    top = Group.objects.create(
        name="SchoolYE",
        group_type=gtype,
        velos_total=500,
        velos_spendable=80,
        distance_total=Decimal("12.5"),
    )
    leaf = Group.objects.create(
        name="2b",
        group_type=gtype,
        parent=top,
        velos_total=200,
        velos_spendable=35,
        distance_total=Decimal("4.0"),
    )
    now = timezone.now()
    snapshot = YearEndSnapshot.objects.create(
        group=top,
        snapshot_date=now,
        period_start_date=now,
        period_end_date=now,
        period_type="school_year",
        group_total_km=top.distance_total,
        group_total_velos=top.velos_total,
        group_total_spendable=int(top.velos_spendable or 0),
    )
    YearEndSnapshotDetail.objects.create(
        snapshot=snapshot,
        group=top,
        distance_total=top.distance_total,
        velos_total=top.velos_total,
        velos_spendable=int(top.velos_spendable or 0),
    )
    YearEndSnapshotDetail.objects.create(
        snapshot=snapshot,
        group=leaf,
        distance_total=leaf.distance_total,
        velos_total=leaf.velos_total,
        velos_spendable=int(leaf.velos_spendable or 0),
    )
    assert snapshot.group_total_spendable == 80
    assert snapshot.details.get(group=leaf).velos_spendable == 35
    assert snapshot.details.get(group=top).velos_spendable == 80


@pytest.mark.django_db
def test_admin_partial_transfer_confirm_flow():
    gtype, _ = GroupType.objects.get_or_create(name="ConsGUIPartial")
    top = Group.objects.create(name="GUITop", group_type=gtype, parent=None, velos_spendable=90)
    leaf = Group.objects.create(
        name="GUILeaf", group_type=gtype, parent=top, velos_spendable=1
    )
    su = User.objects.create_superuser(username="su-part", password="x", email="p@ex.com")
    client = Client()
    client.force_login(su)
    url = reverse("admin:api_group_velo_consolidate")
    preview = client.post(
        url,
        {
            "action": "consolidate",
            "source_ids": [str(top.pk)],
            "target_id": str(leaf.pk),
            "amount": "25",
            "reason": "Neujahr Anteil 2b",
        },
    )
    assert preview.status_code == 200
    body = preview.content.decode("utf-8")
    assert "Teilumbuchung" in body or "25" in body

    confirm = client.post(
        url,
        {
            "action": "consolidate",
            "confirm": "1",
            "source_ids": [str(top.pk)],
            "target_id": str(leaf.pk),
            "amount": "25",
            "reason": "Neujahr Anteil 2b",
        },
    )
    assert confirm.status_code == 302
    top.refresh_from_db()
    leaf.refresh_from_db()
    assert top.velos_spendable == 65
    assert leaf.velos_spendable == 26
