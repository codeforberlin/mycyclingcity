# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftPlayerScoreboardSnapshot, MinecraftShopCategory, MinecraftShopItem
from minecraft.services.shop_readiness import check_shop_readiness
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
@pytest.mark.django_db
class TestShopReadiness:
    @patch("minecraft.services.shop_readiness.get_connected_server_ids", return_value=["velo-stadt-1"])
    @patch("minecraft.services.shop_readiness.check_connection", return_value=(True, "", "auth"))
    def test_all_ok_with_registered_team_and_catalog(self, _rcon, _bridge):
        group = GroupFactory(name="Team", mc_username="team_x", velos_spendable=100)
        register_group_for_minecraft(group)
        MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="team_x",
            velos_spendable=100,
        )
        category = MinecraftShopCategory.objects.create(
            slug="tools",
            name="Tools",
            esgui_section="tools",
            enabled=True,
        )
        MinecraftShopItem.objects.create(
            category=category,
            material="DIAMOND_PICKAXE",
            esgui_item_loc="page1.items.pickaxe",
            buy_price_velos=10,
            enabled=True,
        )

        report = check_shop_readiness(
            worker_running=True,
            snapshot_worker_running=True,
            ws_running=True,
        )

        assert report.ok is True
        assert report.summary["errors"] == 0
        check_ids = {check.id for check in report.checks}
        assert "velos_drift" in check_ids
        assert "catalog_items" in check_ids
        velos_check = next(check for check in report.checks if check.id == "velos_drift")
        assert velos_check.ok is True

    @patch("minecraft.services.shop_readiness.get_connected_server_ids", return_value=[])
    @patch("minecraft.services.shop_readiness.check_connection", return_value=(True, "", "auth"))
    def test_velos_drift_detected(self, _rcon, _bridge):
        group = GroupFactory(name="Team", mc_username="team_x", velos_spendable=120)
        register_group_for_minecraft(group)
        MinecraftPlayerScoreboardSnapshot.objects.create(
            player_name="team_x",
            velos_spendable=95,
        )

        report = check_shop_readiness(
            worker_running=True,
            snapshot_worker_running=True,
            ws_running=True,
        )

        assert report.ok is False
        drift = next(check for check in report.checks if check.id == "velos_drift")
        assert drift.ok is False
        assert drift.severity == "error"
        assert "team_x" in drift.detail
        assert drift.action == "sync"

    @patch("minecraft.services.shop_readiness.get_connected_server_ids", return_value=[])
    @patch("minecraft.services.shop_readiness.check_connection", return_value=(False, "timeout", "auth"))
    def test_empty_catalog_fails(self, _rcon, _bridge):
        report = check_shop_readiness(
            worker_running=False,
            snapshot_worker_running=False,
            ws_running=False,
        )

        assert report.ok is False
        catalog = next(check for check in report.checks if check.id == "catalog_items")
        assert catalog.ok is False
        rcon = next(check for check in report.checks if check.id == "rcon")
        assert rcon.ok is False

    @patch("minecraft.services.shop_readiness.get_connected_server_ids", return_value=["velo-stadt-1"])
    @patch("minecraft.services.shop_readiness.check_connection", return_value=(True, "", "auth"))
    def test_incomplete_catalog_items_warning(self, _rcon, _bridge):
        category = MinecraftShopCategory.objects.create(
            slug="tools",
            name="Tools",
            esgui_section="tools",
            enabled=True,
        )
        MinecraftShopItem.objects.create(
            category=category,
            material="DIRT",
            esgui_item_loc="",
            buy_price_velos=5,
            enabled=True,
        )

        report = check_shop_readiness(
            worker_running=True,
            snapshot_worker_running=True,
            ws_running=True,
        )

        incomplete = next(check for check in report.checks if check.id == "catalog_complete")
        assert incomplete.ok is False
        assert incomplete.severity == "warning"

    def test_report_to_dict_serializes_checks(self):
        report = check_shop_readiness(
            worker_running=False,
            snapshot_worker_running=False,
            ws_running=False,
        )
        data = report.to_dict()
        assert "ok" in data
        assert "summary" in data
        assert isinstance(data["checks"], list)
        if data["checks"]:
            assert "label" in data["checks"][0]
            assert isinstance(data["checks"][0]["label"], str)
