# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from unittest.mock import patch

from api.tests.conftest import GroupFactory, CyclistFactory
from minecraft.services.luckperms_sync import (
    apply_luckperms_for_registration,
    collect_minecraft_player_names,
    luckperms_group_name,
    remove_luckperms_for_registration,
)
from minecraft.services.team_registration import register_group_for_minecraft


@pytest.mark.unit
class TestLuckpermsGroupName:
    def test_kette_maps_to_team_kette(self):
        assert luckperms_group_name("Kette") == "team_kette"

    def test_team_alpha_slug(self):
        assert luckperms_group_name("TeamAlpha") == "team_teamalpha"


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectMinecraftPlayerNames:
    def test_includes_group_mc_username_and_cyclists(self):
        group = GroupFactory(name="Kette", mc_username="Kette")
        cyclist = CyclistFactory(mc_username="Radler1")
        cyclist.groups.add(group)
        names = collect_minecraft_player_names(group)
        assert names == ["Kette", "Radler1"]

    def test_deduplicates_names(self):
        group = GroupFactory(name="Kette", mc_username="Kette")
        cyclist = CyclistFactory(mc_username="Kette")
        cyclist.groups.add(group)
        assert collect_minecraft_player_names(group) == ["Kette"]

    def test_uses_registration_mc_username_when_group_field_empty(self):
        group = GroupFactory(name="Kurbel", mc_username=None)
        names = collect_minecraft_player_names(group, team_mc_username="Kurbel")
        assert names == ["Kurbel"]


@pytest.mark.unit
@pytest.mark.django_db
class TestApplyLuckpermsForRegistration:
    @patch("minecraft.services.luckperms_sync.rcon_client.run_commands", return_value=(True, "ok"))
    def test_sends_lp_commands(self, mock_run):
        group = GroupFactory(name="Kette", mc_username="Kette")
        registration = register_group_for_minecraft(group)

        ok, _log = apply_luckperms_for_registration(registration)
        assert ok is True
        commands = mock_run.call_args[0][0]
        joined = "\n".join(commands)
        assert "lp creategroup team_kette" in joined
        assert "lp user Kette parent add team_kette" in joined

    @patch("minecraft.services.luckperms_sync.rcon_client.run_commands", return_value=(True, "ok"))
    def test_remove_lp_parent(self, mock_run):
        group = GroupFactory(name="Kette", mc_username="Kette")
        registration = register_group_for_minecraft(group)
        remove_luckperms_for_registration(registration)
        joined = "\n".join(mock_run.call_args[0][0])
        assert "lp user Kette parent remove team_kette" in joined
