# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from api.tests.conftest import UserFactory
from minecraft.models import MinecraftIntegrationConfig, MinecraftProtectedRegion
from minecraft.services.preset_permissions import user_can_manage_protected_regions
from minecraft.services.region_ops import (
    _region_already_exists_response,
    apply_region_geometry,
    build_flag_commands,
    build_hierarchy_commands,
    build_member_sync_commands,
    build_selection_commands,
    default_region_max_y,
    default_region_min_y,
    normalize_region_id,
    parse_entity_pos,
    WG_MASTER_PRIORITY,
    WG_SUB_PRIORITY,
)


@pytest.mark.unit
class TestRegionOpsHelpers:
    def test_normalize_region_id(self):
        assert normalize_region_id("klasse_5a") == "klasse_5a"
        with pytest.raises(ValueError):
            normalize_region_id("../evil")

    def test_parse_entity_pos(self):
        raw = "mccpc01 has the following entity data: [100.9d, 64.0d, -20.1d]"
        assert parse_entity_pos(raw) == (100, 64, -21)

    def test_selection_commands(self):
        cmds = build_selection_commands("MyCyclingCity", 1, 2, 3, 4, 5, 6)
        assert cmds[0] == "//desel"
        assert cmds[1] == "//sel cuboid"
        assert cmds[2] == "//world mycyclingcity"
        assert cmds[3] == "//pos1 1,2,3"
        assert cmds[4] == "//pos2 4,5,6"

    def test_flag_protect_clears_passthrough(self):
        cmds = build_flag_commands("r1", "w", protect_build=True)
        assert any("passthrough" in c and "allow" not in c for c in cmds)
        assert any(c.endswith(" build") for c in cmds)
        assert "rg flag -w w r1 use deny" in cmds
        assert "rg flag -w w r1 chest-access deny" in cmds
        assert "rg flag -w w r1 pvp deny" in cmds
        assert "rg flag -w w r1 tnt deny" in cmds
        assert "rg flag -w w r1 other-explosion deny" in cmds
        assert "rg flag -w w r1 creeper-explosion deny" in cmds
        assert "rg flag -w w r1 fire-spread deny" in cmds
        assert "rg flag -w w r1 lava-fire deny" in cmds
        assert "rg flag -w w r1 enderman-grief deny" in cmds
        assert any("greeting Willkommen in r1" in c for c in cmds)
        assert any("farewell Bis bald (r1)" in c for c in cmds)

    def test_flag_unprotect(self):
        cmds = build_flag_commands("r1", "w", protect_build=False)
        assert "passthrough allow" in cmds[0]
        assert "rg flag -w w r1 use" in cmds
        assert "rg flag -w w r1 chest-access" in cmds
        # Safety flags stay on even without build protection.
        assert "rg flag -w w r1 pvp deny" in cmds

    def test_member_sync_diff(self):
        cmds = build_member_sync_commands(
            "r1",
            "w",
            desired=["alice", "bob"],
            previously_synced=["bob", "carol"],
        )
        joined = "\n".join(cmds)
        assert "removemember" in joined and "carol" in joined
        assert "addmember" in joined and "alice" in joined
        assert "addmember" in joined and "bob" in joined

    def test_already_exists_response(self):
        assert _region_already_exists_response(
            "A region with that name already exists. Please choose another name."
        )
        assert not _region_already_exists_response("Region saved as foo.")

    def test_default_region_y_span(self):
        assert default_region_min_y() == -64
        assert default_region_max_y() == 320

    def test_hierarchy_commands_master(self):
        region = MinecraftProtectedRegion(
            region_id="master_a",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=1,
            max_y=1,
            max_z=1,
        )
        cmds = build_hierarchy_commands(region)
        assert cmds[0] == f"rg setparent -w MyCyclingCity master_a"
        assert f"priority -w MyCyclingCity master_a {WG_MASTER_PRIORITY}" in cmds[1]

    def test_hierarchy_commands_sub(self):
        master = MinecraftProtectedRegion(
            region_id="master_a",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        # Unsaved parent with region_id is enough for command building.
        sub = MinecraftProtectedRegion(
            region_id="master_a_sub",
            world="MyCyclingCity",
            parent=master,
            min_x=1,
            min_y=0,
            min_z=1,
            max_x=2,
            max_y=5,
            max_z=2,
        )
        # FK may not resolve parent without pk — set manually for command helper.
        sub.parent = master
        cmds = build_hierarchy_commands(sub)
        assert cmds[0] == "rg setparent -w MyCyclingCity master_a_sub master_a"
        assert f"priority -w MyCyclingCity master_a_sub {WG_SUB_PRIORITY}" in cmds[1]


@pytest.mark.unit
@pytest.mark.django_db
class TestRegionOverlap:
    def test_masters_may_not_overlap(self):
        from django.core.exceptions import ValidationError

        MinecraftProtectedRegion.objects.create(
            region_id="m1",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        with pytest.raises(ValidationError):
            MinecraftProtectedRegion(
                region_id="m2",
                world="MyCyclingCity",
                min_x=5,
                min_y=0,
                min_z=5,
                max_x=15,
                max_y=10,
                max_z=15,
            ).save()

    def test_touching_edges_allowed(self):
        MinecraftProtectedRegion.objects.create(
            region_id="edge_a",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=10,
            max_y=10,
            max_z=10,
        )
        # Shares the face at x=10 — not an interior overlap.
        MinecraftProtectedRegion.objects.create(
            region_id="edge_b",
            world="MyCyclingCity",
            min_x=10,
            min_y=0,
            min_z=0,
            max_x=20,
            max_y=10,
            max_z=10,
        )

    def test_sibling_subs_may_not_overlap(self):
        from django.core.exceptions import ValidationError

        master = MinecraftProtectedRegion.objects.create(
            region_id="ms",
            world="MyCyclingCity",
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=100,
            max_y=100,
            max_z=100,
        )
        MinecraftProtectedRegion.objects.create(
            region_id="ms_a",
            world="MyCyclingCity",
            parent=master,
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=20,
            max_y=20,
            max_z=20,
        )
        with pytest.raises(ValidationError):
            MinecraftProtectedRegion(
                region_id="ms_b",
                world="MyCyclingCity",
                parent=master,
                min_x=10,
                min_y=0,
                min_z=10,
                max_x=30,
                max_y=20,
                max_z=30,
            ).save()


@pytest.mark.unit
@pytest.mark.django_db
class TestApplyRegionGeometry:
    @patch("minecraft.services.region_ops.rcon_client.run_commands")
    def test_redefine_when_define_reports_already_exists(self, mock_run):
        region = MinecraftProtectedRegion.objects.create(
            region_id="FEZitty-Baeckerei",
            world="MyCyclingCity",
            min_x=91,
            min_y=-60,
            min_z=-12,
            max_x=105,
            max_y=100,
            max_z=1,
            protect_build=True,
        )

        def fake_run(commands, stop_on_error=True):
            joined = " ".join(commands)
            if "//desel" in joined or "//pos1" in joined:
                return True, "selection ok"
            if "rg define" in joined:
                return True, "rg define -> A region with that name already exists."
            if "rg redefine" in joined:
                return True, "rg redefine -> Region updated"
            return True, "ok"

        mock_run.side_effect = fake_run
        ok, log = apply_region_geometry(region)
        assert ok
        assert "redefine" in log
        assert mock_run.call_count >= 3


def _add_perm(user, codename: str):
    ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    user.user_permissions.add(perm)
    return type(user).objects.get(pk=user.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestProtectedRegionPermission:
    def test_explicit_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "manage_protected_regions")
        assert user_can_manage_protected_regions(user)

    def test_city_alone_not_enough(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        assert not user_can_manage_protected_regions(user)


@pytest.mark.unit
@pytest.mark.django_db
class TestProtectedRegionCityView:
    @patch("minecraft.services.region_ops.rcon_client.run_commands", return_value=(True, "ok"))
    def test_apply_region(self, mock_run):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        user = _add_perm(user, "manage_protected_regions")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "protected_region",
                "action": "apply",
                "rg_region_id": "test_zone",
                "rg_world": "MyCyclingCity",
                "rg_min_x": "0",
                "rg_min_y": "64",
                "rg_min_z": "0",
                "rg_max_x": "10",
                "rg_max_y": "80",
                "rg_max_z": "10",
                "rg_protect_build": "on",
            },
        )
        assert response.status_code == 200
        assert MinecraftProtectedRegion.objects.filter(region_id="test_zone").exists()
        assert mock_run.called

    def test_denied_without_perm(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "protected_region",
                "action": "save",
                "rg_region_id": "nope",
                "rg_world": "MyCyclingCity",
                "rg_min_x": "0",
                "rg_min_y": "0",
                "rg_min_z": "0",
                "rg_max_x": "1",
                "rg_max_y": "1",
                "rg_max_z": "1",
            },
        )
        assert response.status_code == 302
        assert not MinecraftProtectedRegion.objects.filter(region_id="nope").exists()

    def test_save_only_no_rcon(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        user = _add_perm(user, "manage_protected_regions")
        client = Client()
        client.force_login(user)
        with patch("minecraft.services.region_ops.rcon_client.run_commands") as mock_run:
            response = client.post(
                reverse("admin:minecraft_city"),
                {
                    "form_type": "protected_region",
                    "action": "save",
                    "rg_region_id": "db_only",
                    "rg_world": "MyCyclingCity",
                    "rg_min_x": "1",
                    "rg_min_y": "2",
                    "rg_min_z": "3",
                    "rg_max_x": "4",
                    "rg_max_y": "5",
                    "rg_max_z": "6",
                },
            )
        assert response.status_code == 302
        assert MinecraftProtectedRegion.objects.filter(region_id="db_only").exists()
        mock_run.assert_not_called()

    def test_new_form_defaults_full_world_y(self):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        user = _add_perm(user, "manage_protected_regions")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("admin:minecraft_city"))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="rg_min_y" required value="-64"' in content
        assert 'name="rg_max_y" required value="320"' in content
        assert "voller Welthöhe" in content

    @patch(
        "minecraft.services.region_ops.fetch_player_block_pos",
        return_value=(100, -60, -8),
    )
    def test_capture_pos_keeps_world_y(self, _mock_pos):
        user = UserFactory(is_staff=True, is_superuser=False)
        user = _add_perm(user, "access_minecraft_city")
        user = _add_perm(user, "manage_protected_regions")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("admin:minecraft_city"),
            {
                "form_type": "protected_region",
                "action": "capture_pos",
                "rg_corner": "min",
                "rg_player": "mccpc01",
                "rg_region_id": "new_zone",
                "rg_world": "MyCyclingCity",
                "rg_min_y": "-64",
                "rg_max_y": "320",
            },
        )
        assert response.status_code == 200
        draft = response.context["rg_draft"]
        assert draft["min_x"] == 100
        assert draft["min_z"] == -8
        assert draft["min_y"] == -64
        assert draft["max_y"] == 320
