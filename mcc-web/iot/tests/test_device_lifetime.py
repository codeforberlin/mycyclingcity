# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from api.models import Group, GroupType
from api.services.year_end import collect_year_end_preview, execute_year_end_snapshot
from iot.models import Device


@pytest.mark.django_db
def test_year_end_keeps_device_lifetime():
    gtype, _ = GroupType.objects.get_or_create(name="DevLifeType")
    top = Group.objects.create(name="LifeTOP", group_type=gtype, distance_total=Decimal("1.0"))
    device = Device.objects.create(
        name="life-box-1",
        display_name="Life Box",
        group=top,
        distance_total=Decimal("12.50000"),
        distance_lifetime_km=Decimal("100.00000"),
    )
    now = timezone.now()
    execute_year_end_snapshot(
        top_group=top,
        snapshot_date=now,
        period_start_date=now,
        period_end_date=now,
        period_type="school_year",
    )
    device.refresh_from_db()
    assert device.distance_total == Decimal("0.00000")
    assert device.distance_lifetime_km == Decimal("100.00000")


@pytest.mark.django_db
def test_year_end_preview_includes_lifetime():
    gtype, _ = GroupType.objects.get_or_create(name="DevLifePreview")
    top = Group.objects.create(name="PrevTOP", group_type=gtype)
    Device.objects.create(
        name="prev-box",
        group=top,
        distance_total=Decimal("3.00000"),
        distance_lifetime_km=Decimal("33.00000"),
    )
    preview = collect_year_end_preview(top)
    assert preview["counts"]["devices"] == 1
    assert preview["devices"][0]["distance_lifetime_km"] == Decimal("33.00000")
    assert preview["totals"]["devices_lifetime_sum"] == Decimal("33.00000")
