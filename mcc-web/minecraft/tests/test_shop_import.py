# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from minecraft.models import MinecraftShopCategory, MinecraftShopItem
from minecraft.services.shop_import import (
    collect_yaml_files,
    esgui_section_from_shop_path,
    import_esgui_catalog,
    item_display_name_from_yaml,
    parse_esgui_shop_items,
    slug_from_filename,
    slug_from_shop_path,
    strip_minecraft_colors,
)


SAMPLE_SHOP_YAML = """
pages:
  page1:
    gui-rows: 6
    title: "Blocks"
    items:
      '1':
        material: stone
        buy: 5.5
        sell: 1
      '2':
        material: minecraft:dirt
        buy: 2
        sell: -1
        display-name: "&aErde"
      '3':
        material: barrier
        sell: 10
"""

DUPLICATE_MATERIAL_SHOP_YAML = """
pages:
  page1:
    items:
      normal_pickaxe:
        material: WOODEN_PICKAXE
        buy: 3
      super_pickaxe:
        material: WOODEN_PICKAXE
        buy: 5
        display-name: "&c&lLösch-Werkzeug"
"""


SAMPLE_SECTION_YAML = """
enable: true
slot: 3
title: "&a&lBaumaterial"
item:
  material: GRASS_BLOCK
  name: "&aBaumaterial"
"""


@pytest.mark.unit
class TestShopImportParsing:
    def test_slug_from_filename(self):
        assert slug_from_filename("Blocks.yml") == "blocks"
        assert slug_from_filename("shops/Food.yaml") == "food"

    def test_nested_shop_paths(self):
        assert esgui_section_from_shop_path("Mobs/spawn_eggs.yml") == "Mobs/spawn_eggs"
        assert slug_from_shop_path("Mobs/spawn_eggs.yml") == "mobs_spawn_eggs"
        assert esgui_section_from_shop_path("building.yml") == "building"

    def test_collect_yaml_files_skips_bak(self, tmp_path):
        (tmp_path / "misc.yml").write_text("pages: {}", encoding="utf-8")
        (tmp_path / "misc.yml.bak").write_text("pages: {}", encoding="utf-8")
        files = collect_yaml_files(tmp_path)
        assert "misc.yml" in files
        assert "misc.yml.bak" not in files
        assert len(files) == 1

    def test_strip_minecraft_colors(self):
        assert strip_minecraft_colors("&a&lErde") == "Erde"

    def test_item_display_name_from_yaml(self):
        assert item_display_name_from_yaml({"display-name": "&c&lTool"}) == "Tool"
        assert item_display_name_from_yaml({"name": "&aErde"}) == "Erde"
        assert item_display_name_from_yaml({"material": "STONE"}) == ""

    def test_parse_esgui_shop_items(self):
        items = parse_esgui_shop_items(SAMPLE_SHOP_YAML)

        assert len(items) == 2
        assert items[0]["material"] == "STONE"
        assert items[0]["buy_price_velos"] == 6
        assert items[0]["esgui_item_key"] == "1"
        assert items[1]["material"] == "DIRT"
        assert items[1]["display_name"] == "Erde"
        assert items[0]["esgui_item_loc"] == "page1.items.1"


@pytest.mark.unit
@pytest.mark.django_db
class TestShopImportService:
    def test_import_esgui_catalog_creates_categories_and_items(self):
        result = import_esgui_catalog(
            shop_files={"Blocks.yml": SAMPLE_SHOP_YAML},
            section_files={"blocks": SAMPLE_SECTION_YAML},
            replace_items=False,
        )

        assert result.ok
        assert result.categories_created == 1
        assert result.items_created == 2

        category = MinecraftShopCategory.objects.get(slug="blocks")
        assert category.name == "Baumaterial"
        assert category.esgui_section == "Blocks"
        assert category.sort_order == 3
        assert category.items.count() == 2

    def test_import_nested_shop_path(self):
        result = import_esgui_catalog(
            shop_files={"Mobs/spawn_eggs.yml": SAMPLE_SHOP_YAML},
            replace_items=False,
        )

        assert result.ok
        category = MinecraftShopCategory.objects.get(slug="mobs_spawn_eggs")
        assert category.esgui_section == "Mobs/spawn_eggs"

    def test_import_duplicate_materials_same_category(self):
        result = import_esgui_catalog(
            shop_files={"tools.yml": DUPLICATE_MATERIAL_SHOP_YAML},
            replace_items=False,
        )

        assert result.ok
        assert result.items_created == 2
        items = list(MinecraftShopItem.objects.order_by("esgui_item_loc"))
        assert len(items) == 2
        assert items[0].material == items[1].material == "WOODEN_PICKAXE"
        assert items[0].esgui_item_loc == "page1.items.normal_pickaxe"
        assert items[1].esgui_item_loc == "page1.items.super_pickaxe"
        assert items[1].display_name == "Lösch-Werkzeug"

    def test_import_esgui_catalog_replace_items(self):
        category = MinecraftShopCategory.objects.create(slug="blocks", name="Old")
        MinecraftShopItem.objects.create(
            category=category,
            material="OLD_ITEM",
            esgui_item_key="old_item",
            esgui_item_loc="page1.items.old_item",
            buy_price_velos=1,
        )

        result = import_esgui_catalog(
            shop_files={"Blocks.yml": SAMPLE_SHOP_YAML},
            replace_items=True,
        )

        assert result.ok
        assert MinecraftShopItem.objects.filter(
            category=category, esgui_item_loc="page1.items.old_item"
        ).count() == 0
        assert category.items.count() == 2
