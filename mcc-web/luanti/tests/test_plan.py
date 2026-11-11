# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

import pytest
from django.test import override_settings

from api.models import Group, GroupType
from luanti.models import (
    LuantiAccount,
    LuantiPlanBlock,
    LuantiProtectedRegion,
    LuantiRegionPlanFunding,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
)
from luanti.services.plan import (
    PlanError,
    materialize_blocks,
    register_placed_block,
    region_summary,
    remove_planned_blocks,
    resolve_build_region_at,
    set_plan_live_convert,
    summary_for_player,
    tick_plan_live_convert_on_earn,
    tick_plan_live_convert_regions,
    try_auto_materialize_for_group,
    try_auto_materialize_for_region,
)
from luanti.services.session_control import start_session
from luanti.services.shop import (
    effective_max_buy_quantity,
    parse_planning_flag,
    shop_buy,
    shop_sell_batch,
    ShopError,
)


def _signed(body: dict) -> dict:
    body = dict(body)
    body["server_id"] = "luanti-1"
    body["auth_token"] = "test-secret"
    return body


@pytest.fixture
def plan_setup(db):
    gtype, _ = GroupType.objects.get_or_create(name="PlanType")
    top = Group.objects.create(name="TopPlan", group_type=gtype, velos_spendable=500)
    extra = Group.objects.create(
        name="OmaTeam", group_type=gtype, parent=top, velos_spendable=200
    )
    account = LuantiAccount.objects.create(
        login_name="Builder1",
        id_tag="rfid-plan-1",
        assigned_to_group=top,
        allowed_modes=["play", "build"],
    )
    start_session(account=account, mode="build", duration=30)
    region = LuantiProtectedRegion.objects.create(
        region_id="plan-zone",
        display_name="Plan Zone",
        assigned_to_group=top,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=10,
        max_y=10,
        max_z=10,
        protect_build=True,
        enabled=True,
    )
    region.members.add(account)
    region.plan_funding_include_master_top = False
    region.save(update_fields=["plan_funding_include_master_top"])
    LuantiRegionPlanFunding.objects.create(region=region, group=extra, sort_order=10)
    return {
        "top": top,
        "extra": extra,
        "account": account,
        "region": region,
    }


@pytest.mark.django_db
def test_register_and_summary(plan_setup):
    register_placed_block(
        login_name="Builder1",
        world="world",
        x=1,
        y=2,
        z=3,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        shop_item_id=99,
        param2=0,
    )
    summary = summary_for_player(
        login_name="Builder1",
        world="world",
        x=1,
        y=2,
        z=3,
    )
    assert summary["planned_count"] == 1
    assert summary["total_velos_planned"] == 5
    assert summary["available_velos"] == 200


@pytest.mark.django_db
def test_materialize_debits_funding_group(plan_setup):
    region = plan_setup["region"]
    extra = plan_setup["extra"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=1,
        y=1,
        z=1,
        target_name="mcl_core:dirt",
        buy_price_velos=10,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    result = materialize_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        client_tx_id="mat-1",
        max_count=1,
    )
    assert result["converted"] == 1
    extra.refresh_from_db()
    assert extra.velos_spendable == 190
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_MATERIALIZED).count() == 1


@pytest.mark.django_db
def test_materialize_grants_purchase_credit_to_placer(plan_setup):
    region = plan_setup["region"]
    top = plan_setup["top"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=2,
        y=1,
        z=1,
        target_name="mcl_core:dirt",
        buy_price_velos=10,
        placed_by="Builder1",
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    result = materialize_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        client_tx_id="mat-credit-1",
        max_count=1,
    )
    assert result["converted"] == 1
    credit = LuantiShopPurchaseCredit.objects.get(group=top, item_name="mcl_core:dirt")
    assert credit.quantity == 1


@pytest.mark.django_db
def test_materialize_purchase_credit_on_region_top_not_leaf_wallet(db):
    """Oma funds convert; sell-back credit sits on region TOP, not the placer leaf wallet."""
    gtype, _ = GroupType.objects.get_or_create(name="PlanInstType")
    school_top = Group.objects.create(
        name="SchoolTOP", group_type=gtype, velos_spendable=0, parent=None
    )
    class_leaf = Group.objects.create(
        name="ClassLeaf", group_type=gtype, velos_spendable=0, parent=school_top
    )
    oma = Group.objects.create(
        name="OmaVelos", group_type=gtype, velos_spendable=200, parent=None
    )
    account = LuantiAccount.objects.create(
        login_name="KidPlan",
        id_tag="rfid-kid-plan",
        assigned_to_group=school_top,
        active_wallet=class_leaf,
        wallet_mode=LuantiAccount.WALLET_FIXED,
        allowed_modes=["play", "build"],
    )
    start_session(account=account, mode="build", duration=30)
    region = LuantiProtectedRegion.objects.create(
        region_id="school-zone",
        assigned_to_group=school_top,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=10,
        max_y=10,
        max_z=10,
        protect_build=True,
        enabled=True,
        plan_funding_include_master_top=False,
    )
    region.members.add(account)
    region.save(update_fields=["plan_funding_include_master_top"])
    LuantiRegionPlanFunding.objects.create(region=region, group=oma, sort_order=10)
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=3,
        y=1,
        z=3,
        target_name="mcl_core:dirt",
        buy_price_velos=10,
        placed_by="KidPlan",
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    materialize_blocks(
        login_name="KidPlan",
        region_id=region.region_id,
        client_tx_id="mat-top-credit",
        max_count=1,
    )
    assert LuantiShopPurchaseCredit.objects.filter(
        group=class_leaf, item_name="mcl_core:dirt"
    ).exists() is False
    credit = LuantiShopPurchaseCredit.objects.get(
        group=school_top, item_name="mcl_core:dirt"
    )
    assert credit.quantity == 1


@pytest.mark.django_db
def test_materialize_purchase_credit_sub_top_override(db):
    """Sub with own TOP gets purchase credit there, not on master TOP."""
    gtype, _ = GroupType.objects.get_or_create(name="SubTopType")
    master_top = Group.objects.create(
        name="MasterTOP", group_type=gtype, velos_spendable=100, parent=None
    )
    sub_top = Group.objects.create(
        name="ClassTOP", group_type=gtype, velos_spendable=100, parent=None
    )
    oma = Group.objects.create(
        name="OmaSubTop", group_type=gtype, velos_spendable=50, parent=None
    )
    master = LuantiProtectedRegion.objects.create(
        region_id="master_site",
        assigned_to_group=master_top,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=100,
        max_y=50,
        max_z=100,
        protect_build=True,
        enabled=True,
        plan_funding_include_master_top=False,
    )
    sub = LuantiProtectedRegion.objects.create(
        region_id="master_site_class_a",
        parent=master,
        assigned_to_group=sub_top,
        min_x=10,
        min_y=0,
        min_z=10,
        max_x=30,
        max_y=20,
        max_z=30,
        protect_build=True,
        enabled=True,
        plan_funding_include_master_top=False,
    )
    LuantiRegionPlanFunding.objects.create(region=sub, group=oma, sort_order=10)
    account = LuantiAccount.objects.create(
        login_name="KidSubTop",
        id_tag="rfid-sub-top",
        assigned_to_group=sub_top,
        allowed_modes=["play", "build"],
    )
    sub.members.add(account)
    LuantiPlanBlock.objects.create(
        region=sub,
        world="world",
        x=12,
        y=1,
        z=12,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        placed_by="KidSubTop",
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    materialize_blocks(
        login_name="KidSubTop",
        region_id=sub.region_id,
        client_tx_id="sub-top-credit",
        max_count=1,
    )
    assert sub.effective_top_group().pk == sub_top.pk
    assert LuantiShopPurchaseCredit.objects.filter(
        group=master_top, item_name="mcl_core:dirt"
    ).exists() is False
    assert LuantiShopPurchaseCredit.objects.get(
        group=sub_top, item_name="mcl_core:dirt"
    ).quantity == 1


@pytest.mark.django_db
def test_sell_batch_parent_credit_velos_to_leaf_wallet(db):
    """Sell-back credit on region TOP; velos refund to the selling player's wallet."""
    gtype, _ = GroupType.objects.get_or_create(name="PlanSellType")
    school_top = Group.objects.create(
        name="SchoolTOP2", group_type=gtype, velos_spendable=0, parent=None
    )
    class_leaf = Group.objects.create(
        name="ClassLeaf2", group_type=gtype, velos_spendable=20, parent=school_top
    )
    account = LuantiAccount.objects.create(
        login_name="KidSell",
        id_tag="rfid-kid-sell",
        assigned_to_group=school_top,
        active_wallet=class_leaf,
        wallet_mode=LuantiAccount.WALLET_FIXED,
        allowed_modes=["play", "build"],
    )
    start_session(account=account, mode="play", duration=30)
    cat = LuantiShopCategory.objects.create(slug="plan-sell-cat", name="Cat")
    LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=7,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(
        group=school_top, item_name="mcl_core:dirt", quantity=1
    )
    result = shop_sell_batch(
        login_name="KidSell",
        items=[{"item_name": "mcl_core:dirt", "quantity": 1}],
        client_tx_id="plan-sell-parent-credit",
    )
    assert result["ok"] is True
    assert result["refunded_total"] == 7
    class_leaf.refresh_from_db()
    assert class_leaf.velos_spendable == 27
    assert not LuantiShopPurchaseCredit.objects.filter(
        group=school_top, item_name="mcl_core:dirt"
    ).exists()


@pytest.mark.django_db
def test_materialize_stair_inner_node_grants_base_purchase_credit(plan_setup):
    region = plan_setup["region"]
    top = plan_setup["top"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=8,
        y=1,
        z=8,
        target_name="mcl_stairs:stair_acaciawood_inner",
        buy_price_velos=5,
        placed_by="Builder1",
        shop_item_id=None,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    materialize_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        client_tx_id="mat-stair-inner-credit",
        max_count=1,
    )
    credit = LuantiShopPurchaseCredit.objects.get(
        group=top, item_name="mcl_stairs:stair_acaciawood"
    )
    assert credit.quantity == 1


@pytest.mark.django_db
def test_replan_at_same_cell_grants_purchase_credit_again(plan_setup):
    """Re-placing a hologram at the same coords must reset purchase_credit_granted."""
    region = plan_setup["region"]
    top = plan_setup["top"]
    x, y, z = 5, 1, 5
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=x,
        y=y,
        z=z,
        target_name="mcl_stairs:stair_acaciawood",
        buy_price_velos=5,
        placed_by="Builder1",
        shop_item_id=None,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    materialize_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        client_tx_id="replan-mat-1",
        max_count=1,
    )
    credit = LuantiShopPurchaseCredit.objects.get(
        group=top, item_name="mcl_stairs:stair_acaciawood"
    )
    assert credit.quantity == 1
    block = LuantiPlanBlock.objects.get(world="world", x=x, y=y, z=z)
    assert block.status == LuantiPlanBlock.STATUS_MATERIALIZED
    assert block.purchase_credit_granted is True

    register_placed_block(
        login_name="Builder1",
        world="world",
        x=x,
        y=y,
        z=z,
        target_name="mcl_stairs:slab_acaciatree_bark",
        buy_price_velos=5,
        shop_item_id=None,
        param2=0,
    )
    block.refresh_from_db()
    assert block.status == LuantiPlanBlock.STATUS_PLANNED
    assert block.purchase_credit_granted is False

    materialize_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        client_tx_id="replan-mat-2",
        max_count=1,
    )
    block.refresh_from_db()
    assert block.purchase_credit_granted is True
    credit_stair = LuantiShopPurchaseCredit.objects.get(
        group=top, item_name="mcl_stairs:stair_acaciawood"
    )
    assert credit_stair.quantity == 1
    credit_slab = LuantiShopPurchaseCredit.objects.get(
        group=top, item_name="mcl_stairs:slab_acaciatree_bark"
    )
    assert credit_slab.quantity == 1


@pytest.mark.django_db
@override_settings(LUANTI_PLAN_CLEAR_MAX_BATCH=512)
def test_remove_planned_blocks(plan_setup):
    region = plan_setup["region"]
    for i, (x, y, z, price) in enumerate(
        [(1, 1, 1, 5), (2, 1, 1, 7), (3, 1, 1, 3)], start=1
    ):
        LuantiPlanBlock.objects.create(
            region=region,
            world="world",
            x=x,
            y=y,
            z=z,
            target_name="mcl_core:dirt",
            buy_price_velos=price,
            status=LuantiPlanBlock.STATUS_PLANNED,
        )
    result = remove_planned_blocks(
        login_name="Builder1",
        region_id=region.region_id,
        max_count=2,
        world="world",
        x=1,
        y=1,
        z=1,
    )
    assert result["removed"] == 2
    assert result["velos_total"] == 12
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_PLANNED).count() == 1

    with pytest.raises(PlanError) as exc:
        remove_planned_blocks(
            login_name="Nobody",
            region_id=region.region_id,
            max_count=1,
            world="world",
            x=1,
            y=1,
            z=1,
        )
    assert exc.value.code == "not_member"


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_planning_buy_zero_velo(client, plan_setup):
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blocks")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=7,
    )
    group = plan_setup["top"]
    resp = client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Builder1",
                    "item_id": item.pk,
                    "quantity": 2,
                    "client_tx_id": "plan-buy-1",
                    "planning": True,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    meta = data["grant"][0]["meta"]
    assert meta["mcc_plan"] == "1"
    assert meta["mcc_purchase_velos"] == "0"
    assert meta["mcc_buy_price_velos"] == "7"
    group.refresh_from_db()
    assert group.velos_spendable == 500
    assert not LuantiShopPurchaseCredit.objects.filter(group=group).exists()
    assert LuantiShopTransaction.objects.filter(side=LuantiShopTransaction.SIDE_PLAN_BUY).exists()
    assert data["grant"][0]["count"] == 2


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        ("true", True),
        ("True", True),
        ("1", True),
        (1, True),
        ("yes", True),
        ("on", True),
        (False, False),
        ("false", False),
        ("0", False),
        (0, False),
        (None, False),
        ("", False),
        ("no", False),
    ],
)
def test_parse_planning_flag(value, expected):
    assert parse_planning_flag(value) is expected


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_planning_buy_accepts_string_true(client, plan_setup):
    cat = LuantiShopCategory.objects.create(slug="blocks-str", name="BlocksStr")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=4,
    )
    group = plan_setup["top"]
    resp = client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Builder1",
                    "item_id": item.pk,
                    "quantity": 1,
                    "client_tx_id": "plan-buy-str-true",
                    "planning": "true",
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    group.refresh_from_db()
    assert group.velos_spendable == 500
    tx = LuantiShopTransaction.objects.get(client_tx_id="plan-buy-str-true")
    assert tx.side == LuantiShopTransaction.SIDE_PLAN_BUY
    assert tx.velos_delta == 0


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_buy_without_planning_still_charges(client, plan_setup):
    cat = LuantiShopCategory.objects.create(slug="blocks-paid", name="BlocksPaid")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:cobble",
        buy_price_velos=9,
    )
    group = plan_setup["top"]
    resp = client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Builder1",
                    "item_id": item.pk,
                    "quantity": 2,
                    "client_tx_id": "paid-buy-1",
                    "planning": False,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    group.refresh_from_db()
    assert group.velos_spendable == 482
    tx = LuantiShopTransaction.objects.get(client_tx_id="paid-buy-1")
    assert tx.side == LuantiShopTransaction.SIDE_BUY
    assert tx.velos_delta == -18


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_effective_max_buy_quantity_stone_stack_size_one(db):
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blocks")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=2,
        stack_size=1,
    )
    assert effective_max_buy_quantity(item) == 64


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_buy_stone_quantity_with_stack_size_one(client, plan_setup):
    cat = LuantiShopCategory.objects.create(slug="blocks2", name="Blocks2")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=2,
        stack_size=1,
    )
    resp = client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Builder1",
                    "item_id": item.pk,
                    "quantity": 16,
                    "client_tx_id": "buy-stone-16",
                    "planning": True,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["grant"][0]["count"] == 16


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_buy_quantity_is_physical_not_stack_size(client, plan_setup):
    """Treppen/Blöcke mit stack_size=64: Menge 1 im Shop = 1 Item, nicht 64."""
    cat = LuantiShopCategory.objects.create(slug="stairs", name="Stairs")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_stairs:stair_acacia",
        buy_price_velos=3,
        stack_size=64,
    )
    resp = client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Builder1",
                    "item_id": item.pk,
                    "quantity": 1,
                    "client_tx_id": "buy-stair-1",
                    "planning": True,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["grant"][0]["count"] == 1


@pytest.mark.django_db
def test_shop_buy_quantity_exceeds_stack_size(plan_setup):
    cat = LuantiShopCategory.objects.create(slug="tools", name="Tools")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_tools:axe_diamond",
        buy_price_velos=10,
        stack_size=1,
    )
    with pytest.raises(ShopError) as exc:
        shop_buy(
            login_name="Builder1",
            item_id=item.pk,
            quantity=2,
            client_tx_id="buy-axe-2",
            planning=True,
        )
    assert exc.value.code == "quantity_exceeds_stack"


@pytest.mark.django_db
def test_shop_planning_requires_build(db):
    gtype, _ = GroupType.objects.get_or_create(name="PlanType2")
    group = Group.objects.create(name="T2", group_type=gtype, velos_spendable=10)
    LuantiAccount.objects.create(
        login_name="Player2",
        id_tag="rfid-2",
        assigned_to_group=group,
        allowed_modes=["play", "build"],
    )
    start_session(
        account=LuantiAccount.objects.get(login_name="Player2"),
        mode="play",
        duration=10,
    )
    cat = LuantiShopCategory.objects.create(slug="b2", name="B2")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:cobble",
        buy_price_velos=3,
    )
    with pytest.raises(ShopError) as exc:
        shop_buy(
            login_name="Player2",
            item_id=item.pk,
            quantity=1,
            client_tx_id="pb-1",
            planning=True,
        )
    assert exc.value.code == "planning_requires_build"


@pytest.mark.django_db
@override_settings(MCC_LUANTI_WORLD="mycyclingcity")
def test_resolve_build_region_legacy_world_alias(db, plan_setup):
    region = plan_setup["region"]
    region.world = "mycyclingcity"
    region.save(update_fields=["world"])
    resolved = resolve_build_region_at(world="world", x=1, y=2, z=3)
    assert resolved is not None
    assert resolved.region_id == region.region_id


@pytest.mark.django_db
def test_summary_parent_region_membership(db, plan_setup):
    gtype, _ = GroupType.objects.get_or_create(name="PlanParent")
    top = Group.objects.create(name="TopParent", group_type=gtype, velos_spendable=100)
    master = LuantiProtectedRegion.objects.create(
        region_id="master-plan",
        display_name="Master",
        assigned_to_group=top,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=20,
        max_y=10,
        max_z=20,
        protect_build=True,
        enabled=True,
    )
    master.members.add(plan_setup["account"])
    sub = LuantiProtectedRegion.objects.create(
        region_id="sub-plan",
        display_name="Sub",
        parent=master,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=10,
        max_y=10,
        max_z=10,
        protect_build=True,
        enabled=True,
    )
    LuantiRegionPlanFunding.objects.create(region=sub, group=plan_setup["extra"], sort_order=1)
    sub.plan_funding_include_master_top = False
    sub.save(update_fields=["plan_funding_include_master_top"])
    summary = summary_for_player(
        login_name="Builder1",
        world="world",
        x=5,
        y=1,
        z=5,
    )
    assert summary["region_id"] == "sub-plan"
    assert summary["planned_count"] == 0

    other = LuantiAccount.objects.create(
        login_name="Outsider",
        id_tag="rfid-out",
        assigned_to_group=top,
        allowed_modes=["build"],
    )
    with pytest.raises(PlanError) as exc:
        summary_for_player(
            login_name=other.login_name,
            world="world",
            x=5,
            y=1,
            z=5,
        )
    assert exc.value.code == "not_member"


@pytest.mark.django_db
def test_try_auto_materialize_for_group_converts_when_pool_funded(plan_setup):
    region = plan_setup["region"]
    extra = plan_setup["extra"]
    set_plan_live_convert(region, active=True, user=None)
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=1,
        y=1,
        z=1,
        target_name="mcl_core:dirt",
        buy_price_velos=10,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    converted = try_auto_materialize_for_group(extra.pk)
    assert converted >= 1
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_MATERIALIZED).count() == 1


@pytest.mark.django_db
def test_try_auto_materialize_for_group_skips_without_live_flag(plan_setup):
    region = plan_setup["region"]
    extra = plan_setup["extra"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=2,
        y=1,
        z=2,
        target_name="mcl_core:dirt",
        buy_price_velos=10,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    assert try_auto_materialize_for_group(extra.pk) == 0


@pytest.mark.django_db
def test_tick_plan_live_convert_auto_stops_when_empty(plan_setup):
    region = plan_setup["region"]
    set_plan_live_convert(region, active=True, user=None)
    tick_plan_live_convert_regions()
    region.refresh_from_db()
    assert region.plan_live_convert_active is False


@pytest.mark.django_db
def test_tick_plan_live_convert_on_earn_reserves_fresh_leaf_credit(plan_setup):
    """Live on earn must not debit Velos credited in the same IoT impulse."""
    region = plan_setup["region"]
    extra = plan_setup["extra"]
    extra.velos_spendable = 10
    extra.save(update_fields=["velos_spendable"])
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=6,
        y=1,
        z=6,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    region.plan_live_convert_active = True
    region.save(update_fields=["plan_live_convert_active", "updated_at"])
    with override_settings(LUANTI_PLAN_AUTO_CONVERT_ENABLED=True):
        converted = tick_plan_live_convert_on_earn(10, earned_group_id=extra.pk)
    assert converted == 0
    extra.refresh_from_db()
    assert extra.velos_spendable == 10
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_PLANNED).count() == 1

    extra.velos_spendable = 25
    extra.save(update_fields=["velos_spendable"])
    with override_settings(LUANTI_PLAN_AUTO_CONVERT_ENABLED=True):
        converted = tick_plan_live_convert_on_earn(10, earned_group_id=extra.pk)
    assert converted >= 1
    extra.refresh_from_db()
    assert extra.velos_spendable == 20


@pytest.mark.django_db
def test_tick_plan_live_convert_on_earn_master_top_only_funding(plan_setup):
    """IoT earn triggers all live regions (not only regions_for_funding_group leaf)."""
    region = plan_setup["region"]
    top = plan_setup["top"]
    region.plan_funding_links.all().delete()
    region.plan_funding_include_master_top = True
    region.save(update_fields=["plan_funding_include_master_top"])
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=4,
        y=1,
        z=4,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    region.plan_live_convert_active = True
    region.save(update_fields=["plan_live_convert_active", "updated_at"])
    with override_settings(LUANTI_PLAN_AUTO_CONVERT_ENABLED=True):
        converted = tick_plan_live_convert_on_earn(2)
    assert converted >= 1
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_MATERIALIZED).count() == 1
    top.refresh_from_db()
    assert top.velos_spendable == 500 - 5


@pytest.mark.django_db
def test_push_plan_materialize_live_uses_shorter_layer_delay(plan_setup, monkeypatch):
    from luanti.services import plan_push

    captured: list[dict] = []

    def fake_push(message):
        captured.append(message)
        return 1

    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        fake_push,
    )
    with override_settings(
        LUANTI_PLAN_CONVERT_LAYER_DELAY=0.35,
        LUANTI_PLAN_LIVE_CONVERT_LAYER_DELAY=0.1,
    ):
        plan_push.push_plan_materialize([{"x": 1, "y": 1, "z": 1}], live=True)
        plan_push.push_plan_materialize([{"x": 2, "y": 1, "z": 2}], live=False)
    assert captured[0]["layer_delay"] == pytest.approx(0.1)
    assert captured[1]["layer_delay"] == pytest.approx(0.35)


@pytest.mark.django_db
def test_set_plan_live_convert_starts_immediately_when_pool_funded(plan_setup):
    region = plan_setup["region"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=5,
        y=1,
        z=5,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    with override_settings(LUANTI_PLAN_AUTO_CONVERT_ENABLED=True):
        set_plan_live_convert(region, active=True, user=None)
    assert LuantiPlanBlock.objects.filter(status=LuantiPlanBlock.STATUS_MATERIALIZED).count() == 1
    region.refresh_from_db()
    assert region.plan_live_convert_active is True


@pytest.mark.django_db
def test_try_auto_materialize_for_region_respects_live_flag(plan_setup):
    region = plan_setup["region"]
    LuantiPlanBlock.objects.create(
        region=region,
        world="world",
        x=3,
        y=1,
        z=3,
        target_name="mcl_core:dirt",
        buy_price_velos=5,
        status=LuantiPlanBlock.STATUS_PLANNED,
    )
    assert try_auto_materialize_for_region(region) == 0
    set_plan_live_convert(region, active=True, user=None)
    assert try_auto_materialize_for_region(region) >= 1
