# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Map inventory itemstrings (often dig drops) back to shop rows / purchase credit.

from __future__ import annotations

from api.models import Group
from luanti.models import LuantiShopItem, LuantiShopPurchaseCredit

# Inventory item when selling → extra shop item_name(s) that may hold purchase credit.
INVENTORY_TO_SHOP_CREDIT_ALIASES: dict[str, tuple[str, ...]] = {
    "mcl_core:cobble": ("mcl_core:stone",),
    "mcl_core:dirt": (
        "mcl_core:dirt_with_grass",
        "mcl_core:grass_path",
        "mcl_core:podzol",
        "mcl_core:mycelium",
    ),
}

_ENABLED_SHOP_QS = LuantiShopItem.objects.filter(
    enabled=True, category__enabled=True
).select_related("category")


def stair_shop_credit_item_name(item_name: str) -> str:
    """Mineclonia stair nodes (_inner/_outer) map to one shop/credit item (base stair)."""
    name = (item_name or "").strip()
    base = _mcl_stair_base_name(name)
    return base if base else name


def door_shop_credit_item_name(item_name: str) -> str:
    """Door world nodes (_b_# / _t_#) map to the shop craft item (mcl_doors:… without suffix)."""
    name = (item_name or "").strip()
    if not name.startswith("mcl_doors:"):
        return name
    for sep in ("_b_", "_t_"):
        idx = name.rfind(sep)
        if idx > len("mcl_doors:") and name[idx + len(sep) :].isdigit():
            return name[:idx]
    return name


def shop_credit_item_name(item_name: str) -> str:
    return door_shop_credit_item_name(stair_shop_credit_item_name(item_name))


def _mcl_stair_base_name(item_name: str) -> str | None:
    if not item_name.startswith("mcl_stairs:stair_"):
        return None
    if item_name.endswith("_inner"):
        return item_name[: -len("_inner")]
    if item_name.endswith("_outer"):
        return item_name[: -len("_outer")]
    return item_name


def _mcl_stair_shape_aliases(item_name: str) -> tuple[str, ...]:
    base = _mcl_stair_base_name(item_name)
    if not base:
        return ()
    variants = (base, f"{base}_inner", f"{base}_outer")
    return tuple(v for v in variants if v != item_name)


def credit_item_name_candidates(inventory_name: str) -> list[str]:
    name = (inventory_name or "").strip()
    if not name:
        return []
    names = [name]
    for alias in INVENTORY_TO_SHOP_CREDIT_ALIASES.get(name, ()):
        if alias not in names:
            names.append(alias)
    for alias in _mcl_stair_shape_aliases(name):
        if alias not in names:
            names.append(alias)
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
