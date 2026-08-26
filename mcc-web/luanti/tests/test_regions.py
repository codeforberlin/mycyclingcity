# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from api.models import Group, GroupType
from luanti.models import LuantiAccount, LuantiProtectedRegion
from luanti.services.city import build_regions_payload
from luanti.services.http_security import sign_payload
from luanti.services.player_pos import store_player_pos
from luanti.services.region_admin import save_region_from_post
from luanti.services.regions_push import push_protected_regions_to_luanti

User = get_user_model()


@pytest.fixture
def api_client():
    return Client()


def _signed(body: dict, server_id: str = "luanti-1") -> dict:
    payload = dict(body)
    payload["server_id"] = server_id
    payload["timestamp"] = int(time.time())
    payload["signature"] = sign_payload(
        {k: v for k, v in payload.items() if k != "signature"}
    )
    return payload


@pytest.fixture
def region_staff(db):
    user = User.objects.create_user(
        username="rg_admin", password="x", is_staff=True, is_active=True
    )
    for codename in ("access_luanti_city", "manage_luanti_regions"):
        perm = Permission.objects.get(
            codename=codename, content_type__app_label="luanti"
        )
        user.user_permissions.add(perm)
    return user


@pytest.fixture
def top_group(db):
    gtype, _ = GroupType.objects.get_or_create(name="RegionTopType")
    return Group.objects.create(name="TOP-Region", group_type=gtype, parent=None)


@pytest.mark.django_db
def test_region_hierarchy_validation(top_group):
    master = LuantiProtectedRegion.objects.create(
        region_id="master_a",
        world="world",
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=100,
        max_y=50,
        max_z=100,
        assigned_to_group=top_group,
    )
    sub = LuantiProtectedRegion(
        region_id="master_a_sub",
        world="world",
        parent=master,
        min_x=10,
        min_y=0,
        min_z=10,
        max_x=20,
        max_y=20,
        max_z=20,
    )
    sub.full_clean()
    sub.save()

    outside = LuantiProtectedRegion(
        region_id="master_a_out",
        world="world",
        parent=master,
        min_x=-10,
        min_y=0,
        min_z=0,
        max_x=5,
        max_y=10,
        max_z=5,
    )
    with pytest.raises(ValidationError):
        outside.full_clean()


@pytest.mark.django_db
def test_sibling_overlap_rejected():
    master = LuantiProtectedRegion.objects.create(
        region_id="m_ov",
        world="world",
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=50,
        max_y=50,
        max_z=50,
    )
    LuantiProtectedRegion.objects.create(
        region_id="m_ov_a",
        world="world",
        parent=master,
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=20,
        max_y=20,
        max_z=20,
    )
    peer = LuantiProtectedRegion(
        region_id="m_ov_b",
        world="world",
        parent=master,
        min_x=10,
        min_y=0,
        min_z=10,
        max_x=30,
        max_y=20,
        max_z=30,
    )
    with pytest.raises(ValidationError):
        peer.full_clean()


@pytest.mark.django_db
def test_build_regions_payload_includes_members_and_parent():
    account = LuantiAccount.objects.create(login_name="Builder1", id_tag="rfid-b1")
    master = LuantiProtectedRegion.objects.create(
        region_id="city",
        world="world",
        min_x=0,
        min_y=-64,
        min_z=0,
        max_x=10,
        max_y=100,
        max_z=10,
        protect_build=True,
    )
    sub = LuantiProtectedRegion.objects.create(
        region_id="city_plot",
        world="world",
        parent=master,
        min_x=1,
        min_y=-64,
        min_z=1,
        max_x=5,
        max_y=50,
        max_z=5,
        spawn_x=2,
        spawn_y=4,
        spawn_z=2,
    )
    sub.members.add(account)
    payload = build_regions_payload()
    by_id = {r["region_id"]: r for r in payload["regions"]}
    assert by_id["city"]["parent_id"] is None
    assert by_id["city_plot"]["parent_id"] == "city"
    assert by_id["city_plot"]["members"] == ["Builder1"]
    assert by_id["city_plot"]["spawn"] == [2, 4, 2]
    assert "color_rgb" in by_id["city_plot"]
    assert len(by_id["city_plot"]["color_rgb"]) == 3
    assert "outline_enabled" in payload
    assert "enter_hint_enabled" in payload
    assert payload["view_distance"] >= 8


@pytest.mark.django_db
def test_save_region_from_post(region_staff, top_group):
    post = {
        "rg_region_id": "plaza",
        "rg_display_name": "Plaza",
        "rg_world": "world",
        "rg_parent": "",
        "rg_assigned_to_group": str(top_group.pk),
        "rg_min_x": "0",
        "rg_min_y": "-64",
        "rg_min_z": "0",
        "rg_max_x": "32",
        "rg_max_y": "128",
        "rg_max_z": "32",
        "rg_protect_build": "on",
        "rg_enabled": "on",
        "rg_notes": "",
    }

    class _Post(dict):
        def getlist(self, key):
            return []

    region = save_region_from_post(_Post(post), user=region_staff)
    assert region.region_id == "plaza"
    assert region.assigned_to_group_id == top_group.pk


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_HTTP_SHARED_SECRET="test-secret",
    MCC_LUANTI_ALLOWED_SERVER_IDS=["luanti-1"],
)
def test_player_pos_api_stores_coords(api_client, settings):
    settings.MCC_LUANTI_HTTP_SHARED_SECRET = "test-secret"
    request_id = "abc123deadbeef"
    resp = api_client.post(
        reverse("luanti_player_pos"),
        data=json.dumps(
            _signed(
                {
                    "request_id": request_id,
                    "player": "P1",
                    "x": 12,
                    "y": 5,
                    "z": -3,
                }
            )
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    from luanti.models import LuantiPlayerPosReply

    row = LuantiPlayerPosReply.objects.get(request_id=request_id)
    assert (row.x, row.y, row.z) == (12, 5, -3)


@pytest.mark.django_db
def test_fetch_player_pos_reads_cache(monkeypatch):
    from luanti.services import player_pos as pp

    monkeypatch.setattr(
        "luanti.services.bridge_connection.bridge_is_online", lambda: True
    )
    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync",
        lambda msg: (store_player_pos(msg["request_id"], 7, 8, 9) or 1),
    )
    x, y, z = pp.fetch_player_block_pos("PlayerOne", timeout_sec=1.0)
    assert (x, y, z) == (7, 8, 9)


@pytest.mark.django_db
def test_regions_admin_page(client, region_staff):
    client.force_login(region_staff)
    resp = client.get(reverse("admin:luanti_regions"))
    assert resp.status_code == 200
    assert b"Region" in resp.content


@pytest.mark.django_db
def test_push_regions(monkeypatch):
    calls = []

    def _push(msg):
        calls.append(msg)
        return 1

    monkeypatch.setattr(
        "luanti.consumers.LuantiEventConsumer.push_to_all_sync", _push
    )
    LuantiProtectedRegion.objects.create(
        region_id="push_me",
        world="world",
        min_x=0,
        min_y=0,
        min_z=0,
        max_x=1,
        max_y=1,
        max_z=1,
    )
    ok, detail = push_protected_regions_to_luanti()
    assert ok is True
    assert calls and calls[0]["type"] == "REGIONS_UPDATE"
    assert calls[0]["regions"][0]["region_id"] == "push_me"
