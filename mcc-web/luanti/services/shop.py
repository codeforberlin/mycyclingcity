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
    item_name: str = "",
    item_id: int | None = None,
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
            "refunded": int(tx.velos_delta),
            "take": [{"item_name": tx.item_name, "count": tx.quantity}],
        }
    quantity = max(1, int(quantity))
    from luanti.services.session_control import get_active_session

    session = get_active_session(login_name)
    if session and session.is_paused:
        raise ShopError("session_paused")
    item = None
    if item_id is not None:
        item = (
            LuantiShopItem.objects.select_related("category")
            .filter(pk=int(item_id), enabled=True)
            .first()
        )
        if item and not item.category.enabled:
            item = None
    elif item_name:
        item = (
            LuantiShopItem.objects.filter(
                item_name=item_name, enabled=True, category__enabled=True
            )
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
    take_count = quantity * max(1, int(item.stack_size or 1))
    LuantiShopTransaction.objects.create(
        client_tx_id=client_tx_id,
        side=LuantiShopTransaction.SIDE_SELL,
        login_name=login_name,
        group=group,
        item_name=item.item_name,
        quantity=quantity,
        velos_delta=refund,
    )
    return {
        "ok": True,
        "velos_spendable": int(group.velos_spendable),
        "refunded": refund,
        "take": [{"item_name": item.item_name, "count": take_count}],
    }


@transaction.atomic
def shop_sell_batch(
    *,
    login_name: str,
    items: list,
    client_tx_id: str,
) -> dict:
    """Sell multiple stacks; consume purchase credit partially per item.

    ``items`` entries: ``{"item_name": str, "quantity": int}`` where quantity is
    physical item count (stack units). Credit is in shop units (buy quantity);
    physical take = shop_qty * stack_size.
    """
    if not client_tx_id:
        raise ShopError("missing_client_tx_id")
    prefix = client_tx_id + "#"
    prior = list(
        LuantiShopTransaction.objects.filter(client_tx_id__startswith=prefix).order_by("id")
    )
    if prior:
        group = prior[0].group
        consumed = [
            {
                "item_name": tx.item_name,
                "quantity": tx.quantity,
                "refunded": int(tx.velos_delta),
            }
            for tx in prior
            if tx.side == LuantiShopTransaction.SIDE_SELL
        ]
        return {
            "ok": True,
            "idempotent": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
            "refunded_total": sum(c["refunded"] for c in consumed),
            "consumed": consumed,
            "rejected": [],
        }

    from luanti.services.session_control import get_active_session

    session = get_active_session(login_name)
    if not session:
        raise ShopError("no_session")
    if session.is_paused:
        raise ShopError("session_paused")
    group = resolve_group_for_player(login_name)
    if group is None:
        raise ShopError("no_group")
    group = Group.objects.select_for_update().get(pk=group.pk)

    if not isinstance(items, list) or not items:
        raise ShopError("invalid_items")

    # Merge duplicate item_names
    merged: dict[str, int] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("item_name") or "").strip()
        try:
            qty = max(0, int(raw.get("quantity") or 0))
        except (TypeError, ValueError):
            qty = 0
        if not name or qty <= 0:
            continue
        merged[name] = merged.get(name, 0) + qty

    consumed: list[dict] = []
    rejected: list[dict] = []
    refunded_total = 0
    line = 0

    for item_name, physical_qty in merged.items():
        item = (
            LuantiShopItem.objects.filter(
                item_name=item_name, enabled=True, category__enabled=True
            )
            .order_by("id")
            .first()
        )
        if not item:
            rejected.append(
                {"item_name": item_name, "quantity": physical_qty, "reason": "item_not_found"}
            )
            continue
        stack = max(1, int(item.stack_size or 1))
        # Shop credit units (ceil): one buy qty grants ``stack`` physical items.
        shop_want = (physical_qty + stack - 1) // stack
        credit = (
            LuantiShopPurchaseCredit.objects.select_for_update()
            .filter(group=group, item_name=item.item_name)
            .first()
        )
        available = int(credit.quantity) if credit else 0
        if available <= 0:
            rejected.append(
                {
                    "item_name": item_name,
                    "quantity": physical_qty,
                    "reason": "insufficient_credit",
                }
            )
            continue
        shop_take = min(available, shop_want)
        physical_take = min(physical_qty, shop_take * stack)

        credit.quantity = F("quantity") - shop_take
        credit.save(update_fields=["quantity"])
        refund = item.buy_price_velos * shop_take
        group.velos_spendable = F("velos_spendable") + refund
        group.save(update_fields=["velos_spendable"])
        group.refresh_from_db(fields=["velos_spendable"])
        LuantiShopTransaction.objects.create(
            client_tx_id=f"{prefix}{line}",
            side=LuantiShopTransaction.SIDE_SELL,
            login_name=login_name,
            group=group,
            item_name=item.item_name,
            quantity=shop_take,
            velos_delta=refund,
        )
        line += 1
        refunded_total += refund
        consumed.append(
            {
                "item_name": item.item_name,
                "quantity": shop_take,
                "physical_count": physical_take,
                "refunded": refund,
            }
        )
        leftover_phys = physical_qty - physical_take
        if leftover_phys > 0:
            rejected.append(
                {
                    "item_name": item_name,
                    "quantity": leftover_phys,
                    "reason": "insufficient_credit",
                }
            )

    if line == 0 and not consumed:
        # No marker txs — still ok response with only rejects (SellGUI style).
        group.refresh_from_db(fields=["velos_spendable"])
        return {
            "ok": True,
            "velos_spendable": int(group.velos_spendable),
            "refunded_total": 0,
            "consumed": [],
            "rejected": rejected,
        }

    group.refresh_from_db(fields=["velos_spendable"])
    return {
        "ok": True,
        "velos_spendable": int(group.velos_spendable),
        "refunded_total": refunded_total,
        "consumed": consumed,
        "rejected": rejected,
    }
