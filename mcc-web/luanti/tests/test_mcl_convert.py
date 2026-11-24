# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from luanti.models import (
    LuantiAccount,
    LuantiPlayerInventory,
    LuantiRegisteredItem,
    LuantiShopCategory,
    LuantiShopItem,
)
from luanti.services.mcl_convert import apply_conversion, build_report


def _write_map(tmp_path: Path, entries, unknown=None) -> None:
    world = tmp_path / "worlds" / "city"
    world.mkdir(parents=True)
    payload = {"entries": entries, "unknown": unknown or []}
    (world / "mcc_migrator_map.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.django_db
def test_convert_renames_shop_and_is_idempotent(settings, tmp_path):
    settings.MCC_LUANTI_SERVER_DIR = str(tmp_path)
    _write_map(
        tmp_path,
        [{"old": "mcl_core:stone", "new": "default:stone", "param2_rule": "keep"}],
    )
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blöcke")
    LuantiShopItem.objects.create(
        category=cat, item_name="mcl_core:stone", buy_price_velos=3
    )
    LuantiRegisteredItem.objects.create(item_name="mcl_core:stone", kind="node")
    account = LuantiAccount.objects.create(login_name="ada")
    LuantiPlayerInventory.objects.create(
        account=account,
        mode=LuantiAccount.MODE_PLAY,
        payload=[{"name": "mcl_core:stone", "count": 2, "slot": 1}],
    )

    report = build_report("city")
    assert report.counts["shop"] == 1
    assert not report.blocked

    applied = apply_conversion("city")
    assert applied.applied
    assert LuantiShopItem.objects.get().item_name == "default:stone"
    assert LuantiRegisteredItem.objects.filter(pk="default:stone").exists()
    inv = LuantiPlayerInventory.objects.get()
    assert inv.payload[0]["name"] == "default:stone"

    again = apply_conversion("city")
    assert again.applied
    assert LuantiShopItem.objects.count() == 1
    assert LuantiShopItem.objects.get().item_name == "default:stone"


@pytest.mark.django_db
def test_convert_refuses_shop_unique_conflict(settings, tmp_path):
    settings.MCC_LUANTI_SERVER_DIR = str(tmp_path)
    _write_map(
        tmp_path,
        [
            {"old": "mcl_core:stone", "new": "default:stone"},
            {"old": "mcl_core:bedrock", "new": "default:obsidian"},
        ],
    )
    cat = LuantiShopCategory.objects.create(slug="blocks", name="Blöcke")
    LuantiShopItem.objects.create(category=cat, item_name="mcl_core:stone", buy_price_velos=1)
    LuantiShopItem.objects.create(category=cat, item_name="default:stone", buy_price_velos=2)
    report = build_report("city")
    assert report.conflicts
    assert not apply_conversion("city").applied
    assert LuantiShopItem.objects.filter(item_name="mcl_core:stone").exists()


@pytest.mark.django_db
def test_command_refuses_unknown(settings, tmp_path):
    settings.MCC_LUANTI_SERVER_DIR = str(tmp_path)
    _write_map(tmp_path, [], unknown=["mcl_color_blocks:concrete_red"])
    with pytest.raises(CommandError):
        call_command("luanti_convert_from_mineclonia", "--world", "city", "--apply")
