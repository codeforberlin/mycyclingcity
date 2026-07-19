# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftShopCategory, MinecraftShopItem, MinecraftTeamRegistration
from minecraft.services.shop_catalog import build_shop_catalog_payload
from minecraft.services.team_velos_query import get_team_velos_by_mc_username


def _register_group(group):
    return MinecraftTeamRegistration.objects.create(
        group=group,
        mc_username=group.mc_username,
        is_active=True,
        was_ever_registered=True,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestTeamVelosQuery:
    def test_get_team_velos_success(self):
        group = GroupFactory(
            name="Alpha Team",
            mc_username="TeamAlpha",
            velos_total=5000,
            velos_spendable=1200,
        )
        _register_group(group)

        result = get_team_velos_by_mc_username("TeamAlpha")

        assert result == {
            "player": "TeamAlpha",
            "team_name": "Alpha Team",
            "velos_spendable": 1200,
            "velos_total": 5000,
        }

    def test_get_team_velos_not_found(self):
        assert get_team_velos_by_mc_username("unknown") is None


@pytest.mark.unit
@pytest.mark.django_db
class TestShopCatalog:
    def test_build_shop_catalog_payload(self):
        category = MinecraftShopCategory.objects.create(
            slug="blocks",
            name="Baumaterial",
            esgui_section="blocks",
            sort_order=1,
        )
        MinecraftShopItem.objects.create(
            category=category,
            material="STONE",
            esgui_item_key="1",
            esgui_item_loc="page1.items.1",
            buy_price_velos=5,
            sort_order=1,
        )
        MinecraftShopItem.objects.create(
            category=category,
            material="DISABLED",
            esgui_item_key="disabled",
            esgui_item_loc="page1.items.disabled",
            buy_price_velos=99,
            enabled=False,
        )

        payload = build_shop_catalog_payload()

        assert payload["version"] == 1
        assert len(payload["categories"]) == 1
        assert payload["categories"][0]["section"] == "blocks"
        assert len(payload["categories"][0]["items"]) == 1
        assert payload["categories"][0]["items"][0]["material"] == "STONE"
        assert payload["categories"][0]["items"][0]["buy_price_velos"] == 5

    def test_build_shop_catalog_skips_disabled_categories(self):
        MinecraftShopCategory.objects.create(slug="hidden", name="Hidden", enabled=False)

        payload = build_shop_catalog_payload()

        assert payload["categories"] == []
