# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from collections import Counter

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import (
    MinecraftShopCategory,
    MinecraftShopItem,
    MinecraftShopPurchaseCredit,
    MinecraftTeamRegistration,
)
from minecraft.services.shop_inventory_credit import (
    add_material_credits_for_team,
    parse_inventory_counts_from_snbt,
    parse_online_players_from_list,
)


@pytest.mark.unit
class TestInventorySnbtParse:
    def test_parses_modern_count_format(self):
        snbt = (
            '[{Slot: 0b, id: "minecraft:dirt", count: 64}, '
            '{Slot: 1b, id: "minecraft:stone", count: 3}, '
            '{Slot: 2b, id: "minecraft:dirt", count: 10}]'
        )
        counts = parse_inventory_counts_from_snbt(snbt)
        assert counts == Counter({"DIRT": 74, "STONE": 3})

    def test_parses_list_with_team_prefix(self):
        text = "There are 1 of a max of 6 players online: [Kette] mccpc02"
        assert parse_online_players_from_list(text) == [("mccpc02", "Kette")]


@pytest.mark.unit
@pytest.mark.django_db
class TestAddMaterialCredits:
    def test_adds_only_requested_materials(self):
        group = GroupFactory(mc_username="team_alpha")
        MinecraftTeamRegistration.objects.create(
            group=group,
            mc_username=group.mc_username,
            is_active=True,
            was_ever_registered=True,
        )
        cat = MinecraftShopCategory.objects.create(slug="blocks", name="Blocks")
        MinecraftShopItem.objects.create(
            category=cat,
            material="DIRT",
            esgui_item_loc="page1.items.dirt",
            buy_price_velos=1,
        )

        applied = add_material_credits_for_team("team_alpha", {"DIRT": 20, "STONE": 5})
        assert applied == {"DIRT": 20, "STONE": 5}
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT").quantity == 20
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="STONE").quantity == 5

        add_material_credits_for_team("team_alpha", {"DIRT": 2})
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT").quantity == 22
