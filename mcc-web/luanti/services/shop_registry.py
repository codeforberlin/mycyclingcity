# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_registry.py
# @note    Cache of Mineclonia itemstrings pushed by mcc_bridge.

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from luanti.models import LuantiRegisteredItem


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
        LuantiRegisteredItem.objects.update_or_create(
            item_name=name,
            defaults={"description": desc, "kind": kind, "updated_at": now},
        )
        count += 1
    return count


def request_registry_dump() -> bool:
    """Ask connected / queued bridge to dump registered items."""
    from luanti.consumers import LuantiEventConsumer

    return (
        LuantiEventConsumer.push_to_all_sync({"type": "DUMP_ITEM_REGISTRY"})
        > 0
    )
