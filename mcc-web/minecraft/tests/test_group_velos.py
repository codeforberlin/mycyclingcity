# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.tests.conftest import GroupFactory
from minecraft.models import MinecraftOutboxEvent, MinecraftTeamRegistration
from minecraft.services.group_velos import spend_group_velos_from_minecraft


def _register_group(group):
    return MinecraftTeamRegistration.objects.create(
        group=group,
        mc_username=group.mc_username,
        is_active=True,
        was_ever_registered=True,
    )


@pytest.mark.unit
@pytest.mark.django_db
class TestGroupVelosSpend:
    def test_spend_success(self):
        group = GroupFactory(mc_username="team_alpha", velos_total=1000, velos_spendable=500)
        _register_group(group)

        result = spend_group_velos_from_minecraft("team_alpha", 100)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 400

        event = MinecraftOutboxEvent.objects.filter(
            event_type=MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS
        ).first()
        assert event is not None
        assert event.payload["player"] == "team_alpha"
        assert event.payload["velos_spendable"] == 400
        assert event.payload["reason"] == "minecraft_spend"

    def test_spend_case_insensitive_mc_username(self):
        group = GroupFactory(mc_username="Team_Alpha", velos_total=1000, velos_spendable=200)
        _register_group(group)

        result = spend_group_velos_from_minecraft("team_alpha", 50)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 150

    def test_spend_clamps_at_zero(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=30)
        _register_group(group)

        result = spend_group_velos_from_minecraft("team_alpha", 100)

        assert result == "ok"
        group.refresh_from_db()
        assert group.velos_spendable == 0

    def test_group_not_found_without_registration(self):
        GroupFactory(mc_username="team_alpha", velos_spendable=100)
        assert spend_group_velos_from_minecraft("unknown_player", 10) == "group_not_found"

    def test_group_not_found_when_inactive(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=100)
        registration = _register_group(group)
        registration.is_active = False
        registration.save(update_fields=["is_active"])
        assert spend_group_velos_from_minecraft("team_alpha", 10) == "group_not_found"

    def test_invalid_amount_zero(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=100)
        _register_group(group)
        assert spend_group_velos_from_minecraft("team_alpha", 0) == "invalid_amount"

    def test_invalid_amount_negative(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=100)
        _register_group(group)
        assert spend_group_velos_from_minecraft("team_alpha", -5) == "invalid_amount"

    def test_invalid_amount_non_numeric(self):
        group = GroupFactory(mc_username="team_alpha", velos_spendable=100)
        _register_group(group)
        assert spend_group_velos_from_minecraft("team_alpha", "abc") == "invalid_amount"
