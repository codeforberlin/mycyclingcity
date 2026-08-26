# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import (
    LuantiAccount,
    LuantiSession,
    LuantiShopCategory,
    LuantiShopItem,
    LuantiStation,
)
from luanti.services.http_security import sign_payload
from luanti.services.session_control import start_session

User = get_user_model()


@pytest.fixture
def api_client():
    return Client()


def _signed(body: dict, server_id: str = "luanti-1") -> dict:
    payload = dict(body)
    payload["server_id"] = server_id
    payload["timestamp"] = int(time.time())
    payload["signature"] = sign_payload({k: v for k, v in payload.items() if k != "signature"})
    return payload


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_heartbeat_drains_queued_city_preset(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.consumers import LuantiEventConsumer
    from luanti.models import LuantiPendingCommand

    assert LuantiEventConsumer.push_to_all_sync(
        {"type": "RUN_CITY_PRESET", "slug": "daytime", "steps": [{"op": "set_time", "value": 6000}]}
    ) == 1
    assert LuantiPendingCommand.objects.filter(delivered_at__isnull=True).count() == 1

    resp = api_client.post(
        "/api/luanti/heartbeat/",
        data=json.dumps(_signed({})),
        content_type="application/json",
    )
    data = resp.json()
    assert data["ok"] is True
    assert len(data["commands"]) == 1
    assert data["commands"][0]["slug"] == "daytime"
    assert LuantiPendingCommand.objects.filter(delivered_at__isnull=True).count() == 0


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_heartbeat_reconciles_offline_paused_session(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    account = LuantiAccount.objects.create(login_name="Orphan1", id_tag="Orphan1", is_active=True)
    session = start_session(account=account, duration=20)
    from luanti.services.session_control import pause_session

    pause_session(session)
    resp = api_client.post(
        "/api/luanti/heartbeat/",
        data=json.dumps(_signed({"players": [], "player_count": 0})),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ended_offline"] == 1
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_heartbeat_empty_players_object_from_lua(api_client, settings):
    """Lua write_json turns empty arrays into {} — still reconcile via player_count."""
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    account = LuantiAccount.objects.create(login_name="Orphan2", id_tag="Orphan2", is_active=True)
    session = start_session(account=account, duration=20)
    resp = api_client.post(
        "/api/luanti/heartbeat/",
        data=json.dumps(_signed({"players": {}, "player_count": 0})),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ended_offline"] == 1
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_session_join_inventory_modes(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    start_session(account=account, mode="play")
    resp = api_client.post(
        "/api/luanti/session/join/",
        data=json.dumps(_signed({"player": "Schule1"})),
        content_type="application/json",
    )
    data = resp.json()
    assert data["ok"] is True
    assert data["wait"] is False
    assert data["mode"] == "play"
    assert "shout" in data["privs"]
    assert "interact" in data["privs"]


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_session_set_mode_saves_inventory_to_old_mode(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.models import LuantiPlayerInventory

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build", "watch"],
        default_mode="play",
    )
    session = start_session(account=account, mode="play")
    items = [{"name": "mcl_tools:pick_iron", "count": 1, "wear": 0}]
    resp = api_client.post(
        "/api/luanti/session/set-mode/",
        data=json.dumps(
            _signed({"player": "Schule1", "mode": "build", "inventory": items})
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] == "build"
    session.refresh_from_db()
    assert session.mode == "build"
    play_inv = LuantiPlayerInventory.objects.get(account=account, mode="play")
    assert play_inv.payload == items
    build_inv = LuantiPlayerInventory.objects.get(account=account, mode="build")
    assert build_inv.payload == []


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_session_leave_saves_inventory(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.models import LuantiPlayerInventory

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    session = start_session(account=account, mode="play")
    items = [{"name": "mcl_tools:pick_iron", "count": 1, "wear": 0}]
    resp = api_client.post(
        "/api/luanti/session/leave/",
        data=json.dumps(_signed({"player": "Schule1", "inventory": items})),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ended"] is True
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_FINISHED
    inv = LuantiPlayerInventory.objects.get(account=account, mode="play")
    assert inv.payload == items
    assert inv.revision == 1


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_session_leave_saves_empty_inventory_from_lua_object(api_client, settings):
    """Lua write_json encodes empty table as {}; must still clear stored inventory."""
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.models import LuantiPlayerInventory
    from luanti.services.session_control import get_or_create_inventory

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    start_session(account=account, mode="play")
    inv = get_or_create_inventory(account, "play")
    inv.payload = [{"name": "mcl_core:dirt", "count": 2}]
    inv.revision = 2
    inv.save(update_fields=["payload", "revision"])
    resp = api_client.post(
        "/api/luanti/session/leave/",
        data=json.dumps(
            _signed({"player": "Schule1", "inventory": {}, "inventory_count": 0})
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ended"] is True
    inv.refresh_from_db()
    assert inv.payload == []
    assert inv.revision == 3


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_inventory_sync_accepts_lua_empty_object(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.models import LuantiPlayerInventory
    from luanti.services.session_control import get_or_create_inventory

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play"],
        default_mode="play",
    )
    start_session(account=account, mode="play")
    inv = get_or_create_inventory(account, "play")
    inv.payload = [{"name": "mcl_core:stone", "count": 1}]
    inv.save(update_fields=["payload"])
    resp = api_client.post(
        "/api/luanti/inventory/sync/",
        data=json.dumps(
            _signed(
                {
                    "player": "Schule1",
                    "mode": "play",
                    "inventory": {},
                    "inventory_count": 0,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    inv.refresh_from_db()
    assert inv.payload == []


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_admin_kick_queues_without_ending_session(api_client, settings):
    """Admin kick must keep session active so leave can persist inventory."""
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    from luanti.models import LuantiPendingCommand

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    session = start_session(account=account, mode="play")
    user = User.objects.create_user(username="op", password="x", is_staff=True, is_superuser=True)
    api_client.force_login(user)
    resp = api_client.post(
        reverse("admin:luanti_sessions"),
        {"action": "kick", "session_id": str(session.pk)},
    )
    assert resp.status_code == 302
    session.refresh_from_db()
    assert session.status == LuantiSession.STATUS_ACTIVE
    pending = LuantiPendingCommand.objects.filter(delivered_at__isnull=True).order_by("-id").first()
    assert pending is not None
    assert pending.payload.get("type") == "KICK_PLAYER"
    assert pending.payload.get("player") == "Schule1"


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_session_join_marks_waiting_without_session(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    resp = api_client.post(
        "/api/luanti/session/join/",
        data=json.dumps(_signed({"player": "Schule1"})),
        content_type="application/json",
    )
    data = resp.json()
    assert data["ok"] is True
    assert data["wait"] is True
    from luanti.models import LuantiWaitingPlayer

    assert LuantiWaitingPlayer.objects.filter(login_name="Schule1").exists()

    start_session(account=LuantiAccount.objects.get(login_name="Schule1"), mode="play")
    resp2 = api_client.post(
        "/api/luanti/session/join/",
        data=json.dumps(_signed({"player": "Schule1"})),
        content_type="application/json",
    )
    data2 = resp2.json()
    assert data2["wait"] is False
    assert not LuantiWaitingPlayer.objects.filter(login_name="Schule1").exists()


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_shop_buy_sell(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    gtype, _ = GroupType.objects.get_or_create(name="TestType")
    group = Group.objects.create(
        name="TeamL1",
        group_type=gtype,
        luanti_username="Schule1",
        velos_spendable=100,
    )
    LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        assigned_to_group=group,
    )
    cat = LuantiShopCategory.objects.create(slug="tools", name="Tools")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:diamond",
        buy_price_velos=10,
        stack_size=1,
    )
    resp = api_client.post(
        "/api/luanti/shop/buy/",
        data=json.dumps(
            _signed(
                {
                    "player": "Schule1",
                    "item_id": item.pk,
                    "quantity": 2,
                    "client_tx_id": "tx-buy-1",
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    group.refresh_from_db()
    assert group.velos_spendable == 80

    resp = api_client.post(
        "/api/luanti/shop/sell/",
        data=json.dumps(
            _signed(
                {
                    "player": "Schule1",
                    "item_name": "mcl_core:diamond",
                    "quantity": 1,
                    "client_tx_id": "tx-sell-1",
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    group.refresh_from_db()
    assert group.velos_spendable == 90


@pytest.mark.django_db
def test_provision_password_enqueues_set_password():
    from luanti.models import LuantiPendingCommand
    from luanti.services.passwords import provision_account_password

    account = LuantiAccount.objects.create(login_name="Schule1", id_tag="rfid-1")
    pw = provision_account_password(account, "TestPass1")
    account.refresh_from_db()
    assert pw == "TestPass1"
    assert account.login_password == "TestPass1"
    assert account.password_provisioned is True
    pending = LuantiPendingCommand.objects.filter(delivered_at__isnull=True).order_by("-id").first()
    assert pending is not None
    assert pending.payload["type"] == "SET_PASSWORD"
    assert pending.payload["player"] == "Schule1"
    assert pending.payload["password"] == "TestPass1"


@pytest.mark.django_db
def test_station_payload_uses_account_login_password():
    from luanti.services.stations import station_desired_payload

    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        login_password="Secret99",
    )
    station = LuantiStation.objects.create(
        name="PC1",
        default_account=account,
        desired_config={"password": "ignored-fallback"},
    )
    payload = station_desired_payload(station)
    assert payload["account"]["login_name"] == "Schule1"
    assert payload["account"]["password"] == "Secret99"


@pytest.mark.django_db
def test_station_config_requires_key(api_client):
    station = LuantiStation.objects.create(name="PC1")
    resp = api_client.get("/api/luanti/station/config/")
    assert resp.status_code == 403
    resp = api_client.get(
        "/api/luanti/station/config/",
        HTTP_X_STATION_KEY=station.api_key,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.django_db
def test_control_requires_perm(api_client):
    user = User.objects.create_user(username="op", password="x", is_staff=True)
    api_client.force_login(user)
    resp = api_client.get(reverse("admin:luanti_control"))
    assert resp.status_code == 302
    perm = Permission.objects.get(codename="access_luanti_control", content_type__app_label="luanti")
    user.user_permissions.add(perm)
    resp = api_client.get(reverse("admin:luanti_control"))
    assert resp.status_code == 200
