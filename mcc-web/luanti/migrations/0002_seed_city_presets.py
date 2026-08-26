# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def seed_presets(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    defaults = [
        {
            "slug": "daytime",
            "name": "Tag",
            "description": "Helle Tageszeit",
            "steps": [{"op": "set_time", "value": 6000}, {"op": "chat", "message": "Es ist Tag."}],
            "sort_order": 10,
        },
        {
            "slug": "nighttime",
            "name": "Nacht",
            "description": "Nachtzeit",
            "steps": [{"op": "set_time", "value": 18000}, {"op": "chat", "message": "Es ist Nacht."}],
            "sort_order": 20,
        },
    ]
    for row in defaults:
        LuantiCityPreset.objects.get_or_create(slug=row["slug"], defaults=row)


def unseed(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug__in=["daytime", "nighttime"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0001_luanti_integration"),
    ]

    operations = [
        migrations.RunPython(seed_presets, unseed),
    ]
