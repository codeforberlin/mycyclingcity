# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest

from luanti.models import LuantiRegisteredItem
from luanti.services.shop_icon import (
    ICON_MISSING,
    ICON_OK,
    ICON_UNCERTAIN,
    classify_registry_icon,
    icon_hint_for_item_name,
)
from luanti.services.shop_registry import replace_registry_items


@pytest.mark.django_db
def test_classify_icon_with_inventory_image():
    reg = LuantiRegisteredItem(
        item_name="mcl_core:stone",
        inventory_image="default_stone.png",
        drawtype="normal",
    )
    assert classify_registry_icon(reg) == ICON_OK


@pytest.mark.django_db
def test_classify_icon_mesh_without_inventory():
    reg = LuantiRegisteredItem(
        item_name="mcl_chests:blue_shulker_box",
        drawtype="mesh",
        inventory_image="",
    )
    assert classify_registry_icon(reg) == ICON_UNCERTAIN


@pytest.mark.django_db
def test_mcl_stairs_mesh_still_ok_in_shop():
    reg = LuantiRegisteredItem(
        item_name="mcl_stairs:stair_oak",
        drawtype="mesh",
        inventory_image="",
        not_in_creative_inventory=False,
    )
    assert classify_registry_icon(reg) == ICON_OK
    inner = LuantiRegisteredItem(
        item_name="mcl_stairs:stair_oak_inner",
        drawtype="nodebox",
        inventory_image="",
        not_in_creative_inventory=True,
    )
    assert classify_registry_icon(inner) == ICON_OK


@pytest.mark.django_db
def test_classify_icon_missing_registry():
    assert classify_registry_icon(None) == ICON_MISSING


@pytest.mark.django_db
def test_replace_registry_stores_icon_fields():
    replace_registry_items(
        [
            {
                "name": "mcl_core:dirt",
                "description": "Dirt",
                "kind": "node",
                "drawtype": "normal",
                "inventory_image": "default_dirt.png",
                "wield_image": "",
                "not_in_creative_inventory": False,
            }
        ],
        clear=True,
    )
    reg = LuantiRegisteredItem.objects.get(item_name="mcl_core:dirt")
    assert reg.inventory_image == "default_dirt.png"
    hint = icon_hint_for_item_name("mcl_core:dirt", {reg.item_name: reg})
    assert hint["icon_status"] == ICON_OK
