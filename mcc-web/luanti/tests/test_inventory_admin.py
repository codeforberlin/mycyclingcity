# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import (
    LuantiAccount,
    LuantiSession,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiShopPurchaseCredit,
)
from luanti.services.inventory_admin import (
    InventoryAdminError,
    format_inventory_table_html,
    merge_inventory_meta,
    parse_inventory_post,
    save_player_inventory,
)
from luanti.services.session_control import (
    get_or_create_inventory,
    pause_session,
    push_account_inventory,
    start_session,
)

User = get_user_model()


class _FakePost(dict):
  def get(self, key, default=None):
    return super().get(key, default)


@pytest.fixture
def account(db):
    return LuantiAccount.objects.create(login_name="KidInv", id_tag="KidInv")


@pytest.mark.django_db
def test_merge_inventory_meta_keeps_plan_meta():
    old = [
        {
            "slot": 1,
            "name": "mcl_core:dirt",
            "count": 2,
            "meta": {"mcc_plan": "1", "mcc_target_name": "keep"},
        }
    ]
    new = [{"slot": 1, "name": "mcl_core:dirt", "count": 5}]
    merged = merge_inventory_meta(old, new)
    assert merged[0]["count"] == 5
    assert merged[0]["meta"]["mcc_plan"] == "1"


@pytest.mark.django_db
def test_parse_inventory_post_validates():
    post = _FakePost(
        {
            "row-0-slot": "2",
            "row-0-name": "mcl_core:stone",
            "row-0-count": "3",
            "row-1-slot": "2",
            "row-1-name": "mcl_core:dirt",
            "row-1-count": "1",
        }
    )
    with pytest.raises(InventoryAdminError) as exc:
        parse_inventory_post(post)
    assert exc.value.code == "duplicate_slot"


@pytest.mark.django_db
def test_save_player_inventory_pushes_set_inventory(account, monkeypatch):
    session = start_session(account=account, duration=20)
    inv = get_or_create_inventory(account, "play")
    pushed = []

    def _capture(msg):
        pushed.append(msg)
        return 1

    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        _capture,
    )
    rows = [{"slot": 1, "name": "mcl_core:dirt", "count": 4}]
    inv, live = save_player_inventory(inv, rows)
    assert live is True
    assert inv.revision == 1
    assert inv.payload == rows
    assert any(m.get("type") == "SET_INVENTORY" for m in pushed)
    assert pushed[0]["inventory"] == rows
    assert session.pk


@pytest.mark.django_db
def test_push_account_inventory_skipped_when_paused(account, monkeypatch):
    start_session(account=account, duration=20)
    inv = get_or_create_inventory(account, "play")
    inv.payload = [{"slot": 1, "name": "mcl_core:dirt", "count": 1}]
    inv.revision = 1
    inv.save()
    session = LuantiSession.objects.get(account=account, status=LuantiSession.STATUS_ACTIVE)
    pause_session(session)
    pushed = []
    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        lambda msg: pushed.append(msg),
    )
    assert push_account_inventory(inv) is False
    assert pushed == []


@pytest.mark.django_db
def test_format_inventory_table_shows_shop_credit_column(account):
    gtype, _ = GroupType.objects.get_or_create(name="InvTblType")
    wallet = Group.objects.create(
        name="InvWallet",
        group_type=gtype,
        luanti_username="KidInv",
        velos_spendable=0,
    )
    account.assigned_to_group = wallet
    account.save(update_fields=["assigned_to_group"])
    start_session(account=account, mode="build", duration=30)
    cat = LuantiShopCategory.objects.create(slug="inv", name="Inv")
    LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=3,
        stack_size=64,
    )
    LuantiShopPurchaseCredit.objects.create(
        group=wallet, item_name="mcl_core:dirt", quantity=4
    )
    html = str(
        format_inventory_table_html(
            [{"slot": 1, "name": "mcl_core:dirt", "count": 2}],
            account=account,
        )
    )
    assert "Shop-Guthaben" in html
    assert "InvWallet" in html
    assert "4 Kaufguthaben" in html
    assert "3 Velos" in html


@pytest.mark.django_db
def test_format_inventory_table_without_account_omits_shop_column(account):
    html = str(
        format_inventory_table_html(
            [{"slot": 1, "name": "mcl_core:dirt", "count": 1}],
        )
    )
    assert "Shop-Guthaben" not in html


@pytest.mark.django_db
def test_inventory_edit_view_superuser(db, account):
    su = User.objects.create_superuser(username="inv_su", password="x", email="a@b.c")
    client = Client()
    client.force_login(su)
    url = reverse("admin:luanti_account_inventory_edit", args=[account.pk, "play"])
    resp = client.get(url)
    assert resp.status_code == 200