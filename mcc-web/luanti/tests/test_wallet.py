# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import time

import pytest
from django.test import Client, override_settings

from api.models import Group, GroupType
from luanti.models import LuantiAccount
from luanti.services.http_security import sign_payload
from luanti.services.session_control import start_session
from luanti.services.wallet import resolve_wallet_group, withdraw_velos, WalletError


def _signed(body: dict, server_id: str = "luanti-1") -> dict:
    payload = dict(body)
    payload["server_id"] = server_id
    payload["timestamp"] = int(time.time())
    payload["signature"] = sign_payload({k: v for k, v in payload.items() if k != "signature"})
    return payload


@pytest.fixture
def api_client():
    return Client()


@pytest.mark.django_db
def test_candidate_wallet_groups_only_leaves():
    from luanti.services.wallet import candidate_wallet_groups

    gtype, _ = GroupType.objects.get_or_create(name="WalletTypeLeaf")
    top = Group.objects.create(name="TOP-L", group_type=gtype)
    leaf = Group.objects.create(name="LeafL", group_type=gtype, parent=top, velos_spendable=3)
    mid = Group.objects.create(name="Mid", group_type=gtype, parent=top)
    nested = Group.objects.create(name="NestedLeaf", group_type=gtype, parent=mid, velos_spendable=1)
    ids = {g.pk for g in candidate_wallet_groups(top)}
    assert leaf.pk in ids
    assert nested.pk in ids
    assert top.pk not in ids
    assert mid.pk not in ids


@pytest.mark.django_db
def test_resolve_fixed_and_auto_leaf():
    gtype, _ = GroupType.objects.get_or_create(name="WalletType")
    top = Group.objects.create(name="TOP-W", group_type=gtype)
    leaf_a = Group.objects.create(name="LeafA", group_type=gtype, parent=top, velos_spendable=10)
    leaf_b = Group.objects.create(name="LeafB", group_type=gtype, parent=top, velos_spendable=50)
    account = LuantiAccount.objects.create(
        login_name="Player1",
        id_tag="rfid-w1",
        assigned_to_group=top,
        active_wallet=leaf_a,
        wallet_mode=LuantiAccount.WALLET_FIXED,
    )
    assert resolve_wallet_group(account).pk == leaf_a.pk

    account.wallet_mode = LuantiAccount.WALLET_AUTO_LEAF
    account.save(update_fields=["wallet_mode"])
    assert resolve_wallet_group(account).pk == leaf_b.pk

    account.wallet_mode = LuantiAccount.WALLET_POOL
    account.save(update_fields=["wallet_mode"])
    assert resolve_wallet_group(account).pk == top.pk


@pytest.mark.django_db
def test_session_wallet_override():
    gtype, _ = GroupType.objects.get_or_create(name="WalletType2")
    top = Group.objects.create(name="TOP-W2", group_type=gtype)
    leaf = Group.objects.create(name="LeafX", group_type=gtype, parent=top, velos_spendable=7)
    other = Group.objects.create(name="Other", group_type=gtype, velos_spendable=99)
    account = LuantiAccount.objects.create(
        login_name="Player2",
        id_tag="rfid-w2",
        assigned_to_group=top,
        active_wallet=leaf,
        wallet_mode=LuantiAccount.WALLET_FIXED,
    )
    session = start_session(account=account, mode="play", wallet_group=other)
    assert resolve_wallet_group(account, session=session).pk == other.pk


@pytest.mark.django_db
def test_withdraw_velos():
    gtype, _ = GroupType.objects.get_or_create(name="WalletType3")
    leaf = Group.objects.create(name="LeafY", group_type=gtype, velos_spendable=20)
    LuantiAccount.objects.create(
        login_name="Player3",
        id_tag="rfid-w3",
        active_wallet=leaf,
        wallet_mode=LuantiAccount.WALLET_FIXED,
    )
    result = withdraw_velos(login_name="Player3", amount=5)
    assert result["ok"] is True
    assert result["velos_spendable"] == 15
    leaf.refresh_from_db()
    assert leaf.velos_spendable == 15
    with pytest.raises(WalletError):
        withdraw_velos(login_name="Player3", amount=100)


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_wallet_withdraw_api(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    gtype, _ = GroupType.objects.get_or_create(name="WalletType4")
    leaf = Group.objects.create(name="LeafZ", group_type=gtype, velos_spendable=30)
    LuantiAccount.objects.create(
        login_name="Player4",
        id_tag="rfid-w4",
        active_wallet=leaf,
        wallet_mode=LuantiAccount.WALLET_FIXED,
    )
    resp = api_client.post(
        "/api/luanti/wallet/withdraw/",
        data=json.dumps(_signed({"player": "Player4", "amount": 8})),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["velos_spendable"] == 22
