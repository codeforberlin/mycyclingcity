# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse

from luanti.models import LuantiAccount, LuantiCityPreset, LuantiPendingCommand
from luanti.services.preset_steps import parse_steps_text, steps_to_text, validate_steps
from luanti.services.session_bootstrap import push_session_bootstrap
from luanti.services.session_control import start_session

User = get_user_model()


def test_parse_steps_text_roundtrip():
    text = "set_weather clear\nset_time 6000\nchat Es ist Tag.\n"
    steps = parse_steps_text(text)
    assert steps == [
        {"op": "set_weather", "value": "clear"},
        {"op": "set_time", "value": 6000},
        {"op": "chat", "message": "Es ist Tag."},
    ]
    errors, _ = validate_steps(steps)
    assert errors == []
    assert "set_time 6000" in steps_to_text(steps)


def test_parse_steps_json_line():
    steps = parse_steps_text('{"op":"set_time","value":12000}\n')
    assert steps[0]["value"] == 12000


@pytest.mark.django_db
@override_settings(
    MCC_LUANTI_SESSION_BOOTSTRAP_ENABLED=True,
    MCC_LUANTI_SESSION_BOOTSTRAP_PRESET_SLUG="session-bootstrap",
)
def test_session_start_queues_bootstrap():
    LuantiCityPreset.objects.create(
        slug="session-bootstrap",
        name="Bootstrap",
        steps=[{"op": "set_time", "value": 6000}],
        enabled=True,
        is_system=True,
        requires_confirmation=False,
    )
    account = LuantiAccount.objects.create(
        login_name="Schule1",
        id_tag="rfid-1",
        allowed_modes=["play", "build"],
        default_mode="play",
    )
    before = LuantiPendingCommand.objects.count()
    start_session(account=account, mode="play")
    assert LuantiPendingCommand.objects.count() == before + 1
    pending = LuantiPendingCommand.objects.order_by("-id").first()
    assert pending.payload["type"] == "RUN_CITY_PRESET"
    assert pending.payload["slug"] == "session-bootstrap"


@pytest.mark.django_db
@override_settings(MCC_LUANTI_SESSION_BOOTSTRAP_ENABLED=False)
def test_push_bootstrap_disabled():
    ok, msg = push_session_bootstrap()
    assert ok is False
    assert msg == "disabled"


@pytest.mark.django_db
def test_preset_editor_create_and_delete():
    user = User.objects.create_user(
        username="preset-op", password="x", is_staff=True, is_superuser=True
    )
    client = Client()
    client.force_login(user)
    resp = client.post(
        reverse("admin:luanti_preset_add"),
        {
            "name": "Mittag",
            "slug": "noon-test",
            "category": "world",
            "sort_order": "15",
            "enabled": "on",
            "description": "Test",
            "steps": "set_weather clear\nset_time 6000\nchat Mittag",
            "requires_confirmation": "on",
            "action": "save",
            "next": reverse("admin:luanti_preset_list"),
        },
    )
    assert resp.status_code == 302
    preset = LuantiCityPreset.objects.get(slug="noon-test")
    assert preset.step_count == 3
    resp = client.post(reverse("admin:luanti_preset_delete", kwargs={"preset_id": preset.pk}))
    assert resp.status_code == 302
    assert not LuantiCityPreset.objects.filter(slug="noon-test").exists()


@pytest.mark.django_db
def test_preset_list_with_city_and_change_perm():
    user = User.objects.create_user(username="editor", password="x", is_staff=True)
    for codename in ("access_luanti_city", "change_luanticitypreset", "add_luanticitypreset"):
        perm = Permission.objects.get(codename=codename, content_type__app_label="luanti")
        user.user_permissions.add(perm)
    client = Client()
    client.force_login(user)
    resp = client.get(reverse("admin:luanti_preset_list"))
    assert resp.status_code == 200
