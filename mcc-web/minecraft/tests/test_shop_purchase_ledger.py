# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import (
    MinecraftOutboxEvent,
    MinecraftShopPurchaseCredit,
    MinecraftTeamRegistration,
)
from minecraft.services.shop_purchase_ledger import (
    consume_for_sell,
    consume_for_sell_batch,
    credit_group_velos_from_minecraft,
    record_purchase,
)


def _register_group(group):
    return MinecraftTeamRegistration.objects.create(
        group=group,
        mc_username=group.mc_username,
        is_active=True,
        was_ever_registered=True,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestShopPurchaseLedger:
    def test_record_purchase_increments(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)

        assert record_purchase("team_alpha", "dirt", 10) == "ok"
        assert record_purchase("team_alpha", "DIRT", 5) == "ok"

        credit = MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT")
        assert credit.quantity == 15

    def test_consume_for_sell_success(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)
        record_purchase("team_alpha", "STONE", 10)

        assert consume_for_sell("team_alpha", "STONE", 4) == "ok"
        credit = MinecraftShopPurchaseCredit.objects.get(group=group, material="STONE")
        assert credit.quantity == 6

    def test_consume_rejects_over_sell(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)
        record_purchase("team_alpha", "DIRT", 10)

        assert consume_for_sell("team_alpha", "DIRT", 11) == "insufficient_credit"
        credit = MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT")
        assert credit.quantity == 10

    def test_consume_without_prior_purchase(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)

        assert consume_for_sell("team_alpha", "DIRT", 1) == "insufficient_credit"

    def test_consume_batch_all_or_nothing(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)
        record_purchase("team_alpha", "DIRT", 5)
        record_purchase("team_alpha", "STONE", 2)

        assert (
            consume_for_sell_batch(
                "team_alpha",
                [
                    {"material": "DIRT", "amount": 3},
                    {"material": "STONE", "amount": 5},
                ],
            )[0]
            == "insufficient_credit"
        )
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT").quantity == 5
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="STONE").quantity == 2

        status, consumed = consume_for_sell_batch(
            "team_alpha",
            [
                {"material": "DIRT", "amount": 3},
                {"material": "STONE", "amount": 2},
            ],
        )
        assert status == "ok"
        assert consumed == [
            {"material": "DIRT", "amount": 3},
            {"material": "STONE", "amount": 2},
        ]
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT").quantity == 2
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="STONE").quantity == 0

    def test_consume_batch_partial(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)
        record_purchase("team_alpha", "DIRT", 5)

        status, consumed = consume_for_sell_batch(
            "team_alpha",
            [
                {"material": "DIRT", "amount": 20},
                {"material": "STONE", "amount": 5},
            ],
            partial=True,
        )
        assert status == "ok"
        assert consumed == [{"material": "DIRT", "amount": 5}]
        assert MinecraftShopPurchaseCredit.objects.get(group=group, material="DIRT").quantity == 0

    def test_record_group_not_found(self):
        assert record_purchase("unknown", "DIRT", 1) == "group_not_found"

    def test_invalid_payload(self):
        group = GroupFactory(mc_username="team_alpha")
        _register_group(group)
        assert record_purchase("team_alpha", "", 1) == "invalid_payload"
        assert record_purchase("team_alpha", "DIRT", 0) == "invalid_payload"


@pytest.mark.unit
@pytest.mark.django_db
class TestCreditGroupVelos:
    def test_credit_success_queues_scoreboard(self):
        group = GroupFactory(mc_username="team_alpha", velos_total=1000, velos_spendable=500)
        _register_group(group)

        result = credit_group_velos_from_minecraft("team_alpha", 100)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 600

        event = MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS
        ).first()
        assert event is not None
        assert event.payload["player"] == "team_alpha"
        assert event.payload["velos_spendable"] == 600
        assert event.payload["reason"] == "minecraft_sell"

    def test_credit_invalid_amount(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=100)
        _register_group(group)
        assert credit_group_velos_from_minecraft("team_alpha", 0) == "invalid_amount"
        assert credit_group_velos_from_minecraft("team_alpha", -1) == "invalid_amount"

    def test_credit_group_not_found(self):
        assert credit_group_velos_from_minecraft("unknown", 10) == "group_not_found"
