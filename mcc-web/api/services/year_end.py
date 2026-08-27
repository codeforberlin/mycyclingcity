# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Year-end snapshot preview and execution (KM / velos_total reset; spendable kept).

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet

from api.models import Cyclist, Group, YearEndSnapshot, YearEndSnapshotDetail
from eventboard.utils import get_all_subgroup_ids


class YearEndError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _affected_queryset(top_group: Group) -> tuple[list[int], QuerySet, QuerySet, QuerySet]:
    from iot.models import Device

    if top_group.parent_id is not None:
        raise YearEndError("not_top_group")

    subgroup_ids = list(get_all_subgroup_ids(top_group, visible_only=False))
    # get_all_subgroup_ids already includes the TOP itself.
    groups = Group.objects.filter(id__in=subgroup_ids).select_related("parent").order_by("name")
    cyclists = (
        Cyclist.objects.filter(groups__id__in=subgroup_ids)
        .distinct()
        .order_by("user_id")
    )
    devices = (
        Device.objects.filter(group__id__in=subgroup_ids)
        .select_related("group")
        .order_by("name")
    )
    return subgroup_ids, groups, cyclists, devices


def collect_year_end_preview(top_group: Group) -> dict:
    """
    Read-only snapshot of everything that would be archived / reset.

    Spendable is included for review but is NOT reset on execute.
    """
    _, groups, cyclists, devices = _affected_queryset(top_group)

    group_rows = [
        {
            "id": g.pk,
            "name": g.name,
            "parent_name": g.parent.name if g.parent_id else None,
            "is_top": g.parent_id is None,
            "is_visible": bool(g.is_visible),
            "distance_total": g.distance_total,
            "velos_total": int(g.velos_total or 0),
            "velos_spendable": int(g.velos_spendable or 0),
        }
        for g in groups
    ]
    cyclist_rows = [
        {
            "id": c.pk,
            "user_id": c.user_id,
            "distance_total": c.distance_total,
            "velos_balance": int(c.velos_balance or 0),
        }
        for c in cyclists
    ]
    device_rows = [
        {
            "id": d.pk,
            "name": d.name,
            "display_name": getattr(d, "display_name", None) or d.name,
            "group_name": d.group.name if d.group_id else "—",
            "distance_total": d.distance_total,
            "distance_lifetime_km": getattr(d, "distance_lifetime_km", None) or Decimal("0.00000"),
        }
        for d in devices
    ]

    return {
        "top_group": {"id": top_group.pk, "name": top_group.name},
        "counts": {
            "groups": len(group_rows),
            "cyclists": len(cyclist_rows),
            "devices": len(device_rows),
        },
        "totals": {
            "group_km": top_group.distance_total,
            "group_velos": int(top_group.velos_total or 0),
            "group_spendable": int(top_group.velos_spendable or 0),
            "groups_km_sum": sum((r["distance_total"] or Decimal("0") for r in group_rows), Decimal("0")),
            "groups_velos_sum": sum(r["velos_total"] for r in group_rows),
            "groups_spendable_sum": sum(r["velos_spendable"] for r in group_rows),
            "cyclists_km_sum": sum(
                (r["distance_total"] or Decimal("0") for r in cyclist_rows), Decimal("0")
            ),
            "cyclists_balance_sum": sum(r["velos_balance"] for r in cyclist_rows),
            "devices_km_sum": sum(
                (r["distance_total"] or Decimal("0") for r in device_rows), Decimal("0")
            ),
            "devices_lifetime_sum": sum(
                (r["distance_lifetime_km"] or Decimal("0") for r in device_rows), Decimal("0")
            ),
        },
        "groups": group_rows,
        "cyclists": cyclist_rows,
        "devices": device_rows,
    }


@transaction.atomic
def execute_year_end_snapshot(
    *,
    top_group: Group,
    snapshot_date,
    period_start_date,
    period_end_date,
    period_type: str,
    user=None,
) -> YearEndSnapshot:
    """
    Create YearEndSnapshot + details, then reset KM / velos_total / cyclist balance.
    Group.velos_spendable is stored but not reset.
    """
    _, groups, cyclists, devices = _affected_queryset(top_group)
    # Materialize before update() clears values we need to store.
    group_list = list(groups)
    cyclist_list = list(cyclists)
    device_list = list(devices)

    snapshot = YearEndSnapshot.objects.create(
        group=top_group,
        snapshot_date=snapshot_date,
        period_start_date=period_start_date,
        period_end_date=period_end_date,
        period_type=period_type,
        group_total_km=top_group.distance_total,
        group_total_velos=int(top_group.velos_total or 0),
        group_total_spendable=int(top_group.velos_spendable or 0),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )

    for group in group_list:
        YearEndSnapshotDetail.objects.create(
            snapshot=snapshot,
            group=group,
            distance_total=group.distance_total,
            velos_total=int(group.velos_total or 0),
            velos_spendable=int(group.velos_spendable or 0),
        )
    for cyclist in cyclist_list:
        YearEndSnapshotDetail.objects.create(
            snapshot=snapshot,
            cyclist=cyclist,
            distance_total=cyclist.distance_total,
            velos_total=int(cyclist.velos_balance or 0),
            velos_spendable=0,
        )
    for device in device_list:
        YearEndSnapshotDetail.objects.create(
            snapshot=snapshot,
            device=device,
            distance_total=device.distance_total,
            velos_total=0,
            velos_spendable=0,
        )

    Group.objects.filter(pk__in=[g.pk for g in group_list]).update(
        distance_total=Decimal("0.00000"),
        velos_total=0,
    )
    Cyclist.objects.filter(pk__in=[c.pk for c in cyclist_list]).update(
        distance_total=Decimal("0.00000"),
        velos_balance=0,
    )
    from iot.models import Device

    Device.objects.filter(pk__in=[d.pk for d in device_list]).update(
        distance_total=Decimal("0.00000"),
    )

    return snapshot


def collect_year_end_undo_preview(snapshot: YearEndSnapshot) -> dict:
    """Counts / summary for undo confirmation UI."""
    if snapshot.is_undone:
        raise YearEndError("already_undone")
    return {
        "snapshot_id": snapshot.pk,
        "group_name": snapshot.group.name if snapshot.group_id else "—",
        "snapshot_date": snapshot.snapshot_date,
        "period_type": snapshot.period_type,
        "counts": {
            "groups": snapshot.details.filter(group__isnull=False).count(),
            "cyclists": snapshot.details.filter(cyclist__isnull=False).count(),
            "devices": snapshot.details.filter(device__isnull=False).count(),
        },
        "group_total_km": snapshot.group_total_km,
        "group_total_velos": snapshot.group_total_velos,
        "group_total_spendable": int(snapshot.group_total_spendable or 0),
    }


@transaction.atomic
def undo_year_end_snapshot(*, snapshot: YearEndSnapshot, user=None) -> dict:
    """
    Restore KM / velos_total (groups) and cyclist distance + balance from snapshot.
    Does not touch Group.velos_spendable or Device.distance_lifetime_km.
    """
    if snapshot.is_undone:
        raise YearEndError("already_undone")

    from django.utils import timezone
    from api.helpers import invalidate_cache_for_top_group

    group_details = snapshot.details.filter(group__isnull=False).select_related("group")
    cyclist_details = snapshot.details.filter(cyclist__isnull=False).select_related("cyclist")
    device_details = snapshot.details.filter(device__isnull=False).select_related("device")

    group_count = 0
    for detail in group_details:
        if not detail.group_id:
            continue
        # Spendable was never reset — do not overwrite live shop balances.
        detail.group.distance_total = detail.distance_total
        detail.group.velos_total = int(detail.velos_total or 0)
        detail.group.save(update_fields=["distance_total", "velos_total"])
        group_count += 1

    cyclist_count = 0
    for detail in cyclist_details:
        if not detail.cyclist_id:
            continue
        detail.cyclist.distance_total = detail.distance_total
        # Snapshot stores cyclist velos_balance in velos_total.
        detail.cyclist.velos_balance = int(detail.velos_total or 0)
        detail.cyclist.save(update_fields=["distance_total", "velos_balance"])
        cyclist_count += 1

    device_count = 0
    for detail in device_details:
        if not detail.device_id:
            continue
        # Lifetime is never snapshotted/reset — only restore period ledger.
        detail.device.distance_total = detail.distance_total
        detail.device.save(update_fields=["distance_total"])
        device_count += 1

    snapshot.is_undone = True
    snapshot.undone_at = timezone.now()
    snapshot.undone_by = user if getattr(user, "is_authenticated", False) else None
    snapshot.save(update_fields=["is_undone", "undone_at", "undone_by"])

    invalidate_cache_for_top_group(snapshot.group)

    return {
        "snapshot_id": snapshot.pk,
        "groups": group_count,
        "cyclists": cyclist_count,
        "devices": device_count,
    }
