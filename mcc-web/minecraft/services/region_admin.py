# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    region_admin.py
# @note    Shared helpers for Stadtsteuerung and TOP-operator region UIs.

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, QuerySet
from django.utils.translation import gettext as _

from api.models import Group
from minecraft.models import MinecraftProtectedRegion, MinecraftTeamRegistration
from minecraft.services.region_ops import (
    default_region_max_y,
    default_region_min_y,
    normalize_region_id,
    paper_world,
    parse_int_coord,
    suggest_subregion_id,
)


def top_groups_queryset() -> QuerySet[Group]:
    return Group.objects.filter(parent__isnull=True, is_visible=True).order_by("name")


def region_label(region) -> str:
    """Human-readable label; subs prefixed with master name."""
    name = (region.display_name or "").strip() or region.region_id
    if region.parent_id:
        parent = region.parent
        parent_name = (
            (parent.display_name or "").strip() or parent.region_id if parent else "?"
        )
        return f"{parent_name} › {name}"
    return name


def regions_for_builder(registration) -> list:
    """
    Protected regions where this Bau-Account is an explicit WG member (builders M2M).
    """
    if registration is None or not getattr(registration, "pk", None):
        return []
    return list(
        MinecraftProtectedRegion.objects.filter(builders=registration)
        .select_related("parent")
        .order_by("sort_order", "region_id")
    )


def regions_for_builder_choices(registration) -> list[dict]:
    """[{pk, region_id, label}, ...] for Bau-Session tile selects."""
    return [
        {
            "pk": region.pk,
            "region_id": region.region_id,
            "label": region_label(region),
        }
        for region in regions_for_builder(registration)
    ]


def master_regions_queryset() -> QuerySet[MinecraftProtectedRegion]:
    return (
        MinecraftProtectedRegion.objects.filter(parent__isnull=True)
        .select_related("assigned_to_group")
        .order_by("sort_order", "region_id")
    )


def sibling_regions_queryset(
    region: MinecraftProtectedRegion,
) -> QuerySet[MinecraftProtectedRegion]:
    return MinecraftProtectedRegion.objects.filter(parent_id=region.parent_id).order_by(
        "sort_order", "region_id", "pk"
    )


def next_sort_order(*, parent_id: int | None) -> int:
    from django.db.models import Max

    current = (
        MinecraftProtectedRegion.objects.filter(parent_id=parent_id).aggregate(
            m=Max("sort_order")
        )["m"]
        or 0
    )
    return int(current) + 10


def renumber_siblings(parent_id: int | None) -> None:
    siblings = list(
        MinecraftProtectedRegion.objects.filter(parent_id=parent_id).order_by(
            "sort_order", "region_id", "pk"
        )
    )
    for i, sibling in enumerate(siblings):
        desired = i * 10
        if sibling.sort_order != desired:
            MinecraftProtectedRegion.objects.filter(pk=sibling.pk).update(
                sort_order=desired
            )


def move_region(region: MinecraftProtectedRegion, delta: int) -> bool:
    """
    Move region among siblings (same parent). delta=-1 up, +1 down.
    Returns True if the order changed.
    """
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
            MinecraftProtectedRegion.objects.filter(pk=sibling.pk).update(
                sort_order=desired
            )
    return True


def hierarchical_region_list() -> list[MinecraftProtectedRegion]:
    """Masters by sort_order, each followed by its subregions by sort_order."""
    masters = list(
        MinecraftProtectedRegion.objects.filter(parent__isnull=True)
        .select_related("assigned_to_group")
        .prefetch_related(
            Prefetch(
                "subregions",
                queryset=MinecraftProtectedRegion.objects.select_related(
                    "parent", "assigned_to_group"
                )
                .prefetch_related("builders")
                .order_by("sort_order", "region_id"),
            ),
            "builders",
        )
        .order_by("sort_order", "region_id")
    )
    rows: list[MinecraftProtectedRegion] = []
    for master in masters:
        rows.append(master)
        rows.extend(list(master.subregions.all()))
    return rows


def annotate_move_flags(
    regions: list[MinecraftProtectedRegion],
) -> list[MinecraftProtectedRegion]:
    """Attach can_move_up / can_move_down for template buttons (sibling scope)."""
    by_parent: dict[int | None, list[MinecraftProtectedRegion]] = {}
    for region in regions:
        by_parent.setdefault(region.parent_id, []).append(region)
    for group in by_parent.values():
        for i, region in enumerate(group):
            region.can_move_up = i > 0  # type: ignore[attr-defined]
            region.can_move_down = i < len(group) - 1  # type: ignore[attr-defined]
    return regions


def operator_managed_top_group_ids(user) -> list[int]:
    """TOP group IDs the user may manage (direct managed_groups that are roots)."""
    if getattr(user, "is_superuser", False):
        return list(top_groups_queryset().values_list("id", flat=True))
    managed = getattr(user, "managed_groups", None)
    if managed is None:
        return []
    return list(
        managed.filter(parent__isnull=True, is_visible=True).values_list("id", flat=True)
    )


def operator_master_regions(user) -> QuerySet[MinecraftProtectedRegion]:
    top_ids = operator_managed_top_group_ids(user)
    if not top_ids:
        return MinecraftProtectedRegion.objects.none()
    return (
        MinecraftProtectedRegion.objects.filter(
            parent__isnull=True,
            assigned_to_group_id__in=top_ids,
        )
        .select_related("assigned_to_group")
        .prefetch_related(
            Prefetch(
                "subregions",
                queryset=MinecraftProtectedRegion.objects.prefetch_related(
                    "builders"
                ).order_by("sort_order", "region_id"),
            )
        )
        .order_by("sort_order", "region_id")
    )


def operator_can_access_region(user, region: MinecraftProtectedRegion) -> bool:
    """Operator may edit subs of their masters; city admins use manage_protected_regions."""
    top_ids = set(operator_managed_top_group_ids(user))
    if not top_ids:
        return False
    if region.parent_id:
        master = region.parent
        return bool(
            master
            and master.assigned_to_group_id
            and master.assigned_to_group_id in top_ids
        )
    # Operators must not edit master bounds / TOP assignment
    return False


def operator_builder_choices(user) -> QuerySet[MinecraftTeamRegistration]:
    """Bau-Accounts under groups the operator manages (TOP + descendants)."""
    from mgmt.admin import get_operator_managed_group_ids

    group_ids = get_operator_managed_group_ids(user)
    qs = MinecraftTeamRegistration.objects.filter(is_active=True).exclude(ms_username="")
    if not getattr(user, "is_superuser", False):
        if not group_ids:
            return MinecraftTeamRegistration.objects.none()
        qs = qs.filter(group_id__in=group_ids)
    return qs.select_related("group").order_by("ms_username", "mc_username")


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


def empty_region_draft(*, for_operator: bool = False) -> dict:
    return {
        "pk": "",
        "region_id": "",
        "display_name": "",
        "world": paper_world(),
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
        "notes": "",
        "builder_ids": [],
        "player": "",
        "sub_slug": "",
        "for_operator": for_operator,
    }


def region_to_draft(region: MinecraftProtectedRegion, *, player: str = "") -> dict:
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
        "notes": region.notes,
        "builder_ids": list(region.builders.values_list("pk", flat=True)),
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
        "world": (post.get("rg_world") or paper_world()).strip(),
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
        "notes": (post.get("rg_notes") or "").strip(),
        "builder_ids": [int(v) for v in post.getlist("rg_builders") if str(v).isdigit()],
        "player": (post.get("rg_player") or "").strip(),
        "sub_slug": (post.get("rg_sub_slug") or "").strip(),
    }


def parse_optional_spawn_coords(post) -> tuple[int | None, int | None, int | None]:
    """Parse spawn_x/y/z from POST; all empty or all set. Clear checkbox wins."""
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


def save_region_from_post(
    post,
    *,
    user,
    operator_mode: bool = False,
) -> MinecraftProtectedRegion:
    """
    Create/update a protected region from POST data.

    In operator_mode: only subregions under the user's master regions; master
    fields (TOP assignment, master bounds) are not writable.
    """
    pk_raw = (post.get("rg_pk") or "").strip()
    display_name = (post.get("rg_display_name") or "").strip()
    notes = (post.get("rg_notes") or "").strip()
    protect_build = post.get("rg_protect_build") == "on"
    min_x = parse_int_coord(post.get("rg_min_x"), "min_x")
    min_y = parse_int_coord(post.get("rg_min_y"), "min_y")
    min_z = parse_int_coord(post.get("rg_min_z"), "min_z")
    max_x = parse_int_coord(post.get("rg_max_x"), "max_x")
    max_y = parse_int_coord(post.get("rg_max_y"), "max_y")
    max_z = parse_int_coord(post.get("rg_max_z"), "max_z")
    spawn_x, spawn_y, spawn_z = parse_optional_spawn_coords(post)
    builder_ids = [int(v) for v in post.getlist("rg_builders") if str(v).isdigit()]

    parent = None
    parent_raw = (post.get("rg_parent") or "").strip()
    if parent_raw:
        parent = MinecraftProtectedRegion.objects.filter(
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

    if operator_mode:
        if parent is None and not pk_raw:
            raise ValueError(_("Operatoren müssen eine Master-Region wählen."))
        if pk_raw:
            region = MinecraftProtectedRegion.objects.select_related("parent").get(
                pk=int(pk_raw)
            )
            if not operator_can_access_region(user, region):
                raise ValueError(_("Keine Berechtigung für diese Region."))
            parent = region.parent
            if parent is None:
                raise ValueError(_("Operatoren dürfen Master-Regionen nicht ändern."))
            region_id = normalize_region_id(region.region_id)
        else:
            top_ids = set(operator_managed_top_group_ids(user))
            if not parent or parent.assigned_to_group_id not in top_ids:
                raise ValueError(_("Keine Berechtigung für diese Master-Region."))
            sub_slug = (post.get("rg_sub_slug") or post.get("rg_region_id") or "").strip()
            region_id = suggest_subregion_id(parent.region_id, sub_slug)
        world = parent.world
        assigned_group = None
    else:
        region_id = normalize_region_id(post.get("rg_region_id") or "")
        world = (post.get("rg_world") or paper_world()).strip() or paper_world()
        if parent:
            assigned_group = None
            world = parent.world or world

        if pk_raw:
            region = MinecraftProtectedRegion.objects.get(pk=int(pk_raw))
            if region.region_id != region_id:
                if MinecraftProtectedRegion.objects.filter(region_id=region_id).exists():
                    raise ValueError(
                        _("Region-ID „%(id)s“ existiert bereits.") % {"id": region_id}
                    )
                region.region_id = region_id
        else:
            region, _created = MinecraftProtectedRegion.objects.get_or_create(
                region_id=region_id,
                defaults={
                    "min_x": min_x,
                    "min_y": min_y,
                    "min_z": min_z,
                    "max_x": max_x,
                    "max_y": max_y,
                    "max_z": max_z,
                    "world": world,
                    "parent": parent,
                    "assigned_to_group": assigned_group,
                    "sort_order": next_sort_order(
                        parent_id=parent.pk if parent else None
                    ),
                },
            )

    if operator_mode and not pk_raw:
        if MinecraftProtectedRegion.objects.filter(region_id=region_id).exists():
            raise ValueError(
                _("Region-ID „%(id)s“ existiert bereits.") % {"id": region_id}
            )
        region = MinecraftProtectedRegion(
            region_id=region_id,
            world=world,
            parent=parent,
            assigned_to_group=None,
            sort_order=next_sort_order(parent_id=parent.pk if parent else None),
            min_x=min_x,
            min_y=min_y,
            min_z=min_z,
            max_x=max_x,
            max_y=max_y,
            max_z=max_z,
        )

    region.display_name = display_name
    region.world = world
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
    region.notes = notes
    region.updated_by = user
    if not operator_mode:
        region.parent = parent
        region.assigned_to_group = assigned_group if parent is None else None
    else:
        region.parent = parent
        region.assigned_to_group = None

    try:
        region.save()
    except ValidationError as exc:
        raise ValueError(validation_error_message(exc)) from exc

    builder_qs = MinecraftTeamRegistration.objects.filter(
        pk__in=builder_ids, is_active=True
    )
    if operator_mode:
        allowed_ids = set(operator_builder_choices(user).values_list("pk", flat=True))
        builder_qs = builder_qs.filter(pk__in=allowed_ids)
    region.builders.set(builder_qs)
    return region
