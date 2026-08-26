# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_import_mc.py
# @note    Import Minecraft shop catalog into Luanti shop (material → Mineclonia).

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.text import slugify

from luanti.models import LuantiShopCategory, LuantiShopItem
from luanti.services.material_map import resolve_material
from luanti.services.shop_registry import registry_name_set
from minecraft.models import MinecraftShopCategory


@dataclass
class McShopImportResult:
    categories_created: int = 0
    categories_updated: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_skipped: int = 0
    unmapped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return True


@transaction.atomic
def import_minecraft_shop_catalog(*, only_enabled: bool = True) -> McShopImportResult:
    """
    Copy Minecraft shop categories/items into Luanti shop tables.

    Items whose Bukkit material cannot be mapped (optionally against the live
    Mineclonia registry) are skipped and listed in ``unmapped``.
    """
    result = McShopImportResult()
    registry = registry_name_set()
    # Empty registry → optimistic heuristic (still useful before first dump).
    registry_or_none = registry or None

    cat_qs = MinecraftShopCategory.objects.all().order_by("sort_order", "slug")
    if only_enabled:
        cat_qs = cat_qs.filter(enabled=True)

    for mc_cat in cat_qs:
        slug = slugify(mc_cat.slug or mc_cat.name, allow_unicode=False).replace("-", "_")
        if not slug:
            slug = f"cat_{mc_cat.pk}"
        lu_cat, created = LuantiShopCategory.objects.get_or_create(
            slug=slug,
            defaults={
                "name": mc_cat.name,
                "sort_order": mc_cat.sort_order,
                "enabled": mc_cat.enabled,
            },
        )
        if created:
            result.categories_created += 1
        else:
            lu_cat.name = mc_cat.name
            lu_cat.sort_order = mc_cat.sort_order
            lu_cat.enabled = mc_cat.enabled
            lu_cat.save(update_fields=["name", "sort_order", "enabled"])
            result.categories_updated += 1

        item_qs = mc_cat.items.all().order_by("sort_order", "id")
        if only_enabled:
            item_qs = item_qs.filter(enabled=True)

        for mc_item in item_qs:
            mapped = resolve_material(mc_item.material, registry=registry_or_none)
            if not mapped:
                result.items_skipped += 1
                key = f"{mc_item.material}"
                if key not in result.unmapped:
                    result.unmapped.append(key)
                continue
            price = max(1, int(mc_item.buy_price_velos or 1))
            defaults = {
                "display_name": mc_item.display_name or "",
                "buy_price_velos": price,
                "stack_size": max(1, int(mc_item.stack_size or 1)),
                "sort_order": int(mc_item.sort_order or 0),
                "enabled": bool(mc_item.enabled),
            }
            obj, created = LuantiShopItem.objects.update_or_create(
                category=lu_cat,
                item_name=mapped,
                defaults=defaults,
            )
            if created:
                result.items_created += 1
            else:
                result.items_updated += 1

    return result


def add_registry_item_to_shop(
    *,
    item_name: str,
    category_slug: str,
    buy_price_velos: int,
    display_name: str = "",
    stack_size: int = 1,
) -> LuantiShopItem:
    """Manually add a Mineclonia item from the live registry into the shop."""
    item_name = (item_name or "").strip()
    if not item_name or ":" not in item_name:
        raise ValueError("invalid_item_name")
    price = max(1, int(buy_price_velos))
    cat = LuantiShopCategory.objects.filter(slug=category_slug).first()
    if cat is None:
        cat = LuantiShopCategory.objects.create(
            slug=category_slug or "misc",
            name=category_slug or "Misc",
            sort_order=999,
            enabled=True,
        )
    obj, _ = LuantiShopItem.objects.update_or_create(
        category=cat,
        item_name=item_name,
        defaults={
            "display_name": display_name or "",
            "buy_price_velos": price,
            "stack_size": max(1, int(stack_size)),
            "enabled": True,
        },
    )
    return obj
