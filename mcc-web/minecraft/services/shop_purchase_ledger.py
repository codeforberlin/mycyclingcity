# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Team shop purchase ledger: track sellable quantities for bought materials.

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from api.models import Group
from config.logger_utils import get_logger
from minecraft.models import MinecraftShopPurchaseCredit
from minecraft.services.outbox import queue_team_velos_update
from minecraft.services.team_registration import get_active_registration_by_mc_username


logger = get_logger("minecraft")


def _normalize_material(material: str | None) -> str | None:
    if material is None:
        return None
    normalized = str(material).strip().upper().replace("-", "_")
    if normalized.startswith("MINECRAFT:"):
        normalized = normalized[len("MINECRAFT:") :]
    return normalized or None


def _parse_positive_qty(qty) -> int | None:
    try:
        value = int(qty)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


@transaction.atomic
def record_purchase(mc_username: str, material: str, qty: int) -> str:
    """
    Add purchased quantity to the team's sell credit for *material*.

    Returns: ok | group_not_found | invalid_payload
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return "group_not_found"

    normalized = _normalize_material(material)
    amount = _parse_positive_qty(qty)
    if not normalized or amount is None:
        return "invalid_payload"

    group = registration.group
    credit, created = MinecraftShopPurchaseCredit.objects.select_for_update().get_or_create(
        group_id=group.pk,
        material=normalized,
        defaults={"quantity": 0},
    )
    if created:
        credit.quantity = amount
        credit.save(update_fields=["quantity"])
    else:
        MinecraftShopPurchaseCredit.objects.filter(pk=credit.pk).update(
            quantity=F("quantity") + amount
        )

    logger.info(
        "[shop_ledger] purchase mc=%s material=%s qty=%s group=%s",
        mc_username,
        normalized,
        amount,
        group.name,
    )
    return "ok"


@transaction.atomic
def consume_for_sell(mc_username: str, material: str, qty: int) -> str:
    """
    Atomically consume sell credit. Fails if remaining quantity is too low.

    Returns: ok | group_not_found | invalid_payload | insufficient_credit
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return "group_not_found"

    normalized = _normalize_material(material)
    amount = _parse_positive_qty(qty)
    if not normalized or amount is None:
        return "invalid_payload"

    credit = (
        MinecraftShopPurchaseCredit.objects.select_for_update()
        .filter(group_id=registration.group_id, material=normalized)
        .first()
    )
    remaining = int(credit.quantity) if credit else 0
    if remaining < amount:
        return "insufficient_credit"

    MinecraftShopPurchaseCredit.objects.filter(pk=credit.pk).update(
        quantity=remaining - amount
    )
    logger.info(
        "[shop_ledger] sell consume mc=%s material=%s qty=%s remaining=%s",
        mc_username,
        normalized,
        amount,
        remaining - amount,
    )
    return "ok"


@transaction.atomic
def consume_for_sell_batch(
    mc_username: str,
    items: list[dict],
    *,
    partial: bool = False,
) -> tuple[str, list[dict]]:
    """
    Atomically consume credits for multiple materials.

    Each item: {"material": str, "amount": int}

    When *partial* is False (default): all-or-nothing.
    When *partial* is True: consume min(requested, available) per material;
    materials with 0 credit are skipped.

    Returns: (status, consumed) where consumed is [{"material", "amount"}, ...]
    status: ok | group_not_found | invalid_payload | insufficient_credit
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return "group_not_found", []

    if not items:
        return "invalid_payload", []

    totals: dict[str, int] = {}
    for entry in items:
        if not isinstance(entry, dict):
            return "invalid_payload", []
        material = _normalize_material(entry.get("material"))
        amount = _parse_positive_qty(entry.get("amount"))
        if not material or amount is None:
            return "invalid_payload", []
        totals[material] = totals.get(material, 0) + amount

    normalized_items = list(totals.items())
    credits = {
        row.material: row
        for row in MinecraftShopPurchaseCredit.objects.select_for_update().filter(
            group_id=registration.group_id,
            material__in=[m for m, _ in normalized_items],
        )
    }

    planned: list[tuple[str, int]] = []
    for material, amount in normalized_items:
        remaining = int(credits[material].quantity) if material in credits else 0
        if partial:
            take = min(amount, remaining)
            if take > 0:
                planned.append((material, take))
        else:
            if remaining < amount:
                return "insufficient_credit", []
            planned.append((material, amount))

    if not planned:
        # Partial with nothing affordable is still ok (caller clears the sell).
        return ("ok" if partial else "insufficient_credit"), []

    consumed: list[dict] = []
    for material, amount in planned:
        credit = credits[material]
        MinecraftShopPurchaseCredit.objects.filter(pk=credit.pk).update(
            quantity=int(credit.quantity) - amount
        )
        # Refresh local quantity for subsequent same-material rows (already merged).
        credit.quantity = int(credit.quantity) - amount
        consumed.append({"material": material, "amount": amount})

    logger.info(
        "[shop_ledger] sell consume batch mc=%s partial=%s items=%s",
        mc_username,
        partial,
        planned,
    )
    return "ok", consumed


@transaction.atomic
def credit_group_velos_from_minecraft(mc_username: str, amount: int) -> str:
    """
    Add spendable Velos for a leaf group identified by Minecraft username.

    Returns: ok | group_not_found | invalid_amount
    """
    registration = get_active_registration_by_mc_username(mc_username)
    if not registration:
        return "group_not_found"

    group = (
        Group.objects.select_for_update()
        .filter(pk=registration.group_id)
        .first()
    )
    if not group:
        return "group_not_found"

    try:
        credit_amount = int(amount)
    except (TypeError, ValueError):
        return "invalid_amount"
    if credit_amount <= 0:
        return "invalid_amount"

    new_spendable = int(group.velos_spendable or 0) + credit_amount
    Group.objects.filter(pk=group.pk).update(velos_spendable=new_spendable)
    group.refresh_from_db(fields=["velos_total", "velos_spendable", "mc_username"])

    if registration.is_active:
        queue_team_velos_update(
            player=registration.mc_username,
            velos_spendable=int(group.velos_spendable or 0),
            reason="minecraft_sell",
            spendable_action="set",
        )

    logger.info(
        "[minecraft_group_velos] credited %s Velos for mc=%s (group=%s), new_spendable=%s",
        credit_amount,
        mc_username,
        group.name,
        group.velos_spendable,
    )
    return "ok"
