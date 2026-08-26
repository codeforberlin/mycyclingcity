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
    assert resolve_material("POWERED_RAIL") == "mcl_minecarts:golden_rail"
    assert resolve_material("MINECART") == "mcl_minecarts:minecart"
    assert resolve_material("REDSTONE_TORCH") == "mesecons_torch:mesecon_torch_on"
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


@pytest.mark.django_db
def test_add_registry_items_bulk_to_shop():
    from luanti.services.shop_import_mc import add_registry_items_bulk_to_shop

    replace_registry_items(
        [
            {"name": "mesecons_pistons:piston_normal_off", "kind": "node"},
            {"name": "mesecons_walllever:wall_lever_off", "kind": "node"},
            {"name": "mesecons_torch:redstoneblock", "kind": "node"},
        ],
        clear=True,
    )
    result = add_registry_items_bulk_to_shop(
        item_names=[
            "mesecons_pistons:piston_normal_off",
            "mesecons_walllever:wall_lever_off",
            "mesecons_torch:redstoneblock",
            "not_in_registry:foo",
            "invalid",
            "mesecons_pistons:piston_normal_off",  # dup
        ],
        category_slug="redstone",
        buy_price_velos=5,
    )
    assert result.created == 3
    assert result.updated == 0
    assert result.skipped == 2
    assert "not_in_registry:foo" in result.invalid
    assert "invalid" in result.invalid
    assert LuantiShopItem.objects.filter(category__slug="redstone").count() == 3

    again = add_registry_items_bulk_to_shop(
        item_names=["mesecons_pistons:piston_normal_off"],
        category_slug="redstone",
        buy_price_velos=9,
    )
    assert again.created == 0
    assert again.updated == 1
    assert (
        LuantiShopItem.objects.get(
            category__slug="redstone",
            item_name="mesecons_pistons:piston_normal_off",
        ).buy_price_velos
        == 9
    )


@pytest.mark.django_db
def test_shop_ops_bulk_add_view(client, django_user_model):
    from django.contrib.auth.models import Permission
    from django.urls import reverse

    user = django_user_model.objects.create_user(
        username="shop_op", password="x", is_staff=True, is_active=True
    )
    perm = Permission.objects.get(
        codename="access_luanti_shop", content_type__app_label="luanti"
    )
    user.user_permissions.add(perm)
    client.force_login(user)

    replace_registry_items(
        [
            {"name": "mesecons_noteblock:noteblock", "description": "Note"},
            {"name": "mcl_core:stone", "description": "Stone"},
        ],
        clear=True,
    )
    LuantiShopCategory.objects.create(slug="redstone", name="Redstone", sort_order=1)

    url = reverse("admin:luanti_shop_ops")
    resp = client.get(url)
    assert resp.status_code == 200
    assert b"bulk_add_from_registry" in resp.content

    resp = client.post(
        url,
        {
            "action": "bulk_add_from_registry",
            "item_names": [
                "mesecons_noteblock:noteblock",
                "mcl_core:stone",
            ],
            "category_slug": "redstone",
            "buy_price_velos": "7",
            "only_missing": "1",
        },
        follow=True,
    )
    assert resp.status_code == 200
    assert LuantiShopItem.objects.filter(
        item_name="mesecons_noteblock:noteblock", buy_price_velos=7
    ).exists()
    assert LuantiShopItem.objects.filter(item_name="mcl_core:stone").exists()
