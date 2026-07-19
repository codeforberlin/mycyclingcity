# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from minecraft.models import MinecraftShopCategory, MinecraftShopItem


def build_shop_catalog_payload() -> dict:
    """Serialize enabled shop categories and items for MCC-Bridge / EconomyShopGUI sync."""
    categories = []
    for category in MinecraftShopCategory.objects.filter(enabled=True).prefetch_related("items"):
        items = []
        for item in category.items.filter(enabled=True):
            item_payload = {
                "material": item.material.upper(),
                "display_name": item.display_name,
                "buy_price_velos": int(item.buy_price_velos),
                "stack_size": int(item.stack_size),
                "sort_order": int(item.sort_order),
            }
            if item.esgui_item_key:
                item_payload["esgui_item_key"] = item.esgui_item_key
            if item.esgui_item_loc:
                item_payload["esgui_item_loc"] = item.esgui_item_loc
            items.append(item_payload)
        categories.append(
            {
                "slug": category.slug,
                "name": category.name,
                "section": category.section_key,
                "sort_order": int(category.sort_order),
                "items": items,
            }
        )
    return {"version": 1, "categories": categories}


def category_count() -> int:
    return MinecraftShopCategory.objects.filter(enabled=True).count()


def item_count() -> int:
    return MinecraftShopItem.objects.filter(enabled=True, category__enabled=True).count()
