# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest
from django.utils import timezone

from luanti.models import LuantiRegisteredItem
from luanti.services.shop_plan_ghost import (
    PLAN_GHOST_FALLBACK,
    PLAN_GHOST_PREVIEW_SHAPE,
    PLAN_GHOST_SHAPE,
    PLAN_GHOST_UNKNOWN,
    plan_ghost_hint_for_item_name,
    resolve_plan_ghost_status,
)
from luanti.services.shop_registry import replace_registry_items, update_plan_ghost_status


@pytest.mark.django_db
def test_replace_registry_stores_plan_ghost():
    replace_registry_items(
        [
            {
                "name": "mcl_stairs:slab_concrete_green",
                "description": "Green slab",
                "kind": "node",
                "drawtype": "nodebox",
                "plan_ghost_status": "shape",
                "plan_ghost_detail": "",
            }
        ],
        clear=True,
    )
    reg = LuantiRegisteredItem.objects.get(item_name="mcl_stairs:slab_concrete_green")
    assert reg.plan_ghost_status == "shape"
    assert reg.plan_ghost_checked_at is not None


@pytest.mark.django_db
def test_update_plan_ghost_status_partial():
    LuantiRegisteredItem.objects.create(
        item_name="mcl_core:stone",
        kind="node",
        drawtype="normal",
    )
    saved = update_plan_ghost_status(
        [
            {
                "item_name": "mcl_core:stone",
                "plan_ghost_status": "fallback",
                "plan_ghost_detail": "drawtype=liquid",
            }
        ]
    )
    assert saved == 1
    reg = LuantiRegisteredItem.objects.get(item_name="mcl_core:stone")
    assert reg.plan_ghost_status == "fallback"
    assert reg.plan_ghost_detail == "drawtype=liquid"


@pytest.mark.django_db
def test_plan_ghost_hint_uses_stored_status():
    reg = LuantiRegisteredItem.objects.create(
        item_name="mcl_core:dirt",
        kind="node",
        drawtype="normal",
        plan_ghost_status="shape",
        plan_ghost_checked_at=timezone.now(),
    )
    hint = plan_ghost_hint_for_item_name("mcl_core:dirt", {reg.item_name: reg})
    assert hint["plan_ghost_status"] == "shape"
    assert "Form-Klon" in hint["plan_ghost_label"]


@pytest.mark.django_db
def test_legacy_registry_shape_without_verify_is_preview():
    reg = LuantiRegisteredItem.objects.create(
        item_name="mcl_stairs:slab_brick_block",
        kind="node",
        drawtype="nodebox",
        plan_ghost_status="shape",
        plan_ghost_detail="registry_preview",
    )
    assert resolve_plan_ghost_status(reg) == PLAN_GHOST_PREVIEW_SHAPE


@pytest.mark.django_db
def test_plan_ghost_heuristic_when_empty():
    reg = LuantiRegisteredItem.objects.create(
        item_name="mcl_core:lava_source",
        kind="node",
        drawtype="liquid",
    )
    assert resolve_plan_ghost_status(reg) == PLAN_GHOST_FALLBACK
    reg2 = LuantiRegisteredItem.objects.create(
        item_name="mcl_core:stone",
        kind="node",
        drawtype="normal",
    )
    assert resolve_plan_ghost_status(reg2) == PLAN_GHOST_PREVIEW_SHAPE
    assert resolve_plan_ghost_status(None) == PLAN_GHOST_UNKNOWN
