# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest

from luanti.models import LuantiShopCategory, LuantiShopItem
from luanti.services.material_map import candidates_for_material, resolve_material
from luanti.services.shop_import_mc import add_registry_item_to_shop, import_minecraft_shop_catalog
from luanti.services.shop_registry import replace_registry_items
from minecraft.models import MinecraftShopCategory, MinecraftShopItem


@pytest.mark.django_db
def test_resolve_material_tools_and_overrides():
    assert resolve_material("DIAMOND_PICKAXE") == "mcl_tools:pick_diamond"
    assert resolve_material("IRON_CHESTPLATE") == "mcl_armor:chestplate_iron"
    assert resolve_material("COBBLESTONE") == "mcl_core:cobble"
    assert resolve_material("OAK_PLANKS") == "mcl_core:wood"
    assert "mcl_tools:pick_gold" in candidates_for_material("GOLDEN_PICKAXE")


@pytest.mark.django_db
def test_resolve_material_respects_registry():
    registry = {"mcl_core:stone", "mcl_tools:pick_diamond"}
    assert resolve_material("STONE", registry=registry) == "mcl_core:stone"
    assert resolve_material("DIAMOND_SWORD", registry=registry) is None


@pytest.mark.django_db
def test_import_minecraft_shop_catalog_maps_items():
    cat = MinecraftShopCategory.objects.create(
        slug="blocks", name="Blöcke", sort_order=1, enabled=True
    )
    MinecraftShopItem.objects.create(
        category=cat,
        material="STONE",
        display_name="Stein",
        esgui_item_loc="page1.items.stone",
        buy_price_velos=5,
        stack_size=64,
        sort_order=1,
        enabled=True,
    )
    MinecraftShopItem.objects.create(
        category=cat,
        material="TOTALLY_FAKE_ITEM_XYZ",
        display_name="Fake",
        esgui_item_loc="page1.items.fake",
        buy_price_velos=9,
        enabled=True,
    )
    # Without registry: heuristic maps STONE; fake still gets a candidate and is imported.
    result = import_minecraft_shop_catalog()
    assert result.categories_created == 1
    assert LuantiShopItem.objects.filter(item_name="mcl_core:stone").exists()

    LuantiShopItem.objects.all().delete()
    LuantiShopCategory.objects.all().delete()
    replace_registry_items(
        [{"name": "mcl_core:stone", "description": "Stone", "kind": "node"}],
        clear=True,
    )
    result2 = import_minecraft_shop_catalog()
    assert LuantiShopItem.objects.filter(item_name="mcl_core:stone").count() == 1
    assert "TOTALLY_FAKE_ITEM_XYZ" in result2.unmapped


@pytest.mark.django_db
def test_add_registry_item_to_shop():
    replace_registry_items(
        [{"name": "mcl_core:dirt", "kind": "node"}],
        clear=True,
    )
    item = add_registry_item_to_shop(
        item_name="mcl_core:dirt",
        category_slug="misc",
        buy_price_velos=2,
        display_name="Erde",
    )
    assert item.item_name == "mcl_core:dirt"
    assert item.buy_price_velos == 2
    assert LuantiShopCategory.objects.filter(slug="misc").exists()
