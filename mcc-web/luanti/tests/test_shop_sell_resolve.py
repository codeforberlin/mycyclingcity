# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from luanti.services.shop_sell_resolve import (
    credit_item_name_candidates,
    door_shop_credit_item_name,
    shop_credit_item_name,
    stair_shop_credit_item_name,
)


def test_door_shop_credit_item_name_normalizes_world_halves():
    craft = "mcl_doors:acacia_door"
    assert door_shop_credit_item_name(craft) == craft
    assert door_shop_credit_item_name("mcl_doors:acacia_door_b_1") == craft
    assert door_shop_credit_item_name("mcl_doors:acacia_door_t_1") == craft
    assert shop_credit_item_name("mcl_doors:wooden_door_b_0") == "mcl_doors:wooden_door"


def test_stair_shop_credit_item_name_normalizes_inner():
    inner = "mcl_stairs:stair_acaciawood_inner"
    assert stair_shop_credit_item_name(inner) == "mcl_stairs:stair_acaciawood"


def test_stair_inner_outer_credit_aliases():
    base = "mcl_stairs:stair_acaciawood"
    inner = "mcl_stairs:stair_acaciawood_inner"
    outer = "mcl_stairs:stair_acaciawood_outer"
    assert inner in credit_item_name_candidates(base)
    assert outer in credit_item_name_candidates(base)
    assert base in credit_item_name_candidates(inner)
    assert base in credit_item_name_candidates(outer)
