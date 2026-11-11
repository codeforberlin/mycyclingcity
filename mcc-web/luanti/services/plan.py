# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    plan.py
# @note    Hologram planning ledger, funding pools, and materialization.

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from api.models import Group
from luanti.services.region_ops import default_world
from config.logger_utils import get_logger
from luanti.models import (
    LuantiAccount,
    LuantiPlanBlock,
    LuantiPlanMaterializeTransaction,
    LuantiProtectedRegion,
    LuantiRegionPlanFunding,
    LuantiShopPurchaseCredit,
)

logger = get_logger(__name__)


class PlanError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def plan_world_names(world: str | None) -> list[str]:
    """Match regions when Lua sends legacy ``world`` but DB uses MCC_LUANTI_WORLD."""
    raw = (world or "world").strip() or "world"
    names = [raw]
    canonical = default_world()
    if raw == "world" and canonical not in names:
        names.append(canonical)
    elif raw == canonical and "world" not in names:
        names.append("world")
    return names


def resolve_build_region_at(
    *,
    world: str,
    x: int,
    y: int,
    z: int,
) -> LuantiProtectedRegion | None:
    """Prefer smallest enabled protect_build subregion containing the point."""
    candidates: list[tuple[int, int, LuantiProtectedRegion]] = []
    qs = (
        LuantiProtectedRegion.objects.filter(
            enabled=True, protect_build=True, world__in=plan_world_names(world)
        )
        .select_related("parent", "assigned_to_group", "parent__assigned_to_group")
        .order_by("sort_order", "region_id")
    )
    for region in qs:
        if region.contains_point(int(x), int(y), int(z)):
            vol = 1
            mn = region.normalized_bounds()
            vol = (mn[3] - mn[0] + 1) * (mn[4] - mn[1] + 1) * (mn[5] - mn[2] + 1)
            depth = 1 if region.parent_id else 0
            candidates.append((depth, vol, region))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[0], t[1]))
    return candidates[0][2]


def resolved_plan_funding_groups(region: LuantiProtectedRegion) -> list[Group]:
    groups: list[Group] = []
    seen: set[int] = set()
    links = list(
        region.plan_funding_links.select_related("group").order_by("sort_order", "group_id")
    )
    for link in links:
        gid = link.group_id
        if gid and gid not in seen:
            groups.append(link.group)
            seen.add(gid)
    if region.plan_funding_include_master_top:
        top = region.effective_top_group()
        if top is not None and top.pk not in seen:
            groups.append(top)
            seen.add(top.pk)
    return groups


def available_velos_for_region(region: LuantiProtectedRegion) -> int:
    total = 0
    for group in resolved_plan_funding_groups(region):
        total += int(group.velos_spendable or 0)
    return total


def region_summary(region: LuantiProtectedRegion) -> dict:
    planned_qs = LuantiPlanBlock.objects.filter(
        region=region, status=LuantiPlanBlock.STATUS_PLANNED
    )
    count = planned_qs.count()
    total_velos = int(
        planned_qs.aggregate(s=Sum("buy_price_velos"))["s"] or 0
    )
    materialized = LuantiPlanBlock.objects.filter(
        region=region, status=LuantiPlanBlock.STATUS_MATERIALIZED
    ).count()
    return {
        "region_id": region.region_id,
        "region_pk": region.pk,
        "display_name": (region.display_name or "").strip() or region.region_id,
        "planned_count": count,
        "materialized_count": materialized,
        "total_velos_planned": total_velos,
        "available_velos": available_velos_for_region(region),
    }


def account_is_region_member(login_name: str, region: LuantiProtectedRegion) -> bool:
    key = (login_name or "").strip().lower()
    if not key:
        return False
    if region.members.filter(login_name__iexact=login_name).exists():
        return True
    if region.parent_id and region.parent is not None:
        return account_is_region_member(login_name, region.parent)
    return False


def account_has_build_access_at(
    login_name: str,
    *,
    world: str,
    x: int,
    y: int,
    z: int,
) -> bool:
    """Same rule as mcc_bridge build_mode: member of any protect_build region at the point."""
    ix, iy, iz = int(x), int(y), int(z)
    qs = LuantiProtectedRegion.objects.filter(
        enabled=True, protect_build=True, world__in=plan_world_names(world)
    )
    for region in qs:
        if region.contains_point(ix, iy, iz) and account_is_region_member(
            login_name, region
        ):
            return True
    return False


def _debit_velos_from_groups(
    groups: list[Group],
    amount: int,
) -> list[tuple[Group, int]]:
    """Return list of (group, debited) for audit. Raises PlanError if insufficient."""
    if amount <= 0:
        return []
    remaining = amount
    debits: list[tuple[Group, int]] = []
    for group in groups:
        if remaining <= 0:
            break
        group = Group.objects.select_for_update().get(pk=group.pk)
        have = int(group.velos_spendable or 0)
        if have <= 0:
            continue
        take = min(have, remaining)
        group.velos_spendable = F("velos_spendable") - take
        group.save(update_fields=["velos_spendable"])
        group.refresh_from_db(fields=["velos_spendable"])
        debits.append((group, take))
        remaining -= take
    if remaining > 0:
        raise PlanError("insufficient_velos")
    return debits


def _materialize_credit_item_name(block: LuantiPlanBlock) -> str:
    if block.shop_item_id:
        from luanti.models import LuantiShopItem

        shop_name = (
            LuantiShopItem.objects.filter(pk=block.shop_item_id)
            .values_list("item_name", flat=True)
            .first()
        )
        if shop_name:
            return str(shop_name).strip()
    from luanti.services.shop_sell_resolve import shop_credit_item_name

    return shop_credit_item_name((block.target_name or "").strip())


def _grant_materialize_purchase_credit(*, block: LuantiPlanBlock, fallback_login: str) -> bool:
    """Sell-back credit for one materialized block (region TOP, else placer wallet)."""
    from luanti.services.shop import resolve_group_for_player

    if block.purchase_credit_granted:
        logger.info(
            "[plan] materialize purchase_credit skipped block_id=%s item=%s reason=already_granted",
            block.pk,
            _materialize_credit_item_name(block),
        )
        return False
    item_name = _materialize_credit_item_name(block)
    if not item_name:
        logger.warning(
            "[plan] materialize purchase_credit skipped block_id=%s reason=missing_item",
            block.pk,
        )
        return False
    group = None
    region = block.region
    if region is not None:
        group = region.effective_top_group()
    if group is None:
        owner = (block.placed_by or fallback_login or "").strip()
        if not owner:
            logger.warning(
                "[plan] materialize purchase_credit skipped block_id=%s reason=no_region_top_or_owner",
                block.pk,
            )
            return False
        group = resolve_group_for_player(owner)
    if group is None:
        logger.warning(
            "[plan] materialize purchase_credit skipped block_id=%s reason=no_credit_group",
            block.pk,
        )
        return False
    credit, _ = LuantiShopPurchaseCredit.objects.select_for_update().get_or_create(
        group=group,
        item_name=item_name,
        defaults={"quantity": 0},
    )
    credit.quantity = F("quantity") + 1
    credit.save(update_fields=["quantity"])
    block.purchase_credit_granted = True
    block.save(update_fields=["purchase_credit_granted", "updated_at"])
    logger.info(
        "[plan] materialize purchase_credit granted block_id=%s group_id=%s item=%s",
        block.pk,
        group.pk,
        item_name,
    )
    return True


def register_placed_block(
    *,
    login_name: str,
    world: str,
    x: int,
    y: int,
    z: int,
    target_name: str,
    buy_price_velos: int,
    shop_item_id: int | None = None,
    param2: int = 0,
    region_id: str | None = None,
) -> dict:
    region = None
    if region_id:
        region = LuantiProtectedRegion.objects.filter(region_id=region_id, enabled=True).first()
    if region is None:
        region = resolve_build_region_at(world=world, x=x, y=y, z=z)
    if region is None:
        raise PlanError("no_region")
    if not account_has_build_access_at(
        login_name, world=world, x=x, y=y, z=z
    ):
        raise PlanError("not_member")
    price = max(1, int(buy_price_velos or 1))
    block_world = (region.world or "").strip() or default_world()
    block, created = LuantiPlanBlock.objects.update_or_create(
        world=block_world,
        x=int(x),
        y=int(y),
        z=int(z),
        defaults={
            "region": region,
            "shop_item_id": shop_item_id,
            "target_name": (target_name or "")[:128],
            "buy_price_velos": price,
            "param2": int(param2) & 0xFF,
            "placed_by": (login_name or "")[:32],
            "status": LuantiPlanBlock.STATUS_PLANNED,
            "purchase_credit_granted": False,
        },
    )
    return {"ok": True, "created": created, "block_id": block.pk, "region_id": region.region_id}


def unregister_removed_block(*, world: str, x: int, y: int, z: int) -> dict:
    deleted, _ = LuantiPlanBlock.objects.filter(
        world__in=plan_world_names(world),
        x=int(x),
        y=int(y),
        z=int(z),
        status=LuantiPlanBlock.STATUS_PLANNED,
    ).delete()
    return {"ok": True, "deleted": deleted}


def summary_for_player(
    *,
    login_name: str,
    region_id: str | None = None,
    world: str = "world",
    x: int | None = None,
    y: int | None = None,
    z: int | None = None,
) -> dict:
    region = None
    if region_id:
        region = LuantiProtectedRegion.objects.filter(region_id=region_id, enabled=True).first()
    if region is None and x is not None and y is not None and z is not None:
        region = resolve_build_region_at(world=world, x=x, y=y, z=z)
    if region is None:
        raise PlanError("no_region")
    if x is not None and y is not None and z is not None:
        if not account_has_build_access_at(login_name, world=world, x=x, y=y, z=z):
            raise PlanError("not_member")
    elif not account_is_region_member(login_name, region):
        raise PlanError("not_member")
    payload = region_summary(region)
    payload["ok"] = True
    return payload


@transaction.atomic
def materialize_blocks(
    *,
    login_name: str,
    region_id: str,
    client_tx_id: str,
    max_count: int = 1,
    mode: str = "manual",
    max_velos_budget: int | None = None,
) -> dict:
    if not client_tx_id:
        raise PlanError("missing_client_tx_id")
    existing = LuantiPlanMaterializeTransaction.objects.filter(client_tx_id=client_tx_id).first()
    if existing:
        return _materialize_idempotent_reply(existing)

    region = LuantiProtectedRegion.objects.filter(region_id=region_id, enabled=True).first()
    if region is None:
        raise PlanError("no_region")
    if mode != "auto" and not account_is_region_member(login_name, region):
        raise PlanError("not_member")

    max_count = max(1, min(int(max_count or 1), 256))
    order = getattr(settings, "LUANTI_PLAN_AUTO_CONVERT_ORDER", "y_asc")
    qs = (
        LuantiPlanBlock.objects.filter(
            region=region, status=LuantiPlanBlock.STATUS_PLANNED
        )
        .select_related(
            "region",
            "region__parent",
            "region__assigned_to_group",
            "region__parent__assigned_to_group",
        )
        .select_for_update()
    )
    if order == "y_asc":
        qs = qs.order_by("y", "x", "z")
    else:
        qs = qs.order_by("y", "x", "z")
    blocks = list(qs[:max_count])
    if not blocks:
        return {"ok": True, "blocks": [], "converted": 0}

    funding_groups = resolved_plan_funding_groups(region)
    if not funding_groups:
        raise PlanError("no_funding_pool")

    converted: list[dict] = []
    debited_total = 0
    velos_budget = None
    if max_velos_budget is not None:
        velos_budget = max(0, int(max_velos_budget))
    for block in blocks:
        price = int(block.buy_price_velos or 0)
        if price <= 0:
            continue
        if velos_budget is not None and debited_total + price > velos_budget:
            break
        tx_part = f"{client_tx_id}:{block.pk}"
        if LuantiPlanMaterializeTransaction.objects.filter(client_tx_id=tx_part).exists():
            continue
        try:
            debits = _debit_velos_from_groups(funding_groups, price)
        except PlanError as exc:
            if exc.code == "insufficient_velos":
                break
            raise
        block.status = LuantiPlanBlock.STATUS_MATERIALIZED
        block.save(update_fields=["status", "updated_at"])
        credit_granted = _grant_materialize_purchase_credit(
            block=block, fallback_login=login_name
        )
        primary_group = debits[0][0] if debits else None
        logger.info(
            "[plan] materialize block_id=%s pos=%s,%s,%s price=%s debited=%s credit_granted=%s funding_group_id=%s",
            block.pk,
            block.x,
            block.y,
            block.z,
            price,
            sum(d for _, d in debits),
            credit_granted,
            primary_group.pk if primary_group else None,
        )
        debited_total += sum(d for _, d in debits)
        LuantiPlanMaterializeTransaction.objects.create(
            client_tx_id=tx_part,
            region=region,
            group=primary_group,
            world=block.world,
            x=block.x,
            y=block.y,
            z=block.z,
            velos_delta=-price,
            login_name=(login_name or "")[:32],
        )
        converted.append(
            {
                "world": block.world,
                "x": block.x,
                "y": block.y,
                "z": block.z,
                "target_name": block.target_name,
                "param2": block.param2,
            }
        )

    if converted:
        from luanti.services.plan_push import push_plan_materialize

        live_push = mode == "auto" and bool(region.plan_live_convert_active)
        push_plan_materialize(converted, live=live_push)

    summary = region_summary(region)
    fx_key = "LUANTI_PLAN_LIVE_CONVERT_FX_STAGGER" if (
        mode == "auto" and region.plan_live_convert_active
    ) else "LUANTI_PLAN_FX_ENABLED"
    return {
        "ok": True,
        "converted": len(converted),
        "blocks": converted,
        "fx_stagger": bool(getattr(settings, fx_key, True)),
        **summary,
    }


@transaction.atomic
def remove_planned_blocks(
    *,
    login_name: str,
    region_id: str,
    max_count: int = 32,
    mode: str = "manual",
    world: str | None = None,
    x: int | None = None,
    y: int | None = None,
    z: int | None = None,
) -> dict:
    region = LuantiProtectedRegion.objects.filter(region_id=region_id, enabled=True).first()
    if region is None:
        raise PlanError("no_region")
    if mode != "auto":
        if (
            x is not None
            and y is not None
            and z is not None
            and (world or "").strip()
        ):
            if not account_has_build_access_at(
                login_name, world=world or "world", x=x, y=y, z=z
            ):
                raise PlanError("not_member")
        elif not account_is_region_member(login_name, region):
            raise PlanError("not_member")

    cap = int(getattr(settings, "LUANTI_PLAN_CLEAR_MAX_BATCH", 512) or 512)
    default_batch = int(getattr(settings, "LUANTI_PLAN_CLEAR_DEFAULT_BATCH", 32) or 32)
    max_count = max(1, min(int(max_count or default_batch), cap))
    order = getattr(settings, "LUANTI_PLAN_AUTO_CONVERT_ORDER", "y_asc")
    qs = LuantiPlanBlock.objects.filter(
        region=region, status=LuantiPlanBlock.STATUS_PLANNED
    ).select_for_update()
    if order == "y_asc":
        qs = qs.order_by("y", "x", "z")
    else:
        qs = qs.order_by("y", "x", "z")
    blocks = list(qs[:max_count])
    if not blocks:
        summary = region_summary(region)
        return {
            "ok": True,
            "removed": 0,
            "velos_total": 0,
            "blocks": [],
            **summary,
        }

    velos_total = 0
    cleared: list[dict] = []
    pks = []
    for block in blocks:
        velos_total += int(block.buy_price_velos or 0)
        cleared.append(
            {
                "world": block.world,
                "x": block.x,
                "y": block.y,
                "z": block.z,
            }
        )
        pks.append(block.pk)
    LuantiPlanBlock.objects.filter(pk__in=pks).delete()

    if cleared:
        from luanti.services.plan_push import push_plan_clear

        push_plan_clear(cleared)

    summary = region_summary(region)
    return {
        "ok": True,
        "removed": len(cleared),
        "velos_total": velos_total,
        "blocks": cleared,
        **summary,
    }


def _materialize_idempotent_reply(tx: LuantiPlanMaterializeTransaction) -> dict:
    region = tx.region
    return {
        "ok": True,
        "idempotent": True,
        "converted": 0,
        "blocks": [],
        **region_summary(region),
    }


def regions_for_funding_group(group_id: int) -> list[LuantiProtectedRegion]:
    region_ids = set(
        LuantiRegionPlanFunding.objects.filter(group_id=group_id).values_list(
            "region_id", flat=True
        )
    )
    if not region_ids:
        return []
    regions = list(
        LuantiProtectedRegion.objects.filter(pk__in=region_ids, enabled=True).prefetch_related(
            "plan_funding_links"
        )
    )
    group = Group.objects.filter(pk=group_id).first()
    if group is not None:
        for region in LuantiProtectedRegion.objects.filter(
            enabled=True, plan_funding_include_master_top=True
        ).select_related("parent", "assigned_to_group", "parent__assigned_to_group"):
            top = region.effective_top_group()
            if top is not None and top.pk == group_id and region.pk not in region_ids:
                regions.append(region)
    return regions


def _live_convert_max_per_tick() -> int:
    return int(
        getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_TICK", 4)
        or 4
    )


def _live_convert_max_per_earn(velos_added: int) -> int:
    if velos_added <= 0:
        return 0
    cap = int(
        getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_MAX_BLOCKS_PER_EARN", 6) or 6
    )
    floor = int(
        getattr(settings, "LUANTI_PLAN_LIVE_CONVERT_MIN_BLOCKS_PER_EARN", 1) or 1
    )
    return max(floor, min(cap, int(velos_added)))


def plan_auto_convert_globally_enabled() -> bool:
    return bool(getattr(settings, "LUANTI_PLAN_AUTO_CONVERT_ENABLED", False))


def _finish_live_convert_if_empty(region: LuantiProtectedRegion) -> bool:
    """Clear live flag when no planned blocks remain. Returns True if flag was cleared."""
    if not region.plan_live_convert_active:
        return False
    remaining = LuantiPlanBlock.objects.filter(
        region=region, status=LuantiPlanBlock.STATUS_PLANNED
    ).count()
    if remaining > 0:
        return False
    LuantiProtectedRegion.objects.filter(pk=region.pk).update(
        plan_live_convert_active=False,
        plan_live_convert_started_at=None,
        plan_live_convert_started_by=None,
    )
    region.plan_live_convert_active = False
    logger.info("[plan] live convert auto-stop region_id=%s (no holograms)", region.region_id)
    return True


def _earn_live_convert_velos_budget(
    region: LuantiProtectedRegion,
    velos_added: int,
    earned_group_id: int | None,
) -> int:
    """Velos an earn-triggered live tick may spend (excludes this impulse's leaf credit)."""
    pool = available_velos_for_region(region)
    if velos_added <= 0 or earned_group_id is None:
        return pool
    funding_ids = {g.pk for g in resolved_plan_funding_groups(region)}
    if earned_group_id in funding_ids:
        return max(0, pool - velos_added)
    return pool


def try_auto_materialize_for_region(
    region: LuantiProtectedRegion,
    *,
    max_count: int | None = None,
    max_velos_budget: int | None = None,
) -> int:
    """
    One live-convert step for a single region (admin-started).
    Returns number of blocks converted this call.
    """
    import uuid

    if not plan_auto_convert_globally_enabled():
        return 0
    region = (
        LuantiProtectedRegion.objects.filter(pk=region.pk, enabled=True)
        .prefetch_related("plan_funding_links")
        .first()
    )
    if region is None or not region.plan_live_convert_active:
        return 0
    pool = available_velos_for_region(region)
    if pool <= 0:
        return 0
    if max_velos_budget is not None and int(max_velos_budget) <= 0:
        return 0
    planned = LuantiPlanBlock.objects.filter(
        region=region, status=LuantiPlanBlock.STATUS_PLANNED
    ).count()
    if planned <= 0:
        _finish_live_convert_if_empty(region)
        return 0
    max_per = max_count if max_count is not None else _live_convert_max_per_tick()
    max_per = max(1, int(max_per))
    tx_id = f"admin-live-{region.pk}-{uuid.uuid4().hex[:12]}"
    try:
        result = materialize_blocks(
            login_name="",
            region_id=region.region_id,
            client_tx_id=tx_id,
            max_count=max_per,
            mode="auto",
            max_velos_budget=max_velos_budget,
        )
        converted = int(result.get("converted") or 0)
        if converted <= 0:
            _finish_live_convert_if_empty(region)
        return converted
    except PlanError:
        return 0


def _live_active_regions() -> list[LuantiProtectedRegion]:
    return list(
        LuantiProtectedRegion.objects.filter(
            plan_live_convert_active=True, enabled=True
        ).prefetch_related("plan_funding_links")
    )


def tick_plan_live_convert_regions() -> int:
    """Process all regions with admin live-convert enabled. Returns total blocks converted."""
    if not plan_auto_convert_globally_enabled():
        return 0
    converted_total = 0
    for region in _live_active_regions():
        converted_total += try_auto_materialize_for_region(region)
    return converted_total


def tick_plan_live_convert_on_earn(
    velos_added: int,
    *,
    earned_group_id: int | None = None,
) -> int:
    """Run live materialize for all active regions after an IoT Velos credit impulse."""
    if velos_added <= 0 or not plan_auto_convert_globally_enabled():
        return 0
    max_per = _live_convert_max_per_earn(velos_added)
    if max_per <= 0:
        return 0
    converted_total = 0
    for region in _live_active_regions():
        velos_budget = _earn_live_convert_velos_budget(
            region, velos_added, earned_group_id
        )
        converted_total += try_auto_materialize_for_region(
            region,
            max_count=max_per,
            max_velos_budget=velos_budget,
        )
    if converted_total:
        logger.info(
            "[plan] live convert on earn velos_added=%s converted=%s",
            velos_added,
            converted_total,
        )
    return converted_total


def set_plan_live_convert(
    region: LuantiProtectedRegion,
    *,
    active: bool,
    user=None,
) -> LuantiProtectedRegion:
    """Start or stop admin live conversion for a region."""
    region.plan_live_convert_active = bool(active)
    if active:
        region.plan_live_convert_started_at = timezone.now()
        region.plan_live_convert_started_by = user
    else:
        region.plan_live_convert_started_at = None
        region.plan_live_convert_started_by = None
    region.save(
        update_fields=[
            "plan_live_convert_active",
            "plan_live_convert_started_at",
            "plan_live_convert_started_by",
            "updated_at",
        ]
    )
    if active and plan_auto_convert_globally_enabled():
        converted = try_auto_materialize_for_region(region)
        if converted:
            logger.info(
                "[plan] live convert kick on start region_id=%s converted=%s",
                region.region_id,
                converted,
            )
    return region


def try_auto_materialize_for_group(group_id: int) -> int:
    """Materialize up to N blocks per active live region when pool has velos."""
    if not plan_auto_convert_globally_enabled():
        return 0
    converted_total = 0
    for region in regions_for_funding_group(group_id):
        if not region.plan_live_convert_active:
            continue
        converted_total += try_auto_materialize_for_region(region)
    return converted_total
