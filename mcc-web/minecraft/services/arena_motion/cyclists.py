# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    cyclists.py
# @note    TOP-group scoped cyclist lists for VeloArena operator UI.

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from api.models import Cyclist, Group


def top_groups_for_user(user) -> QuerySet[Group]:
    """TOP groups the operator may use for arena cyclist selection."""
    qs = Group.objects.filter(parent__isnull=True, is_visible=True).order_by("name")
    if getattr(user, "is_superuser", False):
        return qs
    managed = getattr(user, "managed_groups", None)
    if managed is None:
        return qs.none()
    managed_ids = list(managed.filter(is_visible=True).values_list("id", flat=True))
    if not managed_ids:
        return qs.none()
    # Operators are usually assigned TOP groups; also accept managed subgroups
    # by resolving their top parents.
    top_ids: set[int] = set()
    for group in Group.objects.filter(id__in=managed_ids, is_visible=True).select_related(
        "parent"
    ):
        current = group
        while current.parent_id is not None:
            current = current.parent
        if current.is_visible:
            top_ids.add(current.id)
    return qs.filter(id__in=top_ids)


def _descendant_group_ids(ancestor_id: int) -> set[int]:
    visited: set[int] = set()
    result: set[int] = {ancestor_id}

    def walk(group_id: int) -> None:
        if group_id in visited:
            return
        visited.add(group_id)
        children = Group.objects.filter(
            parent_id=group_id, is_visible=True
        ).values_list("id", flat=True)
        for child_id in children:
            result.add(child_id)
            walk(child_id)

    walk(ancestor_id)
    return result


def cyclists_for_top_group(
    top_group_id: int | None,
    *,
    search: str = "",
    limit: int = 200,
    allowed_top_group_ids: set[int] | list[int] | None = None,
    arena_sim_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Visible cyclists as dicts for arena selects.

    If top_group_id is set, filter to that TOP tree.
    If top_group_id is None and allowed_top_group_ids is set, union of those trees.
    If both are empty/None, return all visible cyclists (superuser "Alle").
    """
    qs = Cyclist.objects.filter(is_visible=True)
    if arena_sim_only:
        qs = qs.filter(is_arena_sim_allowed=True)
    if top_group_id:
        group_ids = _descendant_group_ids(int(top_group_id))
        qs = qs.filter(groups__id__in=group_ids).distinct()
    elif allowed_top_group_ids is not None:
        allowed = {int(x) for x in allowed_top_group_ids}
        if not allowed:
            return []
        group_ids: set[int] = set()
        for tid in allowed:
            group_ids.update(_descendant_group_ids(tid))
        qs = qs.filter(groups__id__in=group_ids).distinct()
    search = (search or "").strip()
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(user_id__icontains=search) | Q(id_tag__icontains=search))

    rows: list[dict[str, Any]] = []
    for cyclist in qs.prefetch_related("groups").order_by("user_id")[:limit]:
        primary = cyclist.groups.first()
        group_label = ""
        if primary is not None:
            subgroup_name = (
                primary.get_kiosk_label()
                if hasattr(primary, "get_kiosk_label")
                else primary.name
            )
            top_parent = getattr(primary, "top_parent_name", "") or ""
            if top_parent and top_parent != subgroup_name:
                group_label = f"{top_parent} – {subgroup_name}"
            else:
                group_label = subgroup_name
        rows.append(
            {
                "user_id": cyclist.user_id,
                "id_tag": cyclist.id_tag,
                "group_label": group_label,
                "is_arena_sim_allowed": bool(cyclist.is_arena_sim_allowed),
            }
        )
    return rows


def devices_for_top_group(
    top_group_id: int | None,
    *,
    search: str = "",
    limit: int = 200,
    allowed_top_group_ids: set[int] | list[int] | None = None,
    arena_sim_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Visible IoT devices for arena lane assignment.

    Like Game-GUI: devices are filtered by TOP group (Device.group), not subgroup.
    """
    from iot.models import Device

    qs = Device.objects.filter(is_visible=True).select_related("configuration", "group")
    if arena_sim_only:
        qs = qs.filter(is_arena_sim_allowed=True)
    if top_group_id:
        qs = qs.filter(group_id=int(top_group_id))
    elif allowed_top_group_ids is not None:
        allowed = {int(x) for x in allowed_top_group_ids}
        if not allowed:
            return []
        qs = qs.filter(group_id__in=allowed)

    search = (search or "").strip()
    if search:
        from django.db.models import Q

        qs = qs.filter(Q(display_name__icontains=search) | Q(name__icontains=search))

    rows: list[dict[str, Any]] = []
    for device in qs.order_by("display_name", "name")[:limit]:
        display = device.display_name or device.name
        try:
            wheel_mm = int(device.radumfang_mm)
        except Exception:
            wheel_mm = 2075
        try:
            fkm = float(device.get_fkm_factor())
        except Exception:
            fkm = 1.0
        group_name = device.group.name if device.group_id else ""
        rows.append(
            {
                "name": device.name,
                "display_name": display,
                "group_name": group_name,
                "wheel_mm": wheel_mm,
                "fkm_factor": round(fkm, 4),
                "is_arena_sim_allowed": bool(device.is_arena_sim_allowed),
            }
        )
    return rows


def resolve_device_motion_params(device_name: str) -> dict[str, Any]:
    """Load wheel/FKM/send-interval params for an IoT device name (Device.name)."""
    from iot.models import Device
    from minecraft.services.arena_motion.iot_update_sim import (
        DEFAULT_SIM_UPDATE_INTERVAL_SECONDS,
        clamp_send_interval,
    )

    name = (device_name or "").strip()
    if not name:
        raise ValueError("device_name required")
    try:
        device = Device.objects.select_related("configuration", "group").get(name=name)
    except Device.DoesNotExist as exc:
        raise ValueError(f"Unbekanntes IoT-Gerät: {name}") from exc
    display = device.display_name or device.name
    wheel_mm = int(device.radumfang_mm)
    fkm = float(device.get_fkm_factor())
    send_interval = DEFAULT_SIM_UPDATE_INTERVAL_SECONDS
    cfg = getattr(device, "configuration", None)
    if cfg is not None:
        try:
            send_interval = int(cfg.send_interval_seconds)
        except (TypeError, ValueError):
            send_interval = int(DEFAULT_SIM_UPDATE_INTERVAL_SECONDS)
    return {
        "device_name": device.name,
        "device_display": display,
        "wheel_mm": wheel_mm,
        "device_factor": fkm,
        "send_interval_seconds": clamp_send_interval(send_interval),
    }
