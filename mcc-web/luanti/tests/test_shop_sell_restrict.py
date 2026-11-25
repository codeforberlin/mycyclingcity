# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import time

import pytest
from django.conf import settings
from django.test import override_settings

from api.models import Group, GroupType
from luanti.services.http_security import sign_payload
from luanti.models import (
    LuantiAccount,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
)
from luanti.services.session_control import start_session
from luanti.services.shop import (
    luanti_shop_sell_own_wallet_restricted,
    purchase_credit_holder_chain,
    shop_sell,
    shop_sell_batch,
)
from luanti.services.shop import sell_hint_for_inventory_name


def _signed(body: dict, server_id: str = "luanti-1") -> dict:
    payload = dict(body)
    payload["server_id"] = server_id
    payload["timestamp"] = int(time.time())
    payload["signature"] = sign_payload({k: v for k, v in payload.items() if k != "signature"})
    return payload


@pytest.mark.django_db
def test_purchase_credit_chain_respects_top_flag(db):
    gtype, _ = GroupType.objects.get_or_create(name="RestrictType")
    top = Group.objects.create(
        name="SchoolTOP",
        group_type=gtype,
        luanti_shop_sell_own_wallet_credit_only=False,
    )
    leaf = Group.objects.create(
        name="Class1a",
        group_type=gtype,
        parent=top,
        luanti_username="RestrictPlayer",
    )
    assert luanti_shop_sell_own_wallet_restricted(leaf) is False
    assert [g.pk for g in purchase_credit_holder_chain(leaf)] == [leaf.pk, top.pk]

    top.luanti_shop_sell_own_wallet_credit_only = True
    top.save(update_fields=["luanti_shop_sell_own_wallet_credit_only"])
    assert luanti_shop_sell_own_wallet_restricted(leaf) is True
    assert [g.pk for g in purchase_credit_holder_chain(leaf)] == [leaf.pk]


@pytest.mark.django_db
def test_sell_hints_parent_pool_locked(db):
    gtype, _ = GroupType.objects.get_or_create(name="HintRestrict")
    top = Group.objects.create(
        name="TOP-Hint",
        group_type=gtype,
        luanti_shop_sell_own_wallet_credit_only=True,
    )
    leaf = Group.objects.create(
        name="Leaf-Hint",
        group_type=gtype,
        parent=top,
        luanti_username="HintRestrictPlayer",
    )
    LuantiAccount.objects.create(
        login_name="HintRestrictPlayer",
        id_tag="rfid-hint-restrict",
        assigned_to_group=leaf,
        allowed_modes=["build"],
    )
    start_session(
        account=LuantiAccount.objects.get(login_name="HintRestrictPlayer"),
        mode="build",
        duration=30,
    )
    cat = LuantiShopCategory.objects.create(slug="hr", name="HR")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=3,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(group=top, item_name=item.item_name, quantity=5)
    hint = sell_hint_for_inventory_name(
        login_name="HintRestrictPlayer",
        inventory_name="mcl_core:dirt",
    )
    assert hint["sellable"] is False
    assert hint["reason"] == "parent_pool_locked"
    assert hint["credit_group_name"] == top.name

    LuantiShopPurchaseCredit.objects.create(group=leaf, item_name=item.item_name, quantity=2)
    hint2 = sell_hint_for_inventory_name(
        login_name="HintRestrictPlayer",
        inventory_name="mcl_core:dirt",
    )
    assert hint2["sellable"] is True


@pytest.mark.django_db
def test_shop_sell_with_top_pool_credit_when_flag_off(db):
    gtype, _ = GroupType.objects.get_or_create(name="SellOpen")
    top = Group.objects.create(name="TOP-Open", group_type=gtype)
    leaf = Group.objects.create(
        name="Leaf-Open",
        group_type=gtype,
        parent=top,
        luanti_username="SellOpenPlayer",
        velos_spendable=0,
    )
    LuantiAccount.objects.create(
        login_name="SellOpenPlayer",
        id_tag="rfid-sell-open",
        assigned_to_group=leaf,
        allowed_modes=["build"],
    )
    start_session(
        account=LuantiAccount.objects.get(login_name="SellOpenPlayer"),
        mode="build",
        duration=30,
    )
    cat = LuantiShopCategory.objects.create(slug="so", name="SO")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=2,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(group=top, item_name=item.item_name, quantity=1)
    result = shop_sell(
        login_name="SellOpenPlayer",
        item_name=item.item_name,
        quantity=1,
        client_tx_id="sell-open-1",
    )
    assert result["ok"] is True
    leaf.refresh_from_db()
    assert leaf.velos_spendable == 2


@pytest.mark.django_db
def test_shop_sell_rejects_top_pool_when_flag_on(db):
    gtype, _ = GroupType.objects.get_or_create(name="SellLocked")
    top = Group.objects.create(
        name="TOP-Locked",
        group_type=gtype,
        luanti_shop_sell_own_wallet_credit_only=True,
    )
    leaf = Group.objects.create(
        name="Leaf-Locked",
        group_type=gtype,
        parent=top,
        luanti_username="SellLockedPlayer",
    )
    LuantiAccount.objects.create(
        login_name="SellLockedPlayer",
        id_tag="rfid-sell-locked",
        assigned_to_group=leaf,
        allowed_modes=["build"],
    )
    start_session(
        account=LuantiAccount.objects.get(login_name="SellLockedPlayer"),
        mode="build",
        duration=30,
    )
    cat = LuantiShopCategory.objects.create(slug="sl", name="SL")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=2,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(group=top, item_name=item.item_name, quantity=3)
    from luanti.services.shop import ShopError

    with pytest.raises(ShopError) as exc:
        shop_sell(
            login_name="SellLockedPlayer",
            item_name=item.item_name,
            quantity=1,
            client_tx_id="sell-locked-1",
        )
    assert exc.value.code == "insufficient_credit"

    batch = shop_sell_batch(
        login_name="SellLockedPlayer",
        items=[{"item_name": item.item_name, "quantity": 1}],
        client_tx_id="sell-locked-batch-1",
    )
    assert batch["ok"] is True
    assert batch["consumed"] == []
    assert len(batch["rejected"]) == 1
    assert batch["rejected"][0]["reason"] == "insufficient_credit"


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_api_sell_hints_parent_pool_locked(client):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    gtype, _ = GroupType.objects.get_or_create(name="APIRestrict")
    top = Group.objects.create(
        name="API-TOP",
        group_type=gtype,
        luanti_shop_sell_own_wallet_credit_only=True,
    )
    leaf = Group.objects.create(
        name="API-Leaf",
        group_type=gtype,
        parent=top,
        luanti_username="APIRestrictPlayer",
    )
    LuantiAccount.objects.create(
        login_name="APIRestrictPlayer",
        id_tag="rfid-api-restrict",
        assigned_to_group=leaf,
        allowed_modes=["build"],
    )
    start_session(
        account=LuantiAccount.objects.get(login_name="APIRestrictPlayer"),
        mode="build",
        duration=30,
    )
    cat = LuantiShopCategory.objects.create(slug="ar", name="AR")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=1,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(group=top, item_name=item.item_name, quantity=2)
    resp = client.post(
        "/api/luanti/shop/sell_hints/",
        data=json.dumps(
            _signed(
                {
                    "player": "APIRestrictPlayer",
                    "item_names": [item.item_name],
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    hint = data["hints"][item.item_name]
    assert hint["sellable"] is False
    assert hint["reason"] == "parent_pool_locked"