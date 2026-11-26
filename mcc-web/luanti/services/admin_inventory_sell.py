# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import time
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils.translation import gettext as _

from luanti.models import LuantiAccount, LuantiPlayerInventory
from luanti.services.inventory_admin import (
    MAX_STACK_COUNT,
    inventory_rows_for_display,
)
from luanti.services.shop import ShopError, sell_hint_for_inventory_name, shop_sell


class AdminInventorySellError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


SELL_ERROR_MESSAGES = {
    "wrong_mode": _("Verkauf ist nur im Bau-Inventar möglich."),
    "nothing_selected": _("Keine Stacks zum Verkauf ausgewählt."),
    "confirm_required": _("Bitte den Verkauf bestätigen."),
}


def _row_by_slot(payload: list | None, slot: int) -> dict | None:
    if not isinstance(payload, list):
        return None
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            row_slot = int(row.get("slot") or 0)
        except (TypeError, ValueError):
            continue
        if row_slot == slot and (row.get("name") or "").strip():
            return row
    return None


def _is_plan_row(row: dict) -> bool:
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    return str(meta.get("mcc_plan") or "") == "1"


def expected_velos_for_row(
    *, login_name: str, item_name: str, quantity: int
) -> tuple[int, dict]:
    hint = sell_hint_for_inventory_name(login_name=login_name, inventory_name=item_name)
    if not hint.get("sellable"):
        return 0, hint
    price = int(hint.get("buy_price_velos") or 0)
    qty = max(0, min(int(quantity), int(hint.get("credit_available") or 0)))
    return price * qty, hint


def sell_preview_rows(account: LuantiAccount, payload: list | None) -> list[dict[str, Any]]:
    login = account.login_name
    out: list[dict[str, Any]] = []
    for row in inventory_rows_for_display(payload):
        hint = sell_hint_for_inventory_name(login_name=login, inventory_name=row["name"])
        velos, _ = expected_velos_for_row(
            login_name=login, item_name=row["name"], quantity=row["count"]
        )
        out.append(
            {
                **row,
                "sell_hint": hint,
                "expected_velos_full": velos,
                "shop_label_key": hint,
            }
        )
    return out


def parse_sell_post(post) -> list[tuple[int, int]]:
    """Return (slot, quantity) for rows with sell checkbox set."""
    indices: set[int] = set()
    for key in post:
        if key.startswith("row-") and key.endswith("-sell"):
            mid = key[4:-5]
            try:
                indices.add(int(mid))
            except ValueError:
                continue
    selections: list[tuple[int, int]] = []
    for idx in sorted(indices):
        if post.get(f"row-{idx}-sell") not in ("on", "1", "true", True):
            continue
        try:
            slot = int(post.get(f"row-{idx}-slot") or 0)
        except (TypeError, ValueError):
            continue
        if slot < 1 or slot > 64:
            continue
        try:
            qty = int(post.get(f"row-{idx}-sell-qty") or post.get(f"row-{idx}-count") or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty < 1 or qty > MAX_STACK_COUNT:
            continue
        selections.append((slot, qty))
    return selections


def _apply_slot_reduction(payload: list, slot: int, take: int) -> list:
    out: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            row_slot = int(row.get("slot") or 0)
        except (TypeError, ValueError):
            row_slot = 0
        name = str(row.get("name") or "").strip()
        if row_slot == slot and name and take > 0:
            try:
                count = int(row.get("count") or 1)
            except (TypeError, ValueError):
                count = 1
            new_count = count - take
            if new_count > 0:
                entry = dict(row)
                entry["count"] = new_count
                out.append(entry)
            continue
        if name:
            out.append(dict(row))
    return out


def _rejection_reason_label(reason: str, hint: dict | None = None) -> str:
    hint = hint or {}
    if reason == "plan_item":
        return str(_("Plan-Item (nicht verkaufbar)"))
    if reason == "invalid_slot":
        return str(_("Slot nicht im Inventar"))
    if reason == "quantity_exceeds_stack":
        return str(_("Menge größer als Stack"))
    if reason == "not_sellable":
        if hint.get("reason") == "parent_pool_locked":
            return str(_("Kaufguthaben liegt bei übergeordneter Gruppe (TOP-Sperre)"))
        if hint.get("reason") == "other_group":
            return str(_("Kaufguthaben bei anderer Gruppe als Wallet"))
        if hint.get("reason") == "not_in_shop":
            return str(_("Kein Shop-Artikel"))
        return str(_("Nicht verkaufbar"))
    if reason.startswith("shop:"):
        code = reason[5:]
        if code == "insufficient_credit":
            return str(_("Unzureichendes Kaufguthaben"))
        if code == "item_not_found":
            return str(_("Shop-Artikel nicht gefunden"))
        return code
    return reason or "?"


@transaction.atomic
def admin_sell_inventory_slots(
    *,
    inv: LuantiPlayerInventory,
    selections: list[tuple[int, int]],
    operator_user: AbstractBaseUser | None,
) -> dict[str, Any]:
    if inv.mode != LuantiAccount.MODE_BUILD:
        raise AdminInventorySellError("wrong_mode")
    if not selections:
        raise AdminInventorySellError("nothing_selected")

    account = inv.account
    login_name = account.login_name
    operator_id = int(getattr(operator_user, "pk", 0) or 0)
    tx_base = f"admin-inv-sell-{operator_id}-{time.time_ns()}"

    consumed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    refunded_total = 0
    velos_spendable = 0
    wallet_group_name = ""

    payload = list(inv.payload) if isinstance(inv.payload, list) else []

    for line, (slot, quantity) in enumerate(selections):
        row = _row_by_slot(payload, slot)
        if row is None:
            rejected.append(
                {
                    "slot": slot,
                    "quantity": quantity,
                    "reason": "invalid_slot",
                    "label": _rejection_reason_label("invalid_slot"),
                }
            )
            continue
        if _is_plan_row(row):
            rejected.append(
                {
                    "slot": slot,
                    "item_name": row.get("name"),
                    "quantity": quantity,
                    "reason": "plan_item",
                    "label": _rejection_reason_label("plan_item"),
                }
            )
            continue
        item_name = str(row.get("name") or "").strip()
        try:
            stack_count = int(row.get("count") or 1)
        except (TypeError, ValueError):
            stack_count = 1
        if quantity > stack_count:
            rejected.append(
                {
                    "slot": slot,
                    "item_name": item_name,
                    "quantity": quantity,
                    "reason": "quantity_exceeds_stack",
                    "label": _rejection_reason_label("quantity_exceeds_stack"),
                }
            )
            continue
        hint = sell_hint_for_inventory_name(login_name=login_name, inventory_name=item_name)
        if not hint.get("sellable"):
            rejected.append(
                {
                    "slot": slot,
                    "item_name": item_name,
                    "quantity": quantity,
                    "reason": "not_sellable",
                    "label": _rejection_reason_label("not_sellable", hint),
                }
            )
            continue
        try:
            result = shop_sell(
                login_name=login_name,
                item_name=item_name,
                quantity=quantity,
                client_tx_id=f"{tx_base}#slot-{slot}-line-{line}",
                require_active_build_session=False,
            )
        except ShopError as exc:
            rejected.append(
                {
                    "slot": slot,
                    "item_name": item_name,
                    "quantity": quantity,
                    "reason": f"shop:{exc.code}",
                    "label": _rejection_reason_label(f"shop:{exc.code}", hint),
                }
            )
            continue

        take = int(result.get("take", [{}])[0].get("count") or quantity)
        payload = _apply_slot_reduction(payload, slot, take)
        refund = int(result.get("refunded") or 0)
        refunded_total += refund
        velos_spendable = int(result.get("velos_spendable") or 0)
        wallet_group_name = str(result.get("wallet_group_name") or wallet_group_name)
        consumed.append(
            {
                "slot": slot,
                "item_name": item_name,
                "quantity": take,
                "refunded": refund,
            }
        )

    if consumed:
        inv.payload = payload
        inv.revision = int(inv.revision or 0) + 1
        inv.save(update_fields=["payload", "revision", "updated_at"])

    from luanti.services.session_control import push_account_inventory

    pushed = push_account_inventory(inv) if consumed else False

    return {
        "consumed": consumed,
        "rejected": rejected,
        "refunded_total": refunded_total,
        "velos_spendable": velos_spendable,
        "wallet_group_name": wallet_group_name,
        "pushed": pushed,
        "inv": inv,
    }