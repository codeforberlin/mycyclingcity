# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftOutboxEvent
from minecraft.services.group_velos import spend_group_velos_from_minecraft


@pytest.mark.unit
@pytest.mark.django_db
class TestGroupVelosSpend:
    def test_spend_success(self):
        group = GroupFactory(mc_username="team_alpha", velos_total=1000, velos_spendable=500)

        result = spend_group_velos_from_minecraft("team_alpha", 100)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 400

        event = MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS
        ).first()
        assert event is not None
        assert event.payload["player"] == "team_alpha"
        assert event.payload["velos_spendable"] == 400
        assert event.payload["reason"] == "minecraft_spend"

    def test_spend_case_insensitive_mc_username(self):
        group = GroupFactory(mc_username="Team_Alpha", velos_total=1000, velos_spendable=200)

        result = spend_group_velos_from_minecraft("team_alpha", 50)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 150

    def test_spend_clamps_at_zero(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=30)

        result = spend_group_velos_from_minecraft("team_alpha", 100)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 0

    def test_group_not_found(self):
        assert spend_group_velos_from_minecraft("unknown_player", 10) == "group_not_found"

    def test_invalid_amount_zero(self):
        GroupFactory(mc_username="team_alpha", velos_spendable=100)
        assert spend_group_velos_from_minecraft("team_alpha", 0) == "invalid_amount"

    def test_invalid_amount_negative(self):
        GroupFactory(mc_username="team_alpha", velos_spendable=100)
        assert spend_group_velos_from_minecraft("team_alpha", -5) == "invalid_amount"

    def test_invalid_amount_non_numeric(self):
        GroupFactory(mc_username="team_alpha", velos_spendable=100)
        assert spend_group_velos_from_minecraft("team_alpha", "abc") == "invalid_amount"
