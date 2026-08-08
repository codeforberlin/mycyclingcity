# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest

from minecraft.models import MinecraftPlayAccount, MinecraftTeamRegistration
from minecraft.services.playerdata_migrate import (
    MigrateDirection,
    diff_for_direction,
    run_migration,
)
from minecraft.services.playerdata_uuid import offline_player_uuid, parse_ms_uuid, uuid_dashed
from minecraft.services.team_registration import register_group_for_minecraft
from api.tests.conftest import GroupFactory


@pytest.mark.unit
class TestOfflinePlayerUuid:
    def test_known_vectors(self):
        assert uuid_dashed(offline_player_uuid("Steve")) == "5627dd98-e6be-3c21-b8a8-e92344183641"
        assert uuid_dashed(offline_player_uuid("Kette")) == "52bd6834-150c-3ae8-93e5-f7133f6ba4fa"
        assert uuid_dashed(offline_player_uuid("mccpc01")) == "50287e3f-0897-3e69-bfef-efbc24f9ea19"

    def test_parse_ms_uuid_with_and_without_hyphens(self):
        dashed = "069a79f4-44e9-4726-a5fe-8c18a9833bd8"
        assert str(parse_ms_uuid(dashed)) == dashed
        compact = dashed.replace("-", "")
        assert str(parse_ms_uuid(compact)) == dashed


@pytest.mark.unit
@pytest.mark.django_db
class TestPlayerdataMigrate:
    def test_legacy_to_twin_copies_playerdata(self, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_WORLD_ROOT = str(tmp_path / "MyCyclingCity")
        settings.MCC_MINECRAFT_FAILOVER_BACKUP_ROOT = str(tmp_path / "backups")
        world = Path(settings.MCC_MINECRAFT_PAPER_WORLD_ROOT)
        (world / "players" / "data").mkdir(parents=True)

        group = GroupFactory(name="Kette", mc_username="Kette")
        reg = register_group_for_minecraft(group)
        MinecraftTeamRegistration.objects.filter(pk=reg.pk).update(
            ms_username="mccpc01",
            ms_uuid="069a79f4-44e9-4726-a5fe-8c18a9833bd8",
        )

        legacy_uuid = offline_player_uuid("Kette")
        twin_uuid = offline_player_uuid("mccpc01")
        src = world / "players" / "data_backup" / f"{legacy_uuid}.dat"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"legacy-inventory")

        dry = run_migration(MigrateDirection.LEGACY_TO_TWIN, dry_run=True)
        assert dry.ok
        assert not (world / "players" / "data" / f"{twin_uuid}.dat").exists()

        result = run_migration(MigrateDirection.LEGACY_TO_TWIN, dry_run=False)
        assert result.ok
        dst = world / "players" / "data" / f"{twin_uuid}.dat"
        assert dst.read_bytes() == b"legacy-inventory"

        diffs = diff_for_direction(MigrateDirection.LEGACY_TO_TWIN)
        assert len(diffs) == 1
        assert diffs[0].overall.value in {"equal", "source_newer", "target_newer"}

    def test_online_to_offline_requires_ms_uuid(self, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_WORLD_ROOT = str(tmp_path / "MyCyclingCity")
        settings.MCC_MINECRAFT_FAILOVER_BACKUP_ROOT = str(tmp_path / "backups")
        (tmp_path / "MyCyclingCity" / "players" / "data").mkdir(parents=True)

        MinecraftPlayAccount.objects.create(
            id_tag="Arena1",
            short_name="Arena1",
            display_name="Arena 1",
            sort_order=1,
            is_active=True,
            ms_username="mccpc01",
            ms_uuid="",
        )
        result = run_migration(MigrateDirection.ONLINE_TO_OFFLINE, dry_run=False)
        assert result.ok is False
        assert any("ms_uuid" in e for e in result.errors)
