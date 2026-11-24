# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Map inventory itemstrings (often dig drops) back to shop rows / purchase credit.

from __future__ import annotations

from api.models import Group
from luanti.models import LuantiShopItem, LuantiShopPurchaseCredit
from luanti.services.mcl_map import resolve_name

# Dug block → shop row that may hold the purchase credit.
# Mineclonia names stay until luanti_convert_from_mineclonia has renamed the shop.
INVENTORY_TO_SHOP_CREDIT_ALIASES: dict[str, tuple[str, ...]] = {
    "default:cobble": ("default:stone",),
    "default:dirt": ("default:dirt_with_grass",),
    "mcl_core:cobble": ("mcl_core:stone",),
    "mcl_core:dirt": ("mcl_core:dirt_with_grass",),
}

_ENABLED_SHOP_QS = LuantiShopItem.objects.filter(
    enabled=True, category__enabled=True
).select_related("category")


def stair_shop_credit_item_name(item_name: str) -> str:
    """Stair corners resolve through mcl_map to the standard stair node."""
    return shop_credit_item_name(item_name)


def door_shop_credit_item_name(item_name: str) -> str:
    """Door halves resolve through mcl_map to the standard door node."""
    return shop_credit_item_name(item_name)


def shop_credit_item_name(item_name: str) -> str:
    name = (item_name or "").strip()
    resolved = resolve_name(name)
    return resolved or name


def credit_item_name_candidates(inventory_name: str) -> list[str]:
    raw = (inventory_name or "").strip()
    if not raw:
        return []
    resolved = shop_credit_item_name(raw)
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    add(raw)
    add(resolved)
    for key in (raw, resolved):
        for alias in INVENTORY_TO_SHOP_CREDIT_ALIASES.get(key, ()):
            add(alias)
            add(shop_credit_item_name(alias))
    return names


def resolve_shop_item_for_inventory_name(
    inventory_name: str,
    *,
    group: Group | None = None,
) -> LuantiShopItem | None:
    """Resolve a sell-zone stack to a shop row / purchase-credit item_name.

    When both cobble and stone exist in the shop, selling dug cobble must consume
    stone credit if that is where the wallet has balance (stone buy → dig → cobble).
    """
    names = credit_item_name_candidates(inventory_name)
    if not names:
        return None
    items_by_name: dict[str, LuantiShopItem] = {}
    for candidate in names:
        item = _ENABLED_SHOP_QS.filter(item_name=candidate).order_by("id").first()
        if item:
            items_by_name[candidate] = item
    if not items_by_name:
        return None

    if group is not None:
        credit_rows = LuantiShopPurchaseCredit.objects.filter(
            group=group, item_name__in=items_by_name.keys()
        )
        available = {row.item_name: int(row.quantity) for row in credit_rows}
        for candidate in names:
            item = items_by_name.get(candidate)
            if item and available.get(item.item_name, 0) > 0:
                return item

    for candidate in names:
        item = items_by_name.get(candidate)
        if item:
            return item
    return None
