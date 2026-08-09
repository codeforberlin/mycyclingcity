# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from api.tests.conftest import GroupFactory, UserFactory
from minecraft.models import MinecraftProtectedRegion
from minecraft.services.preset_permissions import (
    user_can_manage_assigned_protected_regions,
)
from minecraft.services.region_admin import (
    operator_can_access_region,
    operator_master_regions,
)
from minecraft.services.region_ops import suggest_subregion_id


@pytest.mark.unit
@pytest.mark.django_db
class TestProtectedRegionHierarchy:
    def test_subregion_must_lie_inside_master(self):
        top = GroupFactory(name="TOP-Schule", parent=None)
        master = MinecraftProtectedRegion.objects.create(
            region_id="schule_master",
            world="MyCyclingCity",
            assigned_to_group=top,
            min_x=0,
            min_y=-64,
            min_z=0,
            max_x=100,
            max_y=100,
            max_z=100,
        )
        with pytest.raises(ValidationError):
            MinecraftProtectedRegion(
                region_id="schule_master_out",
                world="MyCyclingCity",
                parent=master,
                min_x=-10,
                min_y=-64,
                min_z=0,
                max_x=10,
                max_y=100,
                max_z=10,
            ).save()

    def test_subregion_inside_master_ok(self):
        top = GroupFactory(name="TOP-OK", parent=None)
        master = MinecraftProtectedRegion.objects.create(
            region_id="ok_master",
            world="MyCyclingCity",
            assigned_to_group=top,
            min_x=0,
            min_y=-64,
            min_z=0,
            max_x=100,
            max_y=100,
            max_z=100,
        )
        sub = MinecraftProtectedRegion.objects.create(
            region_id="ok_master_werk",
            world="MyCyclingCity",
            parent=master,
            min_x=10,
            min_y=-64,
            min_z=10,
            max_x=20,
            max_y=80,
            max_z=20,
        )
        assert sub.region_kind == "sub"
        assert sub.effective_top_group() == top
        assert master.region_kind == "master"

    def test_assigned_group_must_be_top(self):
        top = GroupFactory(name="TOP-Parent", parent=None)
        leaf = GroupFactory(name="Leaf-Klasse", parent=top)
        with pytest.raises(ValidationError):
            MinecraftProtectedRegion(
                region_id="bad_top",
                world="MyCyclingCity",
                assigned_to_group=leaf,
                min_x=0,
                min_y=0,
                min_z=0,
                max_x=1,
                max_y=1,
                max_z=1,
            ).save()

    def test_suggest_subregion_id(self):
        assert suggest_subregion_id("schule", "werkstatt") == "schule_werkstatt"
        assert suggest_subregion_id("schule", "schule_werkstatt") == "schule_werkstatt"

    def test_move_region_among_siblings(self):
        from minecraft.services.region_admin import move_region

        top = GroupFactory(name="TOP-Move", parent=None)
        a = MinecraftProtectedRegion.objects.create(
            region_id="m_a",
            world="MyCyclingCity",
            assigned_to_group=top,
            sort_order=0,
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        b = MinecraftProtectedRegion.objects.create(
            region_id="m_b",
            world="MyCyclingCity",
            assigned_to_group=top,
            sort_order=10,
            min_x=20,
            min_y=0,
            min_z=20,
            max_x=30,
            max_y=10,
            max_z=30,
        )
        assert move_region(b, -1) is True
        a.refresh_from_db()
        b.refresh_from_db()
        assert b.sort_order < a.sort_order
        assert move_region(b, -1) is False



@pytest.mark.unit
@pytest.mark.django_db
class TestOperatorRegionAccess:
    def _add_perm(self, user, codename):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from minecraft.models import MinecraftIntegrationConfig

        ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
        perm = Permission.objects.get(content_type=ct, codename=codename)
        user.user_permissions.add(perm)
        user = type(user).objects.get(pk=user.pk)
        return user

    def test_operator_sees_only_assigned_masters(self):
        top_a = GroupFactory(name="TOP-A", parent=None)
        top_b = GroupFactory(name="TOP-B", parent=None)
        master_a = MinecraftProtectedRegion.objects.create(
            region_id="a_master",
            world="MyCyclingCity",
            assigned_to_group=top_a,
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        MinecraftProtectedRegion.objects.create(
            region_id="b_master",
            world="MyCyclingCity",
            assigned_to_group=top_b,
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        user = UserFactory(is_staff=True)
        user.managed_groups.add(top_a)
        user = self._add_perm(user, "manage_assigned_protected_regions")
        assert user_can_manage_assigned_protected_regions(user)
        qs = operator_master_regions(user)
        assert list(qs.values_list("region_id", flat=True)) == ["a_master"]

        sub = MinecraftProtectedRegion.objects.create(
            region_id="a_master_sub",
            world="MyCyclingCity",
            parent=master_a,
            min_x=1,
            min_y=0,
            min_z=1,
            max_x=2,
            max_y=5,
            max_z=2,
        )
        assert operator_can_access_region(user, sub)
        assert not operator_can_access_region(user, master_a)

    def test_my_build_zones_requires_perm(self, client):
        user = UserFactory(is_staff=True)
        client.force_login(user)
        response = client.get(reverse("admin:minecraft_my_build_zones"))
        assert response.status_code in (302, 403)

        user = self._add_perm(user, "manage_assigned_protected_regions")
        client.force_login(user)
        response = client.get(reverse("admin:minecraft_my_build_zones"))
        assert response.status_code == 200
