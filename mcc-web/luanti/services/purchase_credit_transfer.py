# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Move Luanti shop purchase credit between groups (admin).

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from api.models import Group
from luanti.models import LuantiShopPurchaseCredit


class PurchaseCreditTransferError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass
class PurchaseCreditTransferResult:
    transferred_rows: int = 0
    total_quantity: int = 0
    merged_items: int = 0
    skipped_same_group: int = 0
    source_groups: int = 0


@transaction.atomic
def transfer_purchase_credits_to_group(
    *,
    target_group: Group,
    credit_ids: list[int],
) -> PurchaseCreditTransferResult:
    """Merge selected credit rows into target_group (sum quantities per item_name)."""
    if not credit_ids:
        return PurchaseCreditTransferResult()
    if target_group is None:
        raise PurchaseCreditTransferError("no_target_group")

    result = PurchaseCreditTransferResult()
    qs = (
        LuantiShopPurchaseCredit.objects.select_for_update()
        .filter(pk__in=credit_ids, quantity__gt=0)
        .select_related("group")
        .order_by("group_id", "item_name")
    )
    source_group_ids: set[int] = set()
    for credit in qs:
        if credit.group_id == target_group.pk:
            result.skipped_same_group += 1
            continue
        source_group_ids.add(credit.group_id)
        qty = int(credit.quantity or 0)
        if qty <= 0:
            continue
        dest, _ = LuantiShopPurchaseCredit.objects.select_for_update().get_or_create(
            group=target_group,
            item_name=credit.item_name,
            defaults={"quantity": 0},
        )
        LuantiShopPurchaseCredit.objects.filter(pk=dest.pk).update(
            quantity=F("quantity") + qty
        )
        credit.delete()
        result.transferred_rows += 1
        result.total_quantity += qty
        result.merged_items += 1

    result.source_groups = len(source_group_ids)
    return result


@transaction.atomic
def transfer_all_credits_from_groups(
    *,
    target_group: Group,
    source_group_ids: list[int],
) -> PurchaseCreditTransferResult:
    """Move every purchase-credit row from the given source groups."""
    if not source_group_ids:
        return PurchaseCreditTransferResult()
    ids = list(
        LuantiShopPurchaseCredit.objects.filter(
            group_id__in=source_group_ids,
            quantity__gt=0,
        ).values_list("pk", flat=True)
    )
    out = transfer_purchase_credits_to_group(
        target_group=target_group,
        credit_ids=ids,
    )
    out.source_groups = len(set(source_group_ids))
    return out