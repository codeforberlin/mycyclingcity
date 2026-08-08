# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.urls import reverse

from minecraft.models import MinecraftShopCategory, MinecraftShopItem
from minecraft.services.shop_pricing import (
    assign_minimum_velos,
    count_zero_price_items,
    zero_price_items_queryset,
)


@pytest.fixture
def shop_category(db):
    return MinecraftShopCategory.objects.create(
        slug="blocks",
        name="Blöcke",
        esgui_section="blocks",
        enabled=True,
    )


def _item(category, *, material, loc, price, enabled=True):
    return MinecraftShopItem.objects.create(
        category=category,
        material=material,
        display_name=material,
        esgui_item_key=material.lower(),
        esgui_item_loc=loc,
        buy_price_velos=price,
        enabled=enabled,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestShopPricing:
    def test_finds_zero_price_items(self, shop_category):
        _item(shop_category, material="STONE", loc="page1.items.stone", price=5)
        zero = _item(shop_category, material="DIRT", loc="page1.items.dirt", price=0)
        _item(
            shop_category,
            material="SAND",
            loc="page1.items.sand",
            price=0,
            enabled=False,
        )

        assert count_zero_price_items() == 2
        found = list(zero_price_items_queryset())
        assert {item.pk for item in found} == {
            zero.pk,
            MinecraftShopItem.objects.get(material="SAND").pk,
        }

    def test_assign_minimum_velos(self, shop_category):
        keep = _item(shop_category, material="STONE", loc="page1.items.stone", price=5)
        fix = _item(shop_category, material="DIRT", loc="page1.items.dirt", price=0)

        updated = assign_minimum_velos(minimum=1)
        assert updated == 1
        keep.refresh_from_db()
        fix.refresh_from_db()
        assert keep.buy_price_velos == 5
        assert fix.buy_price_velos == 1
        assert count_zero_price_items() == 0


@pytest.mark.unit
@pytest.mark.django_db
class TestShopOpsMinVelosView:
    @pytest.fixture
    def shop_user(self, django_user_model):
        from django.contrib.auth.models import Permission
        from minecraft.models import MinecraftIntegrationConfig

        user = django_user_model.objects.create_user(
            username="shopops",
            password="x",
            is_staff=True,
        )
        perm = Permission.objects.get(
            content_type__app_label="minecraft",
            codename="access_minecraft_shop",
        )
        # Permission is on MinecraftIntegrationConfig
        assert MinecraftIntegrationConfig._meta.app_label == "minecraft"
        user.user_permissions.add(perm)
        return user

    def test_shop_ops_lists_zero_price_items(self, client, shop_user, shop_category):
        _item(shop_category, material="DIRT", loc="page1.items.dirt", price=0)
        client.force_login(shop_user)
        response = client.get(reverse("admin:minecraft_shop_ops"))
        assert response.status_code == 200
        assert response.context["zero_price_count"] == 1
        assert b"DIRT" in response.content
        assert "assign_min_velos".encode() in response.content

    def test_shop_ops_assigns_minimum_velos(self, client, shop_user, shop_category):
        item = _item(shop_category, material="DIRT", loc="page1.items.dirt", price=0)
        client.force_login(shop_user)
        response = client.post(
            reverse("admin:minecraft_shop_ops"),
            {"action": "assign_min_velos"},
        )
        assert response.status_code == 302
        item.refresh_from_db()
        assert item.buy_price_velos == 1
