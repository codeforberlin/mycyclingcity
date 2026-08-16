# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from django.test import override_settings

from minecraft.services.vehiclesplus_pack_authoring import (
    PackAuthoringError,
    apply_resource_pack_to_server,
    import_model_from_vendor_zip,
    inspect_staged_vendor_zip,
    list_pack_zip_names,
    list_vehicle_model_stems_in_pack,
    merge_model_into_pack,
    next_custom_model_data,
    stage_vendor_zip,
    validate_pack_filename,
)


def _minimal_source_zip(path: Path, *, thresholds: list[int] | None = None) -> None:
    """Create a tiny VP-like pack with leather_boots range_dispatch entries."""
    entries = [
        {
            "threshold": t,
            "model": {
                "type": "model",
                "model": f"vp:item/vehicles/example_{t}",
                "tints": [{"type": "minecraft:dye", "default": -6265536}],
            },
        }
        for t in (thresholds or [1, 2])
    ]
    item_json = {
        "model": {
            "type": "range_dispatch",
            "property": "custom_model_data",
            "entries": entries,
            "fallback": {"type": "model", "model": "minecraft:item/leather_boots"},
        }
    }
    model_json = {"credit": "test", "elements": []}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "pack.mcmeta",
            json.dumps(
                {
                    "pack": {
                        "pack_format": 46,
                        "description": "test",
                        "supported_formats": 46,
                    }
                }
            ),
        )
        zf.writestr(
            "assets/minecraft/items/leather_boots.json",
            json.dumps(item_json),
        )
        zf.writestr(
            "assets/vp/models/item/vehicles/example_1.json",
            json.dumps(model_json),
        )


@pytest.mark.unit
class TestValidatePackFilename:
    def test_accepts_safe_names(self):
        assert validate_pack_filename("MyPack_v2.zip") == "MyPack_v2.zip"
        assert validate_pack_filename("MyPack") == "MyPack.zip"

    def test_rejects_path_traversal(self):
        with pytest.raises(PackAuthoringError):
            validate_pack_filename("../evil.zip")
        with pytest.raises(PackAuthoringError):
            validate_pack_filename("foo/bar.zip")


@pytest.mark.unit
@pytest.mark.django_db
class TestMergeModelIntoPack:
    def test_merge_with_selectable_source_and_output(self, tmp_path, settings):
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        source_name = "VPExample-base.zip"
        output_name = "VPExample-MCC-custom.zip"
        _minimal_source_zip(packs_dir / source_name, thresholds=[1, 7])

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            MCC_MINECRAFT_RESOURCE_PACK_HTTP_BASE="http://example.test:8000",
        ):
            assert list_pack_zip_names() == [source_name]
            model = json.dumps({"credit": "Lastenrad", "elements": []}).encode("utf-8")
            result = merge_model_into_pack(
                source_pack_name=source_name,
                output_pack_name=output_name,
                model_stem="lastenrad",
                model_json_bytes=model,
                custom_model_data=None,
                overwrite_output=True,
            )

        assert result.custom_model_data == 8
        assert result.output_path.name == output_name
        assert result.http_url == f"http://example.test:8000/{output_name}"
        assert result.sha1
        assert (packs_dir / output_name).is_file()
        # Source unchanged as separate file
        assert (packs_dir / source_name).is_file()

        with zipfile.ZipFile(packs_dir / output_name) as zf:
            meta = json.loads(zf.read("pack.mcmeta"))
            assert meta["pack"]["pack_format"] == 64
            assert meta["pack"]["supported_formats"] == 64
            boots = json.loads(zf.read("assets/minecraft/items/leather_boots.json"))
            thresholds = [
                e["threshold"] for e in boots["model"]["entries"]
            ]
            assert 8 in thresholds
            assert "assets/vp/models/item/vehicles/lastenrad.json" in zf.namelist()

    def test_replace_keeps_cmd_and_overwrites_model(self, tmp_path):
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        source_name = "VPExample-base.zip"
        _minimal_source_zip(packs_dir / source_name, thresholds=[1, 7])

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            MCC_MINECRAFT_RESOURCE_PACK_HTTP_BASE="http://example.test:8000",
        ):
            assert list_vehicle_model_stems_in_pack(source_name) == ["example_1"]
            model = json.dumps(
                {"credit": "replaced", "elements": [{"from": [0, 0, 0], "to": [1, 1, 1]}]}
            ).encode("utf-8")
            # Same stem without checkbox → auto-replace, keep CMD 1
            result = merge_model_into_pack(
                source_pack_name=source_name,
                output_pack_name=source_name,
                model_stem="example_1",
                model_json_bytes=model,
                custom_model_data=None,
                replace_existing=False,
            )

        assert result.custom_model_data == 1
        with zipfile.ZipFile(packs_dir / source_name) as zf:
            data = json.loads(zf.read("assets/vp/models/item/vehicles/example_1.json"))
            assert data["credit"] == "replaced"
            boots = json.loads(zf.read("assets/minecraft/items/leather_boots.json"))
            by_cmd = {e["threshold"]: e for e in boots["model"]["entries"]}
            assert by_cmd[1]["model"]["model"] == "vp:item/vehicles/example_1"
            assert sorted(by_cmd) == [1, 7]

    def test_next_cmd_from_extracted_pack(self, tmp_path):
        work = tmp_path / "pack"
        work.mkdir()
        boots = work / "assets" / "minecraft" / "items"
        boots.mkdir(parents=True)
        (boots / "leather_boots.json").write_text(
            json.dumps(
                {
                    "model": {
                        "type": "range_dispatch",
                        "property": "custom_model_data",
                        "entries": [
                            {"threshold": 3, "model": {"type": "model", "model": "x"}},
                            {"threshold": 5, "model": {"type": "model", "model": "y"}},
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        assert next_custom_model_data(work) == 6


def _vendor_model_zip(path: Path) -> None:
    """Pixelmine-like zip: custom namespace model + texture."""
    model = {
        "credit": "VendorBike",
        "texture_size": [64, 64],
        "textures": {
            "0": "pixelmine:item/bikes/cargobike",
            "particle": "pixelmine:item/bikes/cargobike",
        },
        "elements": [
            {
                "from": [0, 0, 0],
                "to": [16, 8, 16],
                "faces": {
                    "north": {"uv": [0, 0, 16, 8], "texture": "#0"},
                },
            }
        ],
    }
    # minimal 1x1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "pack.mcmeta",
            json.dumps({"pack": {"pack_format": 34, "description": "vendor"}}),
        )
        zf.writestr(
            "assets/pixelmine/models/item/bikes/cargobike.json",
            json.dumps(model),
        )
        zf.writestr("assets/pixelmine/textures/item/bikes/cargobike.png", png)


@pytest.mark.unit
@pytest.mark.django_db
class TestVendorZipImport:
    def test_inspect_and_import_single_model(self, tmp_path):
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        source_name = "base.zip"
        output_name = "base_MCC.zip"
        _minimal_source_zip(packs_dir / source_name, thresholds=[1, 7])
        vendor_path = tmp_path / "vendor.zip"
        _vendor_model_zip(vendor_path)
        payload = vendor_path.read_bytes()

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            MCC_MINECRAFT_RESOURCE_PACK_HTTP_BASE="http://example.test:8000",
            DATA_DIR=str(tmp_path),
        ):
            token = stage_vendor_zip(payload=payload, original_name="CargoBike.zip")
            inspection = inspect_staged_vendor_zip(token)
            assert len(inspection.models) == 1
            assert inspection.models[0].path.endswith("cargobike.json")
            assert inspection.models[0].texture_files_found == 1

            result = import_model_from_vendor_zip(
                staging_token=token,
                model_path=inspection.models[0].path,
                source_pack_name=source_name,
                output_pack_name=output_name,
                model_stem="cargobike",
                custom_model_data=None,
                overwrite_output=True,
            )

        assert result.custom_model_data == 8
        assert result.model_resource == "vp:item/vehicles/cargobike"
        with zipfile.ZipFile(packs_dir / output_name) as zf:
            names = zf.namelist()
            assert "assets/vp/models/item/vehicles/cargobike.json" in names
            assert any(
                n.startswith("assets/vp/textures/item/vehicles/cargobike/")
                and n.endswith(".png")
                for n in names
            )
            model = json.loads(zf.read("assets/vp/models/item/vehicles/cargobike.json"))
            assert model["textures"]["0"].startswith("vp:item/vehicles/cargobike/")
            boots = json.loads(zf.read("assets/minecraft/items/leather_boots.json"))
            assert any(e["threshold"] == 8 for e in boots["model"]["entries"])

    def test_vendor_import_replace_reuses_cmd(self, tmp_path):
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        source_name = "base.zip"
        _minimal_source_zip(packs_dir / source_name, thresholds=[1, 7])
        vendor_path = tmp_path / "vendor.zip"
        _vendor_model_zip(vendor_path)
        payload = vendor_path.read_bytes()

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            MCC_MINECRAFT_RESOURCE_PACK_HTTP_BASE="http://example.test:8000",
            DATA_DIR=str(tmp_path),
        ):
            token = stage_vendor_zip(payload=payload, original_name="CargoBike.zip")
            inspection = inspect_staged_vendor_zip(token)
            first = import_model_from_vendor_zip(
                staging_token=token,
                model_path=inspection.models[0].path,
                source_pack_name=source_name,
                output_pack_name=source_name,
                model_stem="cargobike",
                replace_existing=False,
            )
            assert first.custom_model_data == 8

            token2 = stage_vendor_zip(payload=payload, original_name="CargoBike.zip")
            inspection2 = inspect_staged_vendor_zip(token2)
            # Same stem again without replace flag → auto-replace, keep CMD 8
            second = import_model_from_vendor_zip(
                staging_token=token2,
                model_path=inspection2.models[0].path,
                source_pack_name=source_name,
                output_pack_name=source_name,
                model_stem="cargobike",
                custom_model_data=None,
                replace_existing=False,
            )

        assert second.custom_model_data == 8
        with zipfile.ZipFile(packs_dir / source_name) as zf:
            boots = json.loads(zf.read("assets/minecraft/items/leather_boots.json"))
            cmds = [e["threshold"] for e in boots["model"]["entries"]]
            assert cmds.count(8) == 1
            assert sorted(cmds) == [1, 7, 8]

    def test_pixelmine_nested_resource_pack_structure(self, tmp_path):
        """PixelMine: …/Drag & Drop Files/Resource Pack/assets/minecraft/models/pixelmine/…"""
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        _minimal_source_zip(packs_dir / "base.zip", thresholds=[1])

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        model = {
            "textures": {"0": "minecraft:pixelmine/vehicles/school_bus"},
            "elements": [{"from": [0, 0, 0], "to": [1, 1, 1], "faces": {}}],
        }
        override = {
            "parent": "minecraft:item/generated",
            "overrides": [
                {"predicate": {"custom_model_data": 100}, "model": "pixelmine/vehicles/school_bus"}
            ],
        }
        prefix = "PixelMine_Model_Vehicle_SchoolBus/Drag & Drop Files"
        vendor = tmp_path / "schoolbus.zip"
        with zipfile.ZipFile(vendor, "w") as zf:
            # Preferred Resource Pack copy
            zf.writestr(
                f"{prefix}/Resource Pack/assets/minecraft/models/pixelmine/vehicles/school_bus.json",
                json.dumps(model),
            )
            zf.writestr(
                f"{prefix}/Resource Pack/assets/minecraft/textures/pixelmine/vehicles/school_bus.png",
                png,
            )
            zf.writestr(
                f"{prefix}/Resource Pack/assets/minecraft/models/item/leather_boots.json",
                json.dumps(override),
            )
            zf.writestr(f"{prefix}/Resource Pack/pack.mcmeta", "{}")
            # Duplicate under Oraxen (should be deduped away)
            zf.writestr(
                f"{prefix}/Oraxen/pack/assets/minecraft/models/pixelmine/vehicles/school_bus.json",
                json.dumps(model),
            )
            zf.writestr(
                f"{prefix}/Oraxen/pack/assets/minecraft/textures/pixelmine/vehicles/school_bus.png",
                png,
            )
            zf.writestr(
                f"{prefix}/VehiclesPlusPro V3/vehicles/cars/school_bus.hjson",
                "{\n  id: school_bus\n  typeId: cars\n  parts: [{ type: skin, item: { custommodeldata: 1 } }]\n}\n",
            )

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            DATA_DIR=str(tmp_path),
        ):
            token = stage_vendor_zip(
                payload=vendor.read_bytes(), original_name="SchoolBus.zip"
            )
            inspection = inspect_staged_vendor_zip(token)
            assert len(inspection.models) == 1
            chosen = inspection.models[0]
            assert chosen.stem == "school_bus"
            assert "Resource Pack" in chosen.path
            assert chosen.texture_files_found == 1
            assert chosen.leather_item == "leather_boots"
            assert chosen.vendor_cmd == 100

            result = import_model_from_vendor_zip(
                staging_token=token,
                model_path=chosen.path,
                source_pack_name="base.zip",
                output_pack_name="out.zip",
                model_stem="school_bus",
            )

        assert result.custom_model_data == 2
        assert result.vendor_hjson_subdir == "cars"
        assert "custommodeldata: 2" in result.vendor_hjson
        assert "typeId: cars" in result.vendor_hjson
        assert "yoffset: 0.45" not in result.vendor_hjson
        with zipfile.ZipFile(packs_dir / "out.zip") as zf:
            imported = json.loads(
                zf.read("assets/vp/models/item/vehicles/school_bus.json")
            )
            assert imported["textures"]["0"].startswith("vp:item/vehicles/school_bus/")
            assert any(
                n.endswith("school_bus.png")
                for n in zf.namelist()
                if "textures/item/vehicles/school_bus" in n
            )

    def test_rejects_empty_zip(self, tmp_path):
        with override_settings(DATA_DIR=str(tmp_path)):
            with pytest.raises(PackAuthoringError):
                stage_vendor_zip(payload=b"", original_name="x.zip")


@pytest.mark.unit
@pytest.mark.django_db
class TestApplyResourcePackToServer:
    def test_updates_properties_with_timestamped_backup(self, tmp_path):
        paper = tmp_path / "mc-srv"
        paper.mkdir()
        props = paper / "server.properties"
        props.write_text(
            "\n".join(
                [
                    "#minecraft server properties",
                    "motd=MyCyclingCity",
                    "resource-pack=http\\://old.example/old.zip",
                    "resource-pack-sha1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "resource-pack-id=11111111-1111-1111-1111-111111111111",
                    "require-resource-pack=true",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        vp = paper / "plugins" / "VehiclesPlus"
        vp.mkdir(parents=True)
        cfg = vp / "config.yml"
        cfg.write_text(
            "enabled: true\nresourcePackUrl: http://old.example/old.zip\n",
            encoding="utf-8",
        )

        url = "http://192.168.90.14:8000/VPExample-v3-1.21.7-1.21.8_MCC.zip"
        sha1 = "bd018a44a724772871006100be0017d82a39cacc"
        with override_settings(
            MCC_MINECRAFT_PAPER_DIR=str(paper),
            MCC_MINECRAFT_VEHICLESPLUS_VEHICLES_DIR=str(vp / "vehicles"),
        ):
            (vp / "vehicles").mkdir()
            result = apply_resource_pack_to_server(
                pack_http_url=url, sha1=sha1, update_vehiclesplus=True
            )

        assert result.properties_backup.name.startswith("server.properties.bak-")
        assert result.properties_backup.is_file()
        text = props.read_text(encoding="utf-8")
        assert "resource-pack=http\\://192.168.90.14\\:8000/VPExample-v3-1.21.7-1.21.8_MCC.zip" in text
        assert f"resource-pack-sha1={sha1}" in text
        assert "resource-pack-id=" in text
        assert "11111111-1111-1111-1111-111111111111" not in text
        assert "motd=MyCyclingCity" in text
        assert "require-resource-pack=true" in text

        assert result.vehiclesplus_backup is not None
        assert result.vehiclesplus_backup.name.startswith("config.yml.bak-")
        assert f"resourcePackUrl: {url}" in cfg.read_text(encoding="utf-8")
        assert "enabled: true" in cfg.read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.django_db
class TestVehicleExportZip:
    def test_export_includes_hjson_model_and_textures(self, tmp_path):
        packs_dir = tmp_path / "mc-packs"
        packs_dir.mkdir()
        vehicles = tmp_path / "vehicles" / "bikes"
        vehicles.mkdir(parents=True)
        (vehicles / "bike_5.hjson").write_text(
            "{\n  id: bike_5\n  displayName: &aLastenrad\n"
            "  parts: [ { type: bikeskin, item: { custommodeldata: 9 } } ]\n}\n",
            encoding="utf-8",
        )
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with zipfile.ZipFile(packs_dir / "MCC.zip", "w") as zf:
            zf.writestr(
                "assets/vp/models/item/vehicles/bike_5.json",
                json.dumps({"credit": "test", "elements": []}),
            )
            zf.writestr("assets/vp/textures/item/vehicles/bike_5/bike_5.png", png)

        with override_settings(
            MCC_MINECRAFT_RESOURCE_PACKS_DIR=str(packs_dir),
            MCC_MINECRAFT_VEHICLESPLUS_VEHICLES_DIR=str(tmp_path / "vehicles"),
        ):
            from minecraft.services.vehiclesplus_pack_authoring import (
                build_vehicle_export_zip,
            )

            exported = build_vehicle_export_zip(
                model_id="bike_5",
                source_pack_name="MCC.zip",
            )

        assert exported.model_id == "bike_5"
        assert exported.has_model is True
        assert exported.texture_count == 1
        assert exported.custom_model_data == 9
        assert exported.filename.startswith("mcc-vp-bike_5-")
        with zipfile.ZipFile(__import__("io").BytesIO(exported.payload)) as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "vehicles/bikes/bike_5.hjson" in names
            assert (
                "Resource Pack/assets/vp/models/item/vehicles/bike_5.json" in names
            )
            assert any(
                n.startswith("Resource Pack/assets/vp/textures/item/vehicles/bike_5/")
                for n in names
            )
