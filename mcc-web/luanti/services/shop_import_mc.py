# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_import_mc.py
# @note    Import Minecraft shop catalog into Luanti shop (material → Mineclonia).

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.text import slugify

from luanti.models import LuantiRegisteredItem, LuantiShopCategory, LuantiShopItem
from luanti.services.shop_labels import (
    DEFAULT_LANG,
    set_category_label,
    set_item_label,
    suggested_category_label_de,
    suggested_category_label_en,
)
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


def normalize_shop_category_slug(raw: str) -> str:
    slug = slugify((raw or "").strip(), allow_unicode=False).replace("-", "_")
    return slug[:64]


def get_or_create_shop_category(
    *,
    slug: str,
    name: str = "",
    sort_order: int = 999,
    enabled: bool = True,
) -> tuple[LuantiShopCategory, bool]:
    """Resolve shop category by slug; create with display name when missing."""
    cat_slug = normalize_shop_category_slug(slug) or "misc"
    display = (name or "").strip() or cat_slug.replace("_", " ").title()
    cat, created = LuantiShopCategory.objects.get_or_create(
        slug=cat_slug,
        defaults={
            "name": display[:64],
            "sort_order": max(0, int(sort_order)),
            "enabled": enabled,
        },
    )
    if created:
        de_name = display[:64] or suggested_category_label_de(cat)
        set_category_label(cat, "de", de_name, overwrite=True)
        set_category_label(
            cat,
            "en",
            suggested_category_label_en(cat),
            overwrite=True,
            sync_legacy_de=False,
        )
    return cat, created


def default_stack_size_for_kind(kind: str) -> int:
    return 64 if (kind or "").strip() == "node" else 1


def _registry_row_map(names: list[str]) -> dict[str, LuantiRegisteredItem]:
    if not names:
        return {}
    rows = LuantiRegisteredItem.objects.filter(item_name__in=names)
    return {row.item_name: row for row in rows}


def registry_item_names_query(
    *,
    mod: str = "",
    q: str = "",
    only_missing: bool = True,
    shop_names: set[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Ordered itemstrings matching registry filters (for server-side bulk add)."""
    qs = LuantiRegisteredItem.objects.all()
    mod_filter = (mod or "").strip()
    if mod_filter:
        qs = qs.filter(item_name__startswith=f"{mod_filter}:")
    query = (q or "").strip()
    if query:
        qs = qs.filter(item_name__icontains=query)
    if only_missing and shop_names is not None:
        qs = qs.exclude(item_name__in=shop_names)
    qs = qs.order_by("item_name").values_list("item_name", flat=True)
    if limit is not None and limit > 0:
        qs = qs[:limit]
    return list(qs)


def count_missing_registry_items(*, shop_names: set[str] | None = None) -> int:
    qs = LuantiRegisteredItem.objects.all()
    if shop_names is not None:
        qs = qs.exclude(item_name__in=shop_names)
    return qs.count()


def missing_registry_counts_by_mod(*, shop_names: set[str] | None = None) -> dict[str, int]:
    """Count registry items not yet in shop, grouped by mod prefix."""
    qs = LuantiRegisteredItem.objects.all()
    if shop_names is not None:
        qs = qs.exclude(item_name__in=shop_names)
    counts: dict[str, int] = {}
    for name in qs.values_list("item_name", flat=True):
        if ":" not in name:
            continue
        mod = name.split(":", 1)[0]
        counts[mod] = counts.get(mod, 0) + 1
    return counts


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
            set_category_label(lu_cat, "de", mc_cat.name or suggested_category_label_de(lu_cat))
            set_category_label(
                lu_cat,
                "en",
                mc_cat.name or suggested_category_label_en(lu_cat),
                sync_legacy_de=False,
            )
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
    stack_size: int | None = None,
    category_name: str = "",
    category_sort_order: int = 999,
) -> LuantiShopItem:
    """Manually add a Mineclonia item from the live registry into the shop."""
    item_name = (item_name or "").strip()
    if not item_name or ":" not in item_name:
        raise ValueError("invalid_item_name")
    price = max(1, int(buy_price_velos))
    cat, _created = get_or_create_shop_category(
        slug=category_slug,
        name=category_name,
        sort_order=category_sort_order,
    )
    reg = LuantiRegisteredItem.objects.filter(item_name=item_name).first()
    label = (display_name or "").strip()
    if not label and reg and reg.description:
        label = reg.description[:128]
    stack = stack_size
    if stack is None:
        stack = default_stack_size_for_kind(reg.kind if reg else "item")

    existing = LuantiShopItem.objects.filter(category=cat, item_name=item_name).first()
    if existing:
        existing.buy_price_velos = price
        existing.enabled = True
        existing.save(update_fields=["buy_price_velos", "enabled"])
        if label:
            set_item_label(existing, DEFAULT_LANG, label, overwrite=False)
        return existing

    obj = LuantiShopItem.objects.create(
        category=cat,
        item_name=item_name,
        display_name=label,
        buy_price_velos=price,
        stack_size=max(1, int(stack)),
        enabled=True,
    )
    if label:
        set_item_label(obj, DEFAULT_LANG, label, overwrite=True)
    return obj


@dataclass
class BulkAddResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: list[str] = field(default_factory=list)


def add_registry_items_bulk_to_shop(
    *,
    item_names: list[str],
    category_slug: str,
    buy_price_velos: int,
    stack_size: int | None = None,
    require_in_registry: bool = True,
    category_name: str = "",
    category_sort_order: int = 999,
) -> BulkAddResult:
    """Add many registry itemstrings to one shop category (shared price)."""
    result = BulkAddResult()
    registry = registry_name_set() if require_in_registry else None
    price = max(1, int(buy_price_velos))
    cat, _created = get_or_create_shop_category(
        slug=category_slug,
        name=category_name,
        sort_order=category_sort_order,
    )
    seen: set[str] = set()
    pending: list[str] = []

    for raw in item_names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if ":" not in name:
            result.invalid.append(name)
            result.skipped += 1
            continue
        if registry is not None and name not in registry:
            result.invalid.append(name)
            result.skipped += 1
            continue
        pending.append(name)

    reg_map = _registry_row_map(pending)

    for name in pending:
        reg = reg_map.get(name)
        label = ""
        if reg and reg.description:
            label = reg.description[:128]
        stack = stack_size
        if stack is None:
            stack = default_stack_size_for_kind(reg.kind if reg else "item")
        stack = max(1, int(stack))

        existing = LuantiShopItem.objects.filter(category=cat, item_name=name).first()
        if existing:
            existing.buy_price_velos = price
            existing.enabled = True
            existing.save(update_fields=["buy_price_velos", "enabled"])
            if label:
                set_item_label(existing, DEFAULT_LANG, label, overwrite=False)
            result.updated += 1
            continue

        obj = LuantiShopItem.objects.create(
            category=cat,
            item_name=name,
            display_name=label,
            buy_price_velos=price,
            stack_size=stack,
            enabled=True,
        )
        if label:
            set_item_label(obj, DEFAULT_LANG, label, overwrite=True)
        result.created += 1
    return result
