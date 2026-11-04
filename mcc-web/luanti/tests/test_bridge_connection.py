# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from luanti.models import LuantiBridgeConnection
from luanti.services.bridge_connection import (
    get_connected_server_ids,
    mark_all_bridges_disconnected,
    mark_bridge_connected,
)

User = get_user_model()


@pytest.fixture
def control_client(db):
    user = User.objects.create_user(username="luanti_op", password="x", is_staff=True)
    perm = Permission.objects.get(codename="access_luanti_control", content_type__app_label="luanti")
    user.user_permissions.add(perm)
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_mark_all_bridges_disconnected_clears_connected_rows():
    mark_bridge_connected("luanti-1")
    mark_bridge_connected("luanti-2")
    assert get_connected_server_ids() == ["luanti-1", "luanti-2"]

    updated = mark_all_bridges_disconnected()
    assert updated == 2
    assert get_connected_server_ids() == []
    assert not LuantiBridgeConnection.objects.filter(is_connected=True).exists()


@pytest.mark.django_db
def test_control_bridge_offline_when_server_stopped_despite_fresh_heartbeat(
    control_client, monkeypatch
):
    mark_bridge_connected("luanti-1")
    assert get_connected_server_ids() == ["luanti-1"]

    monkeypatch.setattr(
        "luanti.admin_views._get_luanti_server_status",
        lambda: {
            "running": False,
            "output": "Luanti stopped",
            "error": "",
            "dir": "",
            "world": "mycyclingcity",
            "log": "",
        },
    )

    resp = control_client.get(reverse("admin:luanti_control"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Bridge offline" in content or "Bridge offline – kein Heartbeat/WebSocket." in content
    assert "getrennt" in content


@pytest.mark.django_db
def test_luanti_action_stop_marks_bridges_disconnected(control_client, monkeypatch):
    mark_bridge_connected("luanti-1")
    LuantiBridgeConnection.objects.filter(pk="luanti-1").update(
        last_seen_at=timezone.now()
    )

    monkeypatch.setattr(
        "luanti.admin_views._run_luanti_script",
        lambda action, timeout=60: {
            "ok": True,
            "running": False,
            "output": "Luanti stopped",
            "error": "",
        },
    )

    resp = control_client.post(
        reverse("admin:luanti_action", kwargs={"action": "server-stop"}),
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["success"] is True
    assert get_connected_server_ids() == []
    row = LuantiBridgeConnection.objects.get(pk="luanti-1")
    assert row.is_connected is False
