# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest

from luanti.models import (
    LuantiShopCategory,
    LuantiShopCategoryLabel,
    LuantiShopItem,
    LuantiShopItemLabel,
)
from luanti.services.shop import build_catalog_payload
from luanti.services.shop_labels import (
    build_english_to_german_map,
    build_german_to_english_map,
    build_item_search_blob,
    import_english_labels_from_locales,
    import_german_labels_from_locales,
    normalize_language_code,
    normalize_shop_search_text,
    parse_tr_file,
    cleaned_display_name,
    plain_shop_label,
    repair_de_shop_labels,
    resolve_category_display_name,
    resolve_item_display_name,
    set_category_label,
    set_item_label,
    shop_de_label_stats,
    shop_item_search_hits,
    shop_items_missing_de_label,
    sync_category_labels_defaults,
    sync_labels_from_registry,
)
from luanti.services.shop_registry import replace_registry_items


@pytest.mark.django_db
def test_normalize_language_code():
    assert normalize_language_code("de_DE") == "de"
    assert normalize_language_code("en-US") == "en"
    assert normalize_language_code("") == "de"


@pytest.mark.django_db
def test_resolve_item_display_name_fallback():
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        display_name="Legacy",
        buy_price_velos=1,
        stack_size=1,
    )
    LuantiShopItemLabel.objects.create(item=item, language_code="de", display_name="Stein")
    LuantiShopItemLabel.objects.create(item=item, language_code="en", display_name="Stone")
    labels = {"de": "Stein", "en": "Stone"}
    assert resolve_item_display_name(item, "en", labels=labels) == "Stone"
    assert resolve_item_display_name(item, "fr", labels=labels) == "Stein"


@pytest.mark.django_db
def test_build_catalog_payload_lang():
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blocks", enabled=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    set_item_label(item, "de", "Erde", overwrite=True)
    set_item_label(item, "en", "Dirt", overwrite=True)
    de_cat = build_catalog_payload(lang="de")["categories"][0]["items"][0]
    en_cat = build_catalog_payload(lang="en")["categories"][0]["items"][0]
    assert de_cat["display_name"] == "Erde"
    assert en_cat["display_name"] == "Dirt"
    assert de_cat["labels"]["en"] == "Dirt"


@pytest.mark.django_db
def test_sync_labels_from_registry():
    replace_registry_items(
        [{"name": "mcl_core:sand", "description": "Sand", "kind": "node"}],
        clear=True,
    )
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:sand",
        buy_price_velos=1,
        stack_size=1,
    )
    result = sync_labels_from_registry(only_empty=True)
    assert result.created == 1
    assert LuantiShopItemLabel.objects.get(item=item, language_code="de").display_name == "Sand"


@pytest.mark.django_db
def test_parse_tr_and_en_import(tmp_path):
    locale = tmp_path / "mcl_core" / "locale"
    locale.mkdir(parents=True)
    (locale / "mcl_core.de.tr").write_text(
        "# textdomain: mcl_core\nDirt=Erde\n",
        encoding="utf-8",
    )
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=1,
        stack_size=1,
    )
    set_item_label(item, "de", "Erde", overwrite=True)
    de_map = build_german_to_english_map(tmp_path)
    assert de_map.get("Erde") == "Dirt"
    parsed = parse_tr_file(locale / "mcl_core.de.tr")
    assert parsed["Dirt"] == "Erde"
    result = import_english_labels_from_locales(tmp_path, only_empty=True)
    assert result.created == 1
    assert LuantiShopItemLabel.objects.get(item=item, language_code="en").display_name == "Dirt"


@pytest.mark.django_db
def test_category_labels_in_catalog():
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blocks", enabled=True)
    set_category_label(cat, "de", "Blöcke", overwrite=True)
    set_category_label(cat, "en", "Blocks", overwrite=True, sync_legacy_de=False)
    de_payload = build_catalog_payload(lang="de")
    en_payload = build_catalog_payload(lang="en")
    assert de_payload["categories"][0]["name"] == "Blöcke"
    assert en_payload["categories"][0]["name"] == "Blocks"


@pytest.mark.django_db
def test_build_item_search_blob_includes_category_and_holz_alias():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz")
    set_category_label(cat, "de", "Holz", overwrite=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:oak_plank",
        display_name="Eichenbohle",
        buy_price_velos=2,
        stack_size=64,
    )
    set_item_label(item, "de", "Eichenbohle", overwrite=True)
    blob = build_item_search_blob(
        item,
        labels={"de": "Eichenbohle"},
        category=cat,
        category_labels={"de": "Holz"},
    )
    assert "holz" in blob
    assert "eichenbohle" in blob
    assert "oak plank" in blob
    assert normalize_shop_search_text("Holz") in blob


@pytest.mark.django_db
def test_birken_in_display_name_is_in_search_blob():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz", enabled=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:birchwood",
        display_name="Birkenholz",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    set_item_label(item, "de", "Birkenholz", overwrite=True)
    blob = build_item_search_blob(
        item, labels={"de": "Birkenholz"}, category=cat
    )
    assert "birken" in blob


@pytest.mark.django_db
def test_birk_substring_in_birch_search_blob_english_display():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz", enabled=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:birch_stairs",
        display_name="Birch Stairs",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    blob = build_item_search_blob(
        item,
        labels={},
        resolved_display_name="Birch Stairs",
        category=cat,
    )
    assert "birk" in blob
    assert "bir" in blob


@pytest.mark.django_db
def test_birk_matches_birch_item_in_search_blob():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz", enabled=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:birchwood",
        display_name="Birkenholz",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    blob = build_item_search_blob(item, labels={"de": "Birkenholz"}, category=cat)
    assert "birke" in blob
    assert "birk" in blob
    payload = build_catalog_payload(lang="de")
    search = payload["categories"][0]["items"][0]["search"]
    assert "birk" in search


@pytest.mark.django_db
def test_catalog_search_field_matches_holz():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz", enabled=True)
    LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:oak_plank",
        display_name="Eichenbohle",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    payload = build_catalog_payload(lang="de")
    search = payload["categories"][0]["items"][0]["search"]
    assert "holz" in search


@pytest.mark.django_db
def test_plain_shop_label_strips_markup():
    raw = "@1Oak Planks@2 (64)@3"
    assert "Oak" in plain_shop_label(raw) or "Planks" in plain_shop_label(raw)
    assert "@" not in plain_shop_label(raw)


@pytest.mark.django_db
def test_plain_shop_label_mcl_armor_rich_text():
    esc = "\x1b"
    raw = (
        f"{esc}(T@mcl_armor)Chain Boots{esc}E "
        f"{esc}(c@#d0ffd0){esc}(T@mcl_tt)Feet armor{esc}E"
        f"{esc}(c@#fff) {esc}(c@#d0ffd0){esc}(T@mcl_tt)Armor points: {esc}F1{esc}E"
    )
    assert plain_shop_label(raw) == "Chain Boots"
    assert cleaned_display_name(raw) == "Chain Boots"


@pytest.mark.django_db
def test_sync_labels_from_registry_strips_markup():
    replace_registry_items(
        [{"name": "mcl_core:plank", "description": "@1Oak Plank@2", "kind": "node"}],
        clear=True,
    )
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:plank",
        buy_price_velos=1,
        stack_size=1,
    )
    sync_labels_from_registry(only_empty=True)
    label = LuantiShopItemLabel.objects.get(item=item, language_code="de").display_name
    assert "@" not in label


@pytest.mark.django_db
def test_repair_de_shop_labels_scrubs_markup(tmp_path):
    esc = "\x1b"
    rich = f"{esc}(T@mcl_armor)Chain Boots{esc}E {esc}(T@mcl_tt)Feet armor{esc}E"
    replace_registry_items(
        [{"name": "mcl_armor:boots_chain", "description": rich, "kind": "item"}],
        clear=True,
    )
    locale = tmp_path / "mcl_armor" / "locale"
    locale.mkdir(parents=True)
    (locale / "mcl_armor.de.tr").write_text("Chain Boots=Kettenstiefel\n", encoding="utf-8")
    cat = LuantiShopCategory.objects.create(slug="armor", name="Armor")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_armor:boots_chain",
        buy_price_velos=40,
        stack_size=1,
    )
    set_item_label(item, "de", rich[:128], overwrite=True)
    result = repair_de_shop_labels(tmp_path, apply_locales=True)
    assert result.updated == 1
    assert (
        LuantiShopItemLabel.objects.get(item=item, language_code="de").display_name
        == "Kettenstiefel"
    )


@pytest.mark.django_db
def test_import_german_labels_from_locales(tmp_path):
    locale = tmp_path / "mcl_core" / "locale"
    locale.mkdir(parents=True)
    (locale / "mcl_core.de.tr").write_text("Dirt=Erde\n", encoding="utf-8")
    replace_registry_items(
        [{"name": "mcl_core:dirt", "description": "Dirt", "kind": "node"}],
        clear=True,
    )
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:dirt",
        buy_price_velos=1,
        stack_size=1,
    )
    en_de = build_english_to_german_map(tmp_path)
    assert en_de.get("Dirt") == "Erde"
    result = import_german_labels_from_locales(tmp_path, only_empty=True)
    assert result.created == 1
    assert LuantiShopItemLabel.objects.get(item=item, language_code="de").display_name == "Erde"


@pytest.mark.django_db
def test_shop_item_search_hits_holz():
    cat = LuantiShopCategory.objects.create(slug="wood", name="Holz", enabled=True)
    set_category_label(cat, "de", "Holz", overwrite=True)
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:oak_plank",
        display_name="Eichenbohle",
        buy_price_velos=2,
        stack_size=64,
        enabled=True,
    )
    set_item_label(item, "de", "Eichenbohle", overwrite=True)
    hits = shop_item_search_hits("holz")
    assert any(h["item_name"] == "mcl_core:oak_plank" for h in hits)
    assert shop_item_search_hits("") == []


@pytest.mark.django_db
def test_shop_items_missing_de_label():
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    ok = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:stone",
        buy_price_velos=1,
        stack_size=1,
    )
    missing = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:unknown_block",
        buy_price_velos=1,
        stack_size=1,
    )
    set_item_label(ok, "de", "Stein", overwrite=True)
    rows = shop_items_missing_de_label()
    ids = {r["item_id"] for r in rows}
    assert missing.pk in ids
    assert ok.pk not in ids


@pytest.mark.django_db
def test_shop_de_label_stats():
    cat = LuantiShopCategory.objects.create(slug="misc", name="Misc")
    item = LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:a",
        buy_price_velos=1,
        stack_size=1,
    )
    LuantiShopItem.objects.create(
        category=cat,
        item_name="mcl_core:b",
        buy_price_velos=1,
        stack_size=1,
    )
    set_item_label(item, "de", "A", overwrite=True)
    stats = shop_de_label_stats()
    assert stats.shop_items == 2
    assert stats.de_labels_nonempty == 1
    assert stats.de_labels_missing == 1


@pytest.mark.django_db
def test_sync_category_labels_defaults():
    cat = LuantiShopCategory.objects.create(slug="tools", name="Tools")
    sync_category_labels_defaults(only_empty=True)
    assert LuantiShopCategoryLabel.objects.get(category=cat, language_code="de").display_name == "Werkzeuge"
    assert resolve_category_display_name(cat, "de") == "Werkzeuge"
