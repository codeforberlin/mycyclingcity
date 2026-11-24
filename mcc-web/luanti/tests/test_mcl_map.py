# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

import pytest

from luanti.services.mcl_map import resolve_name

SCAN_JSON = Path(
    "/data/games/mcc/luanti/worlds/mycyclingcity_migrate/mcc_migrator_map.json"
)


@pytest.mark.parametrize(
    "old,new_name",
    [
        ("mcl_doors:door_oak_b_1", "doors:door_wood_a"),
        ("mcl_stairs:slab_oak_top", "stairs:slab_wood"),
        ("mcl_core:andesite", "default:stone"),
        ("mcl_colorblocks:concrete_red", "wool:red"),
        ("mcl_wool:green_carpet", "wool:green"),
        ("mcl_chests:trapped_chest_left", "default:chest"),
        ("mcl_chests:chest_left", "default:chest"),
        ("mcl_chests:chest_right", "default:chest"),
        ("mcl_core:redsandstonesmooth", "default:desert_sandstone"),
        ("mcl_core:sandstonesmooth2", "default:sandstone"),
        ("mcl_farming:potato_5", "default:grass_1"),
        ("mcl_farming:potato_6", "default:grass_1"),
        ("mcl_farming:wheat_6", "default:grass_1"),
        ("mcl_stairs:slab_andesite_smooth_double", "stairs:slab_stone"),
        ("mcl_walls:cobble_2", "walls:cobble"),
    ],
)
def test_resolve_examples(old: str, new_name: str) -> None:
    assert resolve_name(old) == new_name


def test_lua_map_avoids_wrong_colorblocks_prefix() -> None:
    lua = (
        Path(__file__).resolve().parents[2]
        / "luanti_mod"
        / "mcc_migrator"
        / "map.lua"
    )
    text = lua.read_text(encoding="utf-8")
    assert 'sub(1, 17) == "mcl_colorblocks:"' not in text
    assert 'sub(1, 10) == "mcl_panes:pane_"' not in text
    assert "(stair|slab)" not in text


def test_unknown_list_from_last_full_scan_resolves() -> None:
    if not SCAN_JSON.is_file():
        pytest.skip(f"migration scan file missing: {SCAN_JSON}")
    data = json.loads(SCAN_JSON.read_text(encoding="utf-8"))
    unknown = data.get("unknown") or []
    missing = [name for name in unknown if not resolve_name(name)]
    assert missing == [], f"still unmapped: {missing[:20]}"