# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from minecraft.services.preset_groups import (
    MINECRAFT_ADMIN_PERMISSION_CODENAMES,
    sync_minecraft_preset_groups,
)
from minecraft.services.preset_permissions import (
    user_can_access_minecraft_city,
    user_can_access_minecraft_control,
    user_can_access_minecraft_shop,
    user_can_manage_builder_sessions,
    user_can_manage_grant_catalog,
    user_can_manage_minecraft_accounts,
    user_can_manage_minecraft_operators,
    user_can_manage_minecraft_proxy,
    user_can_manage_minecraft_stations,
    user_can_manage_player_sessions,
    user_can_manage_vehiclesplus_packs,
    user_can_run_arena_sim,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestMinecraftPresetGroups:
    def test_sync_creates_minecraft_admin(self):
        results = {name: (created, missing) for name, created, missing in sync_minecraft_preset_groups()}
        assert "minecraft_admin" in results
        assert results["minecraft_admin"][1] == []
        group = Group.objects.get(name="minecraft_admin")
        codenames = set(group.permissions.values_list("codename", flat=True))
        assert set(MINECRAFT_ADMIN_PERMISSION_CODENAMES).issubset(codenames)

    def test_setup_command(self):
        call_command("setup_minecraft_preset_groups")
        assert Group.objects.filter(name="minecraft_admin").exists()
        assert Group.objects.filter(name="mcc_operator").exists()

    def test_minecraft_admin_user_has_menu_access(self, django_user_model):
        sync_minecraft_preset_groups()
        user = django_user_model.objects.create_user(
            username="mc_admin",
            password="secret",
            is_staff=True,
        )
        user.groups.add(Group.objects.get(name="minecraft_admin"))
        user = django_user_model.objects.get(pk=user.pk)

        assert user_can_access_minecraft_control(user)
        assert user_can_access_minecraft_city(user)
        assert user_can_access_minecraft_shop(user)
        assert user_can_manage_player_sessions(user)
        assert user_can_manage_builder_sessions(user)
        assert user_can_manage_grant_catalog(user)
        assert user_can_manage_vehiclesplus_packs(user)
        assert user_can_manage_minecraft_accounts(user)
        assert user_can_manage_minecraft_operators(user)
        assert user_can_manage_minecraft_stations(user)
        assert user_can_manage_minecraft_proxy(user)
        assert user_can_run_arena_sim(user)
        assert user.has_perm("minecraft.view_minecraftarenalane")
        assert user.has_perm("minecraft.change_minecraftarenamotionsettings")
        assert user.has_perm("minecraft.view_minecraftshopitem")
