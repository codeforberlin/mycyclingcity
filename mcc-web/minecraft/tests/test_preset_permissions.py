# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from minecraft.models import MinecraftRconPreset
from minecraft.services.preset_permissions import (
    user_can_delete_preset,
    user_can_edit_preset,
    user_can_run_preset,
)


User = get_user_model()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff",
        password="secret",
        is_staff=True,
    )


@pytest.fixture
def moderator_user(db, staff_user):
    content_type = ContentType.objects.get_for_model(MinecraftRconPreset)
    perm = Permission.objects.get(
        content_type=content_type,
        codename="run_rconpreset",
    )
    staff_user.user_permissions.add(perm)
    return staff_user


@pytest.mark.unit
@pytest.mark.django_db
class TestPresetPermissions:
    def test_moderator_can_run_world_preset(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="day",
            name="Tag",
            category=MinecraftRconPreset.CATEGORY_WORLD,
            commands=["time set day"],
        )
        assert user_can_run_preset(moderator_user, preset)

    def test_moderator_cannot_run_gamerule_without_flag(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="city",
            name="Stadt",
            category=MinecraftRconPreset.CATEGORY_GAMERULE,
            commands=["gamerule pvp false"],
        )
        assert not user_can_run_preset(moderator_user, preset)

    def test_moderator_can_run_flagged_gamerule(self, moderator_user):
        preset = MinecraftRconPreset.objects.create(
            slug="city",
            name="Stadt",
            category=MinecraftRconPreset.CATEGORY_GAMERULE,
            commands=["gamerule pvp false"],
            moderator_can_run=True,
        )
        assert user_can_run_preset(moderator_user, preset)

    def test_system_preset_delete_requires_special_perm(self, staff_user):
        preset = MinecraftRconPreset.objects.create(
            slug="sys",
            name="System",
            commands=["time set day"],
            is_system=True,
        )
        assert not user_can_delete_preset(staff_user, preset)

    def test_system_preset_edit_requires_special_perm(self, staff_user):
        preset = MinecraftRconPreset.objects.create(
            slug="sys",
            name="System",
            commands=["time set day"],
            is_system=True,
        )
        assert not user_can_edit_preset(staff_user, preset)
