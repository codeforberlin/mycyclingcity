# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_registry.py
# @note    Cache of Mineclonia itemstrings pushed by mcc_bridge.

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from luanti.models import LuantiRegisteredItem
from luanti.services.shop_plan_ghost import VALID_PLAN_GHOST_STATUSES

def registry_name_set() -> set[str]:
    return set(LuantiRegisteredItem.objects.values_list("item_name", flat=True))


def registry_count() -> int:
    return LuantiRegisteredItem.objects.count()


@transaction.atomic
def replace_registry_items(
    items: list[dict],
    *,
    clear: bool = False,
) -> int:
    """
    Upsert registry rows from bridge dump.

    When ``clear`` is True (first chunk of a dump), wipe the previous registry.
    """
    if clear:
        LuantiRegisteredItem.objects.all().delete()
    now = timezone.now()
    count = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("item_name") or "").strip()
        if not name or ":" not in name:
            continue
        desc = str(raw.get("description") or "")[:256]
        kind = str(raw.get("kind") or "item")[:16]
        drawtype = str(raw.get("drawtype") or "")[:32]
        inventory_image = str(raw.get("inventory_image") or "")[:128]
        wield_image = str(raw.get("wield_image") or "")[:128]
        not_in_creative = bool(raw.get("not_in_creative_inventory"))
        plan_ghost = str(raw.get("plan_ghost_status") or "").strip()[:16]
        if plan_ghost not in VALID_PLAN_GHOST_STATUSES:
            plan_ghost = ""
        plan_ghost_detail = str(raw.get("plan_ghost_detail") or "")[:128]
        defaults = {
            "description": desc,
            "kind": kind,
            "drawtype": drawtype,
            "inventory_image": inventory_image,
            "wield_image": wield_image,
            "not_in_creative_inventory": not_in_creative,
            "updated_at": now,
        }
        if plan_ghost:
            defaults["plan_ghost_status"] = plan_ghost
            defaults["plan_ghost_detail"] = plan_ghost_detail
            defaults["plan_ghost_checked_at"] = now
        LuantiRegisteredItem.objects.update_or_create(
            item_name=name,
            defaults=defaults,
        )
        count += 1
    return count


@transaction.atomic
def update_plan_ghost_status(items: list[dict]) -> int:
    """Merge plan hologram audit rows from VERIFY_PLAN_GHOST_SHOP."""
    now = timezone.now()
    count = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("item_name") or raw.get("name") or "").strip()
        if not name or ":" not in name:
            continue
        status = str(raw.get("plan_ghost_status") or "").strip()[:16]
        if status not in VALID_PLAN_GHOST_STATUSES:
            continue
        detail = str(raw.get("plan_ghost_detail") or "")[:128]
        updated = LuantiRegisteredItem.objects.filter(item_name=name).update(
            plan_ghost_status=status,
            plan_ghost_detail=detail,
            plan_ghost_checked_at=now,
        )
        if updated:
            count += 1
    return count


def request_registry_dump() -> bool:
    """Ask connected / queued bridge to dump registered items."""
    from luanti.consumers import LuantiEventConsumer

    return (
        LuantiEventConsumer.push_to_all_sync({"type": "DUMP_ITEM_REGISTRY"})
        > 0
    )


def request_plan_ghost_verify_shop() -> tuple[bool, int]:
    """Ask bridge to verify plan hologram clone for all enabled shop itemstrings."""
    from luanti.models import LuantiShopItem

    names = list(
        LuantiShopItem.objects.filter(enabled=True)
        .order_by("item_name")
        .values_list("item_name", flat=True)
    )
    if not names:
        return False, 0
    from luanti.consumers import LuantiEventConsumer

    sent = (
        LuantiEventConsumer.push_to_all_sync(
            {
                "type": "VERIFY_PLAN_GHOST_SHOP",
                "item_names": names,
            }
        )
        > 0
    )
    return sent, len(names)
