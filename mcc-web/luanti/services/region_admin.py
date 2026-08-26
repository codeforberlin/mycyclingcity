# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_admin.py
# @note    Shared helpers for Luanti protected-region Admin UI.

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Max, Prefetch, QuerySet
from django.utils.translation import gettext as _

from api.models import Group
from luanti.models import LuantiAccount, LuantiProtectedRegion
from luanti.services.region_ops import (
    default_region_max_y,
    default_region_min_y,
    default_world,
    normalize_region_id,
    parse_int_coord,
    suggest_subregion_id,
)


def top_groups_queryset() -> QuerySet[Group]:
    return Group.objects.filter(parent__isnull=True, is_visible=True).order_by("name")


def region_label(region: LuantiProtectedRegion) -> str:
    name = (region.display_name or "").strip() or region.region_id
    if region.parent_id:
        parent = region.parent
        parent_name = (
            (parent.display_name or "").strip() or parent.region_id if parent else "?"
        )
        return f"{parent_name} › {name}"
    return name


def master_regions_queryset() -> QuerySet[LuantiProtectedRegion]:
    return (
        LuantiProtectedRegion.objects.filter(parent__isnull=True)
        .select_related("assigned_to_group")
        .order_by("sort_order", "region_id")
    )


def sibling_regions_queryset(region: LuantiProtectedRegion) -> QuerySet[LuantiProtectedRegion]:
    return LuantiProtectedRegion.objects.filter(parent_id=region.parent_id).order_by(
        "sort_order", "region_id", "pk"
    )


def next_sort_order(*, parent_id: int | None) -> int:
    current = (
        LuantiProtectedRegion.objects.filter(parent_id=parent_id).aggregate(m=Max("sort_order"))[
            "m"
        ]
        or 0
    )
    return int(current) + 10


def move_region(region: LuantiProtectedRegion, delta: int) -> bool:
    if delta not in (-1, 1):
        return False
    siblings = list(sibling_regions_queryset(region))
    if len(siblings) < 2:
        return False
    idx = next((i for i, r in enumerate(siblings) if r.pk == region.pk), None)
    if idx is None:
        return False
    new_idx = idx + delta
    if new_idx < 0 or new_idx >= len(siblings):
        return False
    siblings.insert(new_idx, siblings.pop(idx))
    for i, sibling in enumerate(siblings):
        desired = i * 10
        if sibling.sort_order != desired:
            LuantiProtectedRegion.objects.filter(pk=sibling.pk).update(sort_order=desired)
    return True


def hierarchical_region_list() -> list[LuantiProtectedRegion]:
    masters = list(
        LuantiProtectedRegion.objects.filter(parent__isnull=True)
        .select_related("assigned_to_group")
        .prefetch_related(
            Prefetch(
                "subregions",
                queryset=LuantiProtectedRegion.objects.select_related(
                    "parent", "assigned_to_group"
                )
                .prefetch_related("members")
                .order_by("sort_order", "region_id"),
            ),
            "members",
        )
        .order_by("sort_order", "region_id")
    )
    rows: list[LuantiProtectedRegion] = []
    for master in masters:
        rows.append(master)
        rows.extend(list(master.subregions.all()))
    return rows


def annotate_move_flags(
    regions: list[LuantiProtectedRegion],
) -> list[LuantiProtectedRegion]:
    by_parent: dict[int | None, list[LuantiProtectedRegion]] = {}
    for region in regions:
        by_parent.setdefault(region.parent_id, []).append(region)
    for group in by_parent.values():
        for i, region in enumerate(group):
            region.can_move_up = i > 0  # type: ignore[attr-defined]
            region.can_move_down = i < len(group) - 1  # type: ignore[attr-defined]
    return regions


def validation_error_message(exc: ValidationError) -> str:
    if hasattr(exc, "message_dict"):
        parts: list[str] = []
        for _field, msgs in exc.message_dict.items():
            for msg in msgs:
                parts.append(str(msg))
        return "; ".join(parts) if parts else str(exc)
    if hasattr(exc, "messages"):
        return "; ".join(str(m) for m in exc.messages)
    return str(exc)


def empty_region_draft() -> dict:
    return {
        "pk": "",
        "region_id": "",
        "display_name": "",
        "world": default_world(),
        "parent_id": "",
        "assigned_to_group_id": "",
        "min_x": "",
        "min_y": default_region_min_y(),
        "min_z": "",
        "max_x": "",
        "max_y": default_region_max_y(),
        "max_z": "",
        "spawn_x": "",
        "spawn_y": "",
        "spawn_z": "",
        "protect_build": True,
        "enabled": True,
        "notes": "",
        "member_ids": [],
        "player": "",
        "sub_slug": "",
    }


def region_to_draft(region: LuantiProtectedRegion, *, player: str = "") -> dict:
    return {
        "pk": str(region.pk),
        "region_id": region.region_id,
        "display_name": region.display_name,
        "world": region.world,
        "parent_id": str(region.parent_id or ""),
        "assigned_to_group_id": str(region.assigned_to_group_id or ""),
        "min_x": region.min_x,
        "min_y": region.min_y,
        "min_z": region.min_z,
        "max_x": region.max_x,
        "max_y": region.max_y,
        "max_z": region.max_z,
        "spawn_x": "" if region.spawn_x is None else region.spawn_x,
        "spawn_y": "" if region.spawn_y is None else region.spawn_y,
        "spawn_z": "" if region.spawn_z is None else region.spawn_z,
        "protect_build": region.protect_build,
        "enabled": region.enabled,
        "notes": region.notes,
        "member_ids": list(region.members.values_list("pk", flat=True)),
        "player": player,
        "sub_slug": "",
    }


def draft_from_post(post, *, keep_y_defaults: bool = False) -> dict:
    min_y_default = default_region_min_y()
    max_y_default = default_region_max_y()

    def _keep_y(raw, default: int) -> int | str:
        text = str(raw if raw is not None else "").strip()
        if text == "":
            return default if keep_y_defaults else ""
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return default if keep_y_defaults else text

    return {
        "pk": (post.get("rg_pk") or "").strip(),
        "region_id": (post.get("rg_region_id") or "").strip(),
        "display_name": (post.get("rg_display_name") or "").strip(),
        "world": (post.get("rg_world") or default_world()).strip(),
        "parent_id": (post.get("rg_parent") or "").strip(),
        "assigned_to_group_id": (post.get("rg_assigned_to_group") or "").strip(),
        "min_x": post.get("rg_min_x") or "",
        "min_y": _keep_y(post.get("rg_min_y"), min_y_default),
        "min_z": post.get("rg_min_z") or "",
        "max_x": post.get("rg_max_x") or "",
        "max_y": _keep_y(post.get("rg_max_y"), max_y_default),
        "max_z": post.get("rg_max_z") or "",
        "spawn_x": post.get("rg_spawn_x") or "",
        "spawn_y": post.get("rg_spawn_y") or "",
        "spawn_z": post.get("rg_spawn_z") or "",
        "protect_build": post.get("rg_protect_build") == "on",
        "enabled": post.get("rg_enabled") == "on",
        "notes": (post.get("rg_notes") or "").strip(),
        "member_ids": [int(v) for v in post.getlist("rg_members") if str(v).isdigit()],
        "player": (post.get("rg_player") or "").strip(),
        "sub_slug": (post.get("rg_sub_slug") or "").strip(),
    }


def parse_optional_spawn_coords(post) -> tuple[int | None, int | None, int | None]:
    if post.get("rg_clear_spawn") == "on":
        return None, None, None
    texts = [
        str(post.get("rg_spawn_x") if post.get("rg_spawn_x") is not None else "").strip(),
        str(post.get("rg_spawn_y") if post.get("rg_spawn_y") is not None else "").strip(),
        str(post.get("rg_spawn_z") if post.get("rg_spawn_z") is not None else "").strip(),
    ]
    if all(t == "" for t in texts):
        return None, None, None
    if any(t == "" for t in texts):
        raise ValueError(
            _("Spawn-Punkt: X, Y und Z müssen zusammen gesetzt werden (oder alle leer).")
        )
    return (
        parse_int_coord(texts[0], "spawn_x"),
        parse_int_coord(texts[1], "spawn_y"),
        parse_int_coord(texts[2], "spawn_z"),
    )


def save_region_from_post(post, *, user) -> LuantiProtectedRegion:
    pk_raw = (post.get("rg_pk") or "").strip()
    display_name = (post.get("rg_display_name") or "").strip()
    notes = (post.get("rg_notes") or "").strip()
    protect_build = post.get("rg_protect_build") == "on"
    enabled = post.get("rg_enabled") == "on"
    world = (post.get("rg_world") or default_world()).strip() or default_world()
    min_x = parse_int_coord(post.get("rg_min_x"), "min_x")
    min_y = parse_int_coord(post.get("rg_min_y"), "min_y")
    min_z = parse_int_coord(post.get("rg_min_z"), "min_z")
    max_x = parse_int_coord(post.get("rg_max_x"), "max_x")
    max_y = parse_int_coord(post.get("rg_max_y"), "max_y")
    max_z = parse_int_coord(post.get("rg_max_z"), "max_z")
    spawn_x, spawn_y, spawn_z = parse_optional_spawn_coords(post)
    member_ids = [int(v) for v in post.getlist("rg_members") if str(v).isdigit()]

    parent = None
    parent_raw = (post.get("rg_parent") or "").strip()
    if parent_raw:
        parent = LuantiProtectedRegion.objects.filter(
            pk=int(parent_raw), parent__isnull=True
        ).first()
        if parent is None:
            raise ValueError(_("Ungültige Master-Region."))

    assigned_group = None
    assigned_raw = (post.get("rg_assigned_to_group") or "").strip()
    if assigned_raw and not parent:
        assigned_group = top_groups_queryset().filter(pk=int(assigned_raw)).first()
        if assigned_group is None:
            raise ValueError(_("Ungültige TOP-Gruppe."))

    if pk_raw:
        region = LuantiProtectedRegion.objects.filter(pk=int(pk_raw)).first()
        if region is None:
            raise ValueError(_("Region nicht gefunden."))
        region_id = region.region_id
        if parent and not region.parent_id:
            raise ValueError(_("Eine bestehende Master-Region kann nicht zur Subregion werden."))
        if region.parent_id and parent is None:
            raise ValueError(_("Subregion braucht weiterhin eine Master-Region."))
        if parent and region.parent_id and parent.pk != region.parent_id:
            raise ValueError(_("Master-Region einer Subregion darf nicht gewechselt werden."))
    else:
        region = LuantiProtectedRegion()
        if parent:
            sub_slug = (post.get("rg_sub_slug") or "").strip()
            raw_id = (post.get("rg_region_id") or "").strip()
            region_id = raw_id or suggest_subregion_id(parent.region_id, sub_slug)
        else:
            region_id = normalize_region_id(post.get("rg_region_id") or "")
        if LuantiProtectedRegion.objects.filter(region_id__iexact=region_id).exists():
            raise ValueError(_("Region-ID „%(id)s“ existiert bereits.") % {"id": region_id})

    region.region_id = region_id
    region.display_name = display_name
    region.world = world if not parent else parent.world
    region.parent = parent
    region.assigned_to_group = None if parent else assigned_group
    region.min_x = min_x
    region.min_y = min_y
    region.min_z = min_z
    region.max_x = max_x
    region.max_y = max_y
    region.max_z = max_z
    region.spawn_x = spawn_x
    region.spawn_y = spawn_y
    region.spawn_z = spawn_z
    region.protect_build = protect_build
    region.enabled = enabled
    region.notes = notes
    if getattr(user, "is_authenticated", False):
        region.updated_by = user
    if not region.pk:
        region.sort_order = next_sort_order(parent_id=parent.pk if parent else None)

    region.full_clean()
    region.save()
    region.members.set(
        LuantiAccount.objects.filter(pk__in=member_ids, is_active=True)
    )
    return region


def account_choices() -> QuerySet[LuantiAccount]:
    return LuantiAccount.objects.filter(is_active=True).order_by("sort_order", "login_name")


def online_player_names() -> list[str]:
    """Login names currently waiting or in an open session."""
    from luanti.models import LuantiSession, LuantiWaitingPlayer

    names: set[str] = set(
        LuantiWaitingPlayer.objects.values_list("login_name", flat=True)
    )
    names.update(
        LuantiSession.objects.filter(status__in=LuantiSession.OPEN_STATUSES).values_list(
            "login_name", flat=True
        )
    )
    return sorted(names, key=str.lower)
