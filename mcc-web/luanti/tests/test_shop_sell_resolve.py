# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from luanti.services.shop_sell_resolve import (
    credit_item_name_candidates,
    door_shop_credit_item_name,
    shop_credit_item_name,
    stair_shop_credit_item_name,
)


def test_door_shop_credit_item_name_uses_standard_door():
    assert door_shop_credit_item_name("mcl_doors:acacia_door_b_1") == "doors:door_wood_a"
    assert door_shop_credit_item_name("mcl_doors:acacia_door_t_1") == "doors:door_wood_b"
    assert shop_credit_item_name("mcl_doors:wooden_door_b_1") == "doors:door_wood_a"
    assert shop_credit_item_name("default:stone") == "default:stone"


def test_stair_shop_credit_item_name_uses_standard_corner():
    inner = "mcl_stairs:stair_acaciawood_inner"
    assert stair_shop_credit_item_name(inner) == "stairs:stair_inner_acacia_wood"
    assert "stairs:stair_inner_acacia_wood" in credit_item_name_candidates(inner)


def test_dug_cobble_can_spend_stone_credit():
    names = credit_item_name_candidates("default:cobble")
    assert names[0] == "default:cobble"
    assert "default:stone" in names
    legacy = credit_item_name_candidates("mcl_core:cobble")
    assert "mcl_core:stone" in legacy
    assert "default:stone" in legacy
