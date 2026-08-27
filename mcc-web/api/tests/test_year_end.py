# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from api.models import Cyclist, Group, GroupType, YearEndSnapshot
from api.services.year_end import collect_year_end_preview, execute_year_end_snapshot

User = get_user_model()


@pytest.fixture
def year_end_tree(db):
    gtype, _ = GroupType.objects.get_or_create(name="YEPreviewType")
    top = Group.objects.create(
        name="YE School",
        group_type=gtype,
        velos_total=500,
        velos_spendable=80,
        distance_total=Decimal("12.50000"),
    )
    leaf = Group.objects.create(
        name="YE 2b",
        group_type=gtype,
        parent=top,
        velos_total=200,
        velos_spendable=35,
        distance_total=Decimal("4.00000"),
    )
    cyclist = Cyclist.objects.create(
        user_id="YE-RADLER-1",
        id_tag="ye-rfid-preview-1",
        distance_total=Decimal("1.25000"),
        velos_balance=40,
    )
    cyclist.groups.add(leaf)
    return top, leaf, cyclist


@pytest.mark.django_db
def test_collect_year_end_preview_lists_groups_and_cyclists(year_end_tree):
    top, leaf, cyclist = year_end_tree
    preview = collect_year_end_preview(top)
    assert preview["counts"]["groups"] == 2
    assert preview["counts"]["cyclists"] == 1
    assert preview["totals"]["group_spendable"] == 80
    names = {r["name"] for r in preview["groups"]}
    assert names == {"YE School", "YE 2b"}
    assert preview["cyclists"][0]["user_id"] == "YE-RADLER-1"
    assert preview["cyclists"][0]["velos_balance"] == 40
    leaf_row = next(r for r in preview["groups"] if r["id"] == leaf.pk)
    assert leaf_row["velos_spendable"] == 35


@pytest.mark.django_db
def test_execute_year_end_resets_totals_keeps_spendable(year_end_tree):
    top, leaf, cyclist = year_end_tree
    now = timezone.now()
    snap = execute_year_end_snapshot(
        top_group=top,
        snapshot_date=now,
        period_start_date=now,
        period_end_date=now,
        period_type="school_year",
    )
    top.refresh_from_db()
    leaf.refresh_from_db()
    cyclist.refresh_from_db()
    assert snap.group_total_spendable == 80
    assert snap.details.get(group=leaf).velos_spendable == 35
    assert top.velos_total == 0
    assert top.distance_total == Decimal("0.00000")
    assert top.velos_spendable == 80
    assert leaf.velos_spendable == 35
    assert cyclist.velos_balance == 0
    assert cyclist.distance_total == Decimal("0.00000")


@pytest.mark.django_db
def test_admin_year_end_preview_then_confirm(client, year_end_tree):
    top, leaf, cyclist = year_end_tree
    su = User.objects.create_superuser(username="ye-su", password="x", email="ye@ex.com")
    client.force_login(su)
    url = reverse("admin:api_yearendsnapshot_create")
    now = timezone.now().strftime("%Y-%m-%dT%H:%M")

    preview = client.post(
        url,
        {
            "group_id": str(top.pk),
            "period_type": "school_year",
            "snapshot_date": now,
            "period_start_date": now,
            "period_end_date": now,
            "step": "preview",
        },
    )
    assert preview.status_code == 200
    body = preview.content.decode("utf-8")
    assert "Vorschau" in body
    assert "YE School" in body
    assert "YE 2b" in body
    assert "YE-RADLER-1" in body
    assert YearEndSnapshot.objects.count() == 0

    confirm = client.post(
        url,
        {
            "group_id": str(top.pk),
            "period_type": "school_year",
            "snapshot_date": now,
            "period_start_date": now,
            "period_end_date": now,
            "step": "confirm",
            "confirm": "1",
        },
    )
    assert confirm.status_code == 302
    assert YearEndSnapshot.objects.count() == 1
    top.refresh_from_db()
    assert top.velos_total == 0
    assert top.velos_spendable == 80
