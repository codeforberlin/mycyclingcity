# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

import pytest

from minecraft.services.vehiclesplus_catalog import (
    list_vehiclesplus_models,
    parse_vehiclesplus_hjson,
    strip_minecraft_colors,
    vehiclesplus_models_by_category,
)


SAMPLE_HJSON = """
{
  id: ExampleBike
  displayName: &cExample &aBike
  typeId: bikes
  price: 100000
}
"""


@pytest.mark.unit
class TestVehiclesPlusCatalogParse:
    def test_strip_colors(self):
        assert strip_minecraft_colors("&cExample &aBike") == "Example Bike"
        assert strip_minecraft_colors("§cRed §fWhite") == "Red White"

    def test_parse_hjson(self):
        model_id, display = parse_vehiclesplus_hjson(SAMPLE_HJSON)
        assert model_id == "ExampleBike"
        assert display == "Example Bike"

    def test_parse_fallback_id(self):
        model_id, display = parse_vehiclesplus_hjson(
            "{ displayName: Plain }\n",
            fallback_id="FromFile",
        )
        assert model_id == "FromFile"
        assert display == "Plain"


@pytest.mark.unit
class TestVehiclesPlusCatalogScan:
    def test_list_from_temp_tree(self, tmp_path: Path):
        bikes = tmp_path / "bikes"
        cars = tmp_path / "cars"
        bikes.mkdir()
        cars.mkdir()
        (bikes / "ExampleBike.hjson").write_text(SAMPLE_HJSON, encoding="utf-8")
        (cars / "ExampleCar.hjson").write_text(
            "{\n  id: ExampleCar\n  displayName: Fast Car\n}\n",
            encoding="utf-8",
        )
        models = list_vehiclesplus_models(root=tmp_path)
        assert [m.model_id for m in models] == ["ExampleBike", "ExampleCar"]
        assert models[0].category == "bikes"
        assert models[0].display_name == "Example Bike"
        groups = vehiclesplus_models_by_category(root=tmp_path)
        assert [c for c, _ in groups] == ["bikes", "cars"]

    def test_missing_dir(self, tmp_path: Path):
        assert list_vehiclesplus_models(root=tmp_path / "missing") == []
