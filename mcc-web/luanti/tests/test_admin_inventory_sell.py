# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import (
    LuantiAccount,
    LuantiPlayerInventory,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
)
from luanti.services.admin_inventory_sell import (
    AdminInventorySellError,
    admin_sell_inventory_slots,
)
from luanti.services.session_control import get_or_create_inventory
from luanti.services.shop import shop_sell

User = get_user_model()


@pytest.fixture
def sell_setup(db):
    gtype, _ = GroupType.objects.get_or_create(name="AdminSellType")
    wallet = Group.objects.create(
        name="SellWallet",
        group_type=gtype,
        luanti_username="SellKid",
        velos_spendable=10,
    )
    account = LuantiAccount.objects.create(
        login_name="SellKid",
        id_tag="SellKid",
        assigned_to_group=wallet,
        allowed_modes=["build"],
    )
    cat = LuantiShopCategory.objects.create(slug="as", name="AS")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=5,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(
        group=wallet, item_name=item.item_name, quantity=3
    )
    inv = get_or_create_inventory(account, LuantiAccount.MODE_BUILD)
    inv.payload = [{"slot": 1, "name": "mcl_core:dirt", "count": 2}]
    inv.save(update_fields=["payload"])
    return account, wallet, item, inv


@pytest.mark.django_db
def test_shop_sell_without_session(sell_setup):
    account, wallet, _item, _inv = sell_setup
    wallet.refresh_from_db()
    before_velos = int(wallet.velos_spendable)
    result = shop_sell(
        login_name=account.login_name,
        item_name="mcl_core:dirt",
        quantity=1,
        client_tx_id="test-no-session-sell",
        require_active_build_session=False,
    )
    wallet.refresh_from_db()
    assert result["refunded"] == 5
    assert wallet.velos_spendable == before_velos + 5
    credit = LuantiShopPurchaseCredit.objects.get(group=wallet, item_name="mcl_core:dirt")
    assert credit.quantity == 2


@pytest.mark.django_db
def test_admin_sell_reduces_inventory_and_credits(sell_setup, monkeypatch):
    _account, wallet, _item, inv = sell_setup
    monkeypatch.setattr(
        "luanti.services.session_control.push_account_inventory",
        lambda _inv: False,
    )
    op = User.objects.create_user(username="op_sell", password="x")
    result = admin_sell_inventory_slots(
        inv=inv,
        selections=[(1, 2)],
        operator_user=op,
    )
    assert len(result["consumed"]) == 1
    assert result["refunded_total"] == 10
    inv.refresh_from_db()
    assert inv.payload == []
    wallet.refresh_from_db()
    assert wallet.velos_spendable == 20
    credit = LuantiShopPurchaseCredit.objects.get(group=wallet, item_name="mcl_core:dirt")
    assert credit.quantity == 1


@pytest.mark.django_db
def test_admin_sell_rejects_plan_item(sell_setup, monkeypatch):
    _account, wallet, _item, inv = sell_setup
    inv.payload = [
        {
            "slot": 2,
            "name": "mcl_core:dirt",
            "count": 1,
            "meta": {"mcc_plan": "1"},
        }
    ]
    inv.save(update_fields=["payload"])
    before_velos = int(wallet.velos_spendable)
    monkeypatch.setattr(
        "luanti.services.session_control.push_account_inventory",
        lambda _inv: False,
    )
    result = admin_sell_inventory_slots(
        inv=inv,
        selections=[(2, 1)],
        operator_user=None,
    )
    assert result["consumed"] == []
    assert result["rejected"][0]["reason"] == "plan_item"
    wallet.refresh_from_db()
    assert wallet.velos_spendable == before_velos


@pytest.mark.django_db
def test_admin_sell_wrong_mode_raises(sell_setup):
    _account, _wallet, _item, inv = sell_setup
    inv.mode = LuantiAccount.MODE_PLAY
    inv.save(update_fields=["mode"])
    with pytest.raises(AdminInventorySellError) as exc:
        admin_sell_inventory_slots(
            inv=inv,
            selections=[(1, 1)],
            operator_user=None,
        )
    assert exc.value.code == "wrong_mode"


@pytest.mark.django_db
def test_admin_sell_top_pool_locked_rejected(sell_setup, monkeypatch):
    account, wallet, item, inv = sell_setup
    gtype = wallet.group_type
    top = Group.objects.create(
        name="SellTOP",
        group_type=gtype,
        luanti_shop_sell_own_wallet_credit_only=True,
    )
    wallet.parent = top
    wallet.save(update_fields=["parent"])
    LuantiShopPurchaseCredit.objects.filter(group=wallet).delete()
    LuantiShopPurchaseCredit.objects.create(group=top, item_name=item.item_name, quantity=5)
    monkeypatch.setattr(
        "luanti.services.session_control.push_account_inventory",
        lambda _inv: False,
    )
    result = admin_sell_inventory_slots(
        inv=inv,
        selections=[(1, 1)],
        operator_user=None,
    )
    assert result["consumed"] == []
    assert result["rejected"][0]["reason"] == "not_sellable"


@pytest.mark.django_db
def test_inventory_sell_http_requires_permission(sell_setup):
    account, wallet, _item, _inv = sell_setup
    staff = User.objects.create_user(username="staff_nosell", password="x", is_staff=True)
    change_perm = Permission.objects.get(codename="change_luantiplayerinventory")
    staff.user_permissions.add(change_perm)
    staff.managed_groups.add(wallet)
    client = Client()
    client.force_login(staff)
    url = reverse("admin:luanti_account_inventory_edit", args=[account.pk, "build"])
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Stacks verkaufen" not in resp.content.decode()

    staff.user_permissions.add(Permission.objects.get(codename="sell_luantiplayerinventory"))
    resp2 = client.get(url)
    assert "Stacks verkaufen" in resp2.content.decode()


@pytest.mark.django_db
def test_inventory_sell_post(sell_setup):
    account, wallet, _item, _inv = sell_setup
    su = User.objects.create_superuser(username="su_sell", password="x", email="a@b.c")
    client = Client()
    client.force_login(su)
    url = reverse("admin:luanti_account_inventory_edit", args=[account.pk, "build"])
    resp = client.post(
        url,
        {
            "submit_sell": "1",
            "sell_confirm": "yes",
            "row-0-sell": "on",
            "row-0-slot": "1",
            "row-0-count": "2",
            "row-0-sell-qty": "1",
        },
    )
    assert resp.status_code == 302
    inv = LuantiPlayerInventory.objects.get(account=account, mode=LuantiAccount.MODE_BUILD)
    assert inv.payload[0]["count"] == 1
    wallet.refresh_from_db()
    assert wallet.velos_spendable == 15