# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftIntegrationConfig, MinecraftProtectedRegion
from minecraft.services.region_catalog import (
    build_protected_regions_payload,
    region_outline_rgb,
)
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
@pytest.mark.django_db
class TestRegionCatalog:
    def test_region_outline_rgb_stable(self):
        a = region_outline_rgb("FEZitty-Baeckerei")
        b = region_outline_rgb("FEZitty-Baeckerei")
        c = region_outline_rgb("other-zone")
        assert a == b
        assert len(a) == 3
        assert all(0 <= v <= 255 for v in a)
        assert a != c

    def test_build_protected_regions_payload(self):
        cfg = MinecraftIntegrationConfig.get_config()
        cfg.region_outline_enabled = True
        cfg.region_outline_enter_hint = False
        cfg.region_outline_view_distance = 64
        cfg.save()

        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        region = MinecraftProtectedRegion.objects.create(
            region_id="test_zone",
            display_name="Test Zone",
            world="MyCyclingCity",
            min_x=0,
            min_y=-64,
            min_z=0,
            max_x=10,
            max_y=100,
            max_z=10,
            protect_build=True,
        )
        region.builders.add(reg)

        payload = build_protected_regions_payload()
        assert payload["version"] == 1
        assert payload["outline_enabled"] is True
        assert payload["enter_hint_enabled"] is False
        assert payload["view_distance"] == 64
        assert len(payload["regions"]) == 1
        row = payload["regions"][0]
        assert row["region_id"] == "test_zone"
        assert row["display_name"] == "Test Zone"
        assert row["min_x"] == 0
        assert row["max_x"] == 10
        assert row["color_rgb"] == region_outline_rgb("test_zone")
        assert "Kette" in row["builder_teams"]
