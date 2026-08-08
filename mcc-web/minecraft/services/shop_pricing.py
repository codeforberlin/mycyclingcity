# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    shop_pricing.py
# @note    Find and fix shop items without a positive Velos price.

from __future__ import annotations

from django.db.models import QuerySet

from minecraft.models import MinecraftShopItem

DEFAULT_MINIMUM_VELOS = 1


def zero_price_items_queryset() -> QuerySet[MinecraftShopItem]:
    """All shop items priced at 0 Velos (any enabled state)."""
    return (
        MinecraftShopItem.objects.filter(buy_price_velos=0)
        .select_related("category")
        .order_by("category__sort_order", "category__name", "sort_order", "material")
    )


def count_zero_price_items() -> int:
    return MinecraftShopItem.objects.filter(buy_price_velos=0).count()


def assign_minimum_velos(
    *,
    minimum: int = DEFAULT_MINIMUM_VELOS,
) -> int:
    """
    Set buy_price_velos to *minimum* for every item currently below that value.

    Returns the number of updated rows. Intended for Admin: no free (0 Velos) items.
    """
    min_price = max(1, int(minimum))
    return MinecraftShopItem.objects.filter(buy_price_velos__lt=min_price).update(
        buy_price_velos=min_price
    )
