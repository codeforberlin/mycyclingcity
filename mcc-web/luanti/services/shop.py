# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from api.models import Group
from config.logger_utils import get_logger
from luanti.models import (
    LuantiAccount,
    LuantiRegisteredItem,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
)
from luanti.services.shop_sell_resolve import resolve_shop_item_for_inventory_name

logger = get_logger("luanti")


class ShopError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _wallet_group_name(group: Group | None) -> str:
    return (group.name if group else "") or ""


def _active_shop_session(login_name: str):
    from luanti.models import LuantiSession
    from luanti.services.session_control import get_active_session

    session = get_active_session(login_name)
    if session is None:
        raise ShopError("no_session")
    if session.status == LuantiSession.STATUS_PAUSED:
        raise ShopError("session_paused")
    return session


def _assert_shop_real_session(session) -> None:
    if session.mode != LuantiAccount.MODE_BUILD:
        raise ShopError("shop_requires_build")


def _assert_shop_plan_session(session) -> None:
    if session.mode != LuantiAccount.MODE_PLAN:
        raise ShopError("shop_plan_requires_plan")


def _purchase_credit_holder_chain_full(wallet: Group) -> list[Group]:
    """Wallet first, then parents (ignores TOP sell restriction)."""
    chain: list[Group] = []
    seen: set[int] = set()
    current: Group | None = wallet
    while current is not None and current.pk not in seen:
        chain.append(current)
        seen.add(current.pk)
        parent_id = current.parent_id
        if not parent_id:
            break
        current = Group.objects.filter(pk=parent_id).first()
    return chain


def luanti_shop_sell_own_wallet_restricted(wallet: Group | None) -> bool:
    """True when a TOP ancestor restricts sell to own-wallet purchase credit only."""
    if wallet is None:
        return False
    current: Group | None = wallet
    seen: set[int] = set()
    while current is not None and current.pk not in seen:
        if current.luanti_shop_sell_own_wallet_credit_only:
            return True
        seen.add(current.pk)
        if not current.parent_id:
            break
        current = Group.objects.filter(pk=current.parent_id).first()
    return False


def purchase_credit_holder_chain(wallet: Group) -> list[Group]:
    """Wallet first, then parents unless TOP blocks pooled parent credit."""
    chain = _purchase_credit_holder_chain_full(wallet)
    if luanti_shop_sell_own_wallet_restricted(wallet):
        return chain[:1]
    return chain


def find_purchase_credit(
    *, wallet: Group, item_name: str
) -> tuple[LuantiShopPurchaseCredit | None, Group | None]:
    """First matching credit row along wallet → parent chain."""
    for holder in purchase_credit_holder_chain(wallet):
        credit = (
            LuantiShopPurchaseCredit.objects.select_for_update()
            .filter(group=holder, item_name=item_name)
            .first()
        )
        if credit is not None and int(credit.quantity or 0) > 0:
            return credit, holder
    return None, None


def foreign_purchase_credit_group(*, wallet: Group | None, shop_item_name: str) -> str:
    """Credit holder outside wallet chain (for sell tooltip when not sellable)."""
    if wallet is None or not (shop_item_name or "").strip():
        return ""
    chain_ids = {g.pk for g in purchase_credit_holder_chain(wallet)}
    row = (
        LuantiShopPurchaseCredit.objects.filter(item_name=shop_item_name, quantity__gt=0)
        .exclude(group_id__in=chain_ids)
        .select_related("group")
        .order_by("-quantity")
        .first()
    )
    return (row.group.name if row and row.group else "") or ""


def _parent_pool_locked_holder(
    *, wallet: Group | None, item_name: str
) -> Group | None:
    if wallet is None or not luanti_shop_sell_own_wallet_restricted(wallet):
        return None
    for holder in _purchase_credit_holder_chain_full(wallet)[1:]:
        row = (
            LuantiShopPurchaseCredit.objects.filter(
                group=holder, item_name=item_name, quantity__gt=0
            )
            .first()
        )
        if row is not None:
            return holder
    return None


def sell_hint_for_inventory_name(*, login_name: str, inventory_name: str) -> dict:
    wallet = resolve_group_for_player(login_name)
    wallet_name = (wallet.name if wallet else "") or ""
    item = resolve_shop_item_for_inventory_name(inventory_name, group=wallet)
    if item is None:
        return {
            "sellable": False,
            "reason": "not_in_shop",
            "wallet_group_name": wallet_name,
        }
    buy_price = int(item.buy_price_velos or 0)
    if wallet is None:
        return {
            "sellable": False,
            "reason": "no_credit",
            "wallet_group_name": wallet_name,
            "shop_item_name": item.item_name,
            "buy_price_velos": buy_price,
        }
    credit, holder = find_purchase_credit(wallet=wallet, item_name=item.item_name)
    if credit is not None and int(credit.quantity or 0) > 0:
        credit_name = (holder.name if holder else wallet_name) or wallet_name
        return {
            "sellable": True,
            "reason": "ok",
            "wallet_group_name": wallet_name,
            "credit_group_name": credit_name,
            "credit_available": int(credit.quantity),
            "shop_item_name": item.item_name,
            "buy_price_velos": buy_price,
        }
    pool_holder = _parent_pool_locked_holder(wallet=wallet, item_name=item.item_name)
    if pool_holder is not None:
        return {
            "sellable": False,
            "reason": "parent_pool_locked",
            "wallet_group_name": wallet_name,
            "credit_group_name": (pool_holder.name or "").strip() or str(pool_holder.pk),
            "shop_item_name": item.item_name,
            "buy_price_velos": buy_price,
        }
    foreign = foreign_purchase_credit_group(wallet=wallet, shop_item_name=item.item_name)
    reason = "other_group" if foreign else "no_credit"
    return {
        "sellable": False,
        "reason": reason,
        "wallet_group_name": wallet_name,
        "credit_group_name": foreign,
        "shop_item_name": item.item_name,
        "buy_price_velos": buy_price,
    }


def build_sell_hints(*, login_name: str, item_names: list) -> dict:
    hints: dict[str, dict] = {}
    seen: set[str] = set()
    for raw in item_names:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        hints[name] = sell_hint_for_inventory_name(login_name=login_name, inventory_name=name)
    wallet = resolve_group_for_player(login_name)
    return {
        "ok": True,
        "wallet_group_name": (wallet.name if wallet else "") or "",
        "hints": hints,
    }


def prune_empty_purchase_credit(credit: LuantiShopPurchaseCredit) -> None:
    """Remove credit rows with no remaining sell-back balance (audit stays in transactions)."""
    credit.refresh_from_db(fields=["quantity"])
    if int(credit.quantity or 0) <= 0:
        credit.delete()


def build_catalog_payload(*, lang: str | None = None) -> dict:
    from luanti.models import LuantiShopCategory
    from luanti.models import LuantiRegisteredItem
    from luanti.services.shop_labels import (
        build_item_search_blob,
        category_labels_map_for_categories,
        labels_map_for_items,
        normalize_language_code,
        normalize_shop_search_text,
        resolve_category_display_name,
        normalize_shop_search_text,
        resolve_item_display_name,
        resolve_search_labels,
    )

    lang_norm = normalize_language_code(lang)
    cat_qs = list(
        LuantiShopCategory.objects.filter(enabled=True).order_by("sort_order", "slug")
    )
    cat_label_maps = category_labels_map_for_categories([c.pk for c in cat_qs])
    all_item_names: list[str] = []
    for cat in cat_qs:
        for item_name in cat.items.filter(enabled=True).values_list("item_name", flat=True):
            all_item_names.append(item_name)
    registry_desc = {
        row.item_name: (row.description or "").strip()
        for row in LuantiRegisteredItem.objects.filter(item_name__in=all_item_names).only(
            "item_name", "description"
        )
    }
    categories = []
    for cat in cat_qs:
        item_qs = list(cat.items.filter(enabled=True).order_by("sort_order", "item_name"))
        label_maps = labels_map_for_items([it.pk for it in item_qs])
        cat_labels = cat_label_maps.get(cat.pk, {})
        cat_display = resolve_category_display_name(cat, lang_norm, labels=cat_labels)
        items = []
        for item in item_qs:
            item_labels = label_maps.get(item.pk, {})
            display_name = resolve_item_display_name(
                item, lang_norm, labels=item_labels
            )
            items.append(
                {
                    "id": item.pk,
                    "item_name": item.item_name,
                    "display_name": display_name,
                    "labels": resolve_search_labels(item, labels=item_labels),
                    "search": build_item_search_blob(
                        item,
                        labels=item_labels,
                        resolved_display_name=display_name,
                        category=cat,
                        category_labels=cat_labels,
                        registry_description=registry_desc.get(item.item_name, ""),
                    ),
                    "buy_price_velos": item.buy_price_velos,
                    "sell_price_velos": item.buy_price_velos,
                    "stack_size": item.stack_size,
                    "max_buy_quantity": effective_max_buy_quantity(item),
                }
            )
        categories.append(
            {
                "slug": cat.slug,
                "name": cat_display,
                "labels": cat_labels,
                "items": items,
            }
        )
    categories.sort(
        key=lambda c: (
            normalize_shop_search_text(c.get("name") or ""),
            (c.get("slug") or "").lower(),
        )
    )
    return {"ok": True, "categories": categories, "catalog_lang": lang_norm}


SHOP_QUANTITY_HARD_MAX = 64

_TOOL_NAME_MARKERS = (
    "_pick",
    "_axe",
    "_shovel",
    "_sword",
    "_hoe",
    "_shears",
    "_bow",
    "_shield",
    "_bucket",
    "_rod",
    "_flint_and_steel",
    "_trident",
    "_crossbow",
)


def max_buy_quantity(stack_size: int) -> int:
    """Cap from explicit stack_size field (max 64)."""
    return max(1, min(SHOP_QUANTITY_HARD_MAX, int(stack_size or 1)))


def effective_max_buy_quantity(item: LuantiShopItem) -> int:
    """Shop buy cap: stack_size when set >1; else 64 when the registry kind is node."""
    ss = int(item.stack_size or 1)
    if ss > 1:
        return max_buy_quantity(ss)
    name = (item.item_name or "").strip().lower()
    if not name:
        return 1
    if any(marker in name for marker in _TOOL_NAME_MARKERS):
        return 1
    reg = (
        LuantiRegisteredItem.objects.filter(item_name=item.item_name)
        .only("kind")
        .first()
    )
    if reg is not None and (reg.kind or "").strip() == "node":
        return SHOP_QUANTITY_HARD_MAX
    return max_buy_quantity(ss)


def physical_grant_count(quantity: int) -> int:
    """GUI/API ``quantity`` is the number of items to receive, not stack bundles."""
    return max(1, int(quantity))


def validate_shop_quantity(quantity: int, item: LuantiShopItem) -> int:
    quantity = physical_grant_count(quantity)
    if quantity > effective_max_buy_quantity(item):
        raise ShopError("quantity_exceeds_stack")
    return quantity


def resolve_group_for_player(login_name: str) -> Group | None:
    from luanti.services.session_control import get_active_session
    from luanti.services.wallet import resolve_wallet_group

    session = get_active_session(login_name)
    return resolve_wallet_group(None, session=session, login_name=login_name)


def parse_planning_flag(value) -> bool:
    """Treat JSON bool, 1, and common truthy strings as planning=true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _plan_item_meta(item: LuantiShopItem, *, lang: str = "de") -> dict:
    from luanti.services.shop_labels import normalize_language_code, resolve_item_display_name

    lang = normalize_language_code(lang)
    display_name = resolve_item_display_name(item, lang)
    return {
        "mcc_plan": "1",
        "mcc_shop_item_id": str(item.pk),
        "mcc_purchase_velos": "0",
        "mcc_buy_price_velos": str(item.buy_price_velos),
        "mcc_target_name": item.item_name,
        "mcc_shop_display_name": display_name[:128],
    }


def _log_shop_buy(
    *,
    login_name: str,
    item_id: int,
    item_name: str,
    quantity: int,
    planning: bool,
    side: str,
    velos_delta: int,
    idempotent: bool = False,
) -> None:
    logger.info(
        "[luanti] shop_buy player=%s item_id=%s item=%s qty=%s planning=%s side=%s velos_delta=%s idempotent=%s",
        login_name,
        item_id,
        item_name,
        quantity,
        planning,
        side,
        velos_delta,
        idempotent,
    )


def shop_buy(
    *,
    login_name: str,
    item_id: int,
    quantity: int,
    client_tx_id: str,
    planning: bool = False,
    lang: str = "de",
) -> dict:
    if not client_tx_id:
        raise ShopError("missing_client_tx_id")
    if LuantiShopTransaction.objects.filter(client_tx_id=client_tx_id).exists():
        tx = LuantiShopTransaction.objects.get(client_tx_id=client_tx_id)
        group = tx.group
        grant_entry = {
            "item_name": tx.item_name,
            "count": physical_grant_count(tx.quantity),
        }
        if tx.side == LuantiShopTransaction.SIDE_PLAN_BUY:
            item_ref = LuantiShopItem.objects.filter(item_name=tx.item_name).first()
            if item_ref:
                grant_entry["meta"] = _plan_item_meta(item_ref, lang=lang)
        _log_shop_buy(
            login_name=login_name,
            item_id=item_id,
            item_name=tx.item_name,
            quantity=tx.quantity,
            planning=planning,
            side=tx.side,
            velos_delta=int(tx.velos_delta),
            idempotent=True,
        )
        return {
            "ok": True,
            "idempotent": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
            "wallet_group_name": _wallet_group_name(group),
            "grant": [grant_entry],
        }
    item = LuantiShopItem.objects.select_related("category").filter(pk=item_id, enabled=True).first()
    if not item or not item.category.enabled:
        raise ShopError("item_not_found")
    quantity = validate_shop_quantity(quantity, item)
    session = _active_shop_session(login_name)
    if planning:
        _assert_shop_plan_session(session)
        group = resolve_group_for_player(login_name)
        LuantiShopTransaction.objects.create(
            client_tx_id=client_tx_id,
            side=LuantiShopTransaction.SIDE_PLAN_BUY,
            login_name=login_name,
            group=group,
            item_name=item.item_name,
            quantity=quantity,
            velos_delta=0,
        )
        _log_shop_buy(
            login_name=login_name,
            item_id=item_id,
            item_name=item.item_name,
            quantity=quantity,
            planning=True,
            side=LuantiShopTransaction.SIDE_PLAN_BUY,
            velos_delta=0,
        )
        return {
            "ok": True,
            "planning": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
            "wallet_group_name": _wallet_group_name(group),
            "grant": [
                {
                    "item_name": item.item_name,
                    "count": physical_grant_count(quantity),
                    "meta": _plan_item_meta(item, lang=lang),
                }
            ],
        }

    _assert_shop_real_session(session)
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
    _log_shop_buy(
        login_name=login_name,
        item_id=item_id,
        item_name=item.item_name,
        quantity=quantity,
        planning=False,
        side=LuantiShopTransaction.SIDE_BUY,
        velos_delta=-cost,
    )
    return {
        "ok": True,
        "velos_spendable": int(group.velos_spendable),
        "wallet_group_name": _wallet_group_name(group),
        "grant": [{"item_name": item.item_name, "count": physical_grant_count(quantity)}],
    }


@transaction.atomic
def shop_sell(
    *,
    login_name: str,
    item_name: str = "",
    item_id: int | None = None,
    quantity: int,
    client_tx_id: str,
    require_active_build_session: bool = True,
) -> dict:
    if LuantiShopTransaction.objects.filter(client_tx_id=client_tx_id).exists():
        tx = LuantiShopTransaction.objects.get(client_tx_id=client_tx_id)
        group = tx.group
        return {
            "ok": True,
            "idempotent": True,
            "velos_spendable": int(group.velos_spendable) if group else 0,
            "wallet_group_name": _wallet_group_name(group),
            "refunded": int(tx.velos_delta),
            "take": [{"item_name": tx.item_name, "count": tx.quantity}],
        }
    if require_active_build_session:
        session = _active_shop_session(login_name)
        _assert_shop_real_session(session)
    item = None
    if item_id is not None:
        item = (
            LuantiShopItem.objects.select_related("category")
            .filter(pk=int(item_id), enabled=True)
            .first()
        )
        if item and not item.category.enabled:
            item = None
    group = resolve_group_for_player(login_name)
    if group is None:
        raise ShopError("no_group")
    group = Group.objects.select_for_update().get(pk=group.pk)
    if item is None and item_name:
        item = resolve_shop_item_for_inventory_name(item_name, group=group)
    if not item:
        raise ShopError("item_not_found")
    quantity = validate_shop_quantity(quantity, item)
    credit, _credit_holder = find_purchase_credit(wallet=group, item_name=item.item_name)
    if credit is None or int(credit.quantity or 0) < quantity:
        raise ShopError("insufficient_credit")
    credit.quantity = F("quantity") - quantity
    credit.save(update_fields=["quantity"])
    prune_empty_purchase_credit(credit)
    refund = item.buy_price_velos * quantity
    group.velos_spendable = F("velos_spendable") + refund
    group.save(update_fields=["velos_spendable"])
    group.refresh_from_db(fields=["velos_spendable"])
    take_count = physical_grant_count(quantity)
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
        "wallet_group_name": _wallet_group_name(group),
        "refunded": refund,
        "take": [{"item_name": item.item_name, "count": take_count}],
    }


@transaction.atomic
def shop_sell_batch(
    *,
    login_name: str,
    items: list,
    client_tx_id: str,
    require_active_build_session: bool = True,
) -> dict:
    """Sell multiple stacks; consume purchase credit partially per item.

    ``items`` entries: ``{"item_name": str, "quantity": int}`` — physical item count.
    Purchase credit is stored in the same physical units as shop buy ``quantity``.
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
            "wallet_group_name": _wallet_group_name(group),
            "refunded_total": sum(c["refunded"] for c in consumed),
            "consumed": consumed,
            "rejected": [],
        }

    if require_active_build_session:
        session = _active_shop_session(login_name)
        _assert_shop_real_session(session)
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
        item = resolve_shop_item_for_inventory_name(item_name, group=group)
        if not item:
            rejected.append(
                {"item_name": item_name, "quantity": physical_qty, "reason": "item_not_found"}
            )
            continue
        credit, _credit_holder = find_purchase_credit(wallet=group, item_name=item.item_name)
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
        physical_take = min(physical_qty, available)

        credit.quantity = F("quantity") - physical_take
        credit.save(update_fields=["quantity"])
        prune_empty_purchase_credit(credit)
        refund = item.buy_price_velos * physical_take
        group.velos_spendable = F("velos_spendable") + refund
        group.save(update_fields=["velos_spendable"])
        group.refresh_from_db(fields=["velos_spendable"])
        LuantiShopTransaction.objects.create(
            client_tx_id=f"{prefix}{line}",
            side=LuantiShopTransaction.SIDE_SELL,
            login_name=login_name,
            group=group,
            item_name=item.item_name,
            quantity=physical_take,
            velos_delta=refund,
        )
        line += 1
        refunded_total += refund
        consumed.append(
            {
                "item_name": item.item_name,
                "quantity": physical_take,
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
            "wallet_group_name": _wallet_group_name(group),
            "refunded_total": 0,
            "consumed": [],
            "rejected": rejected,
        }

    group.refresh_from_db(fields=["velos_spendable"])
    return {
        "ok": True,
        "velos_spendable": int(group.velos_spendable),
        "wallet_group_name": _wallet_group_name(group),
        "refunded_total": refunded_total,
        "consumed": consumed,
        "rejected": rejected,
    }
