# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from api.models import Group
from luanti.models import (
    LuantiShopItem,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
)


class ShopError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def build_catalog_payload() -> dict:
    from luanti.models import LuantiShopCategory

    categories = []
    for cat in LuantiShopCategory.objects.filter(enabled=True).order_by("sort_order", "slug"):
        items = []
        for item in cat.items.filter(enabled=True).order_by("sort_order", "item_name"):
            items.append(
                {
                    "id": item.pk,
                    "item_name": item.item_name,
                    "display_name": item.display_name or item.item_name,
                    "buy_price_velos": item.buy_price_velos,
                    "sell_price_velos": item.buy_price_velos,
                    "stack_size": item.stack_size,
                }
            )
        categories.append(
            {
                "slug": cat.slug,
                "name": cat.name,
                "items": items,
            }
        )
    return {"ok": True, "categories": categories}


def resolve_group_for_player(login_name: str) -> Group | None:
    from luanti.services.session_control import get_active_session
    from luanti.services.wallet import resolve_wallet_group

    session = get_active_session(login_name)
    return resolve_wallet_group(None, session=session, login_name=login_name)

@transaction.atomic
def shop_buy(
    *,
    login_name: str,
    item_id: int,
    quantity: int,
    client_tx_id: str,
) -> dict:
    if not client_tx_id:
        raise ShopError("missing_client_tx_id")
    if LuantiShopTransaction.objects.filter(client_tx_id=client_tx_id).exists():
        tx = LuantiShopTransaction.objects.get(client_tx_id=client_tx_id)
        group = tx.group
        return {
            "ok": True,
            "idempotent": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
            "grant": [{"item_name": tx.item_name, "count": tx.quantity}],
        }
    quantity = max(1, int(quantity))
    item = LuantiShopItem.objects.select_related("category").filter(pk=item_id, enabled=True).first()
    if not item or not item.category.enabled:
        raise ShopError("item_not_found")
    from luanti.services.session_control import get_active_session

    session = get_active_session(login_name)
    if session and session.is_paused:
        raise ShopError("session_paused")
    group = resolve_group_for_player(login_name)
    if group is None:
        raise ShopError("no_group")
    cost = item.buy_price_velos * quantity
    group = Group.objects.select_for_update().get(pk=group.pk)
    if group.velos_spendable < cost:
        raise ShopError("insufficient_velos")
    group.velos_spendable = F("velos_spendable") - cost
    group.save(update_fields=["velos_spendable"])
    group.refresh_from_db(fields=["velos_spendable"])
    credit, _ = LuantiShopPurchaseCredit.objects.select_for_update().get_or_create(
        group=group,
        item_name=item.item_name,
        defaults={"quantity": 0},
    )
    credit.quantity = F("quantity") + quantity
    credit.save(update_fields=["quantity"])
    LuantiShopTransaction.objects.create(
        client_tx_id=client_tx_id,
        side=LuantiShopTransaction.SIDE_BUY,
        login_name=login_name,
        group=group,
        item_name=item.item_name,
        quantity=quantity,
        velos_delta=-cost,
    )
    return {
        "ok": True,
        "velos_spendable": int(group.velos_spendable),
        "grant": [{"item_name": item.item_name, "count": quantity * item.stack_size}],
    }


@transaction.atomic
def shop_sell(
    *,
    login_name: str,
    item_name: str,
    quantity: int,
    client_tx_id: str,
) -> dict:
    if LuantiShopTransaction.objects.filter(client_tx_id=client_tx_id).exists():
        tx = LuantiShopTransaction.objects.get(client_tx_id=client_tx_id)
        group = tx.group
        return {
            "ok": True,
            "idempotent": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
        }
    quantity = max(1, int(quantity))
    item = (
        LuantiShopItem.objects.filter(item_name=item_name, enabled=True, category__enabled=True)
        .order_by("id")
        .first()
    )
    if not item:
        raise ShopError("item_not_found")
    group = resolve_group_for_player(login_name)
    if group is None:
        raise ShopError("no_group")
    group = Group.objects.select_for_update().get(pk=group.pk)
    credit = (
        LuantiShopPurchaseCredit.objects.select_for_update()
        .filter(group=group, item_name=item.item_name)
        .first()
    )
    if not credit or credit.quantity < quantity:
        raise ShopError("insufficient_credit")
    credit.quantity = F("quantity") - quantity
    credit.save(update_fields=["quantity"])
    refund = item.buy_price_velos * quantity
    group.velos_spendable = F("velos_spendable") + refund
    group.save(update_fields=["velos_spendable"])
    group.refresh_from_db(fields=["velos_spendable"])
    LuantiShopTransaction.objects.create(
        client_tx_id=client_tx_id,
        side=LuantiShopTransaction.SIDE_SELL,
        login_name=login_name,
        group=group,
        item_name=item.item_name,
        quantity=quantity,
        velos_delta=refund,
    )
    return {"ok": True, "velos_spendable": int(group.velos_spendable), "refunded": refund}
