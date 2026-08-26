# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


DAY_STEPS = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "chat", "message": "Es ist Tag."},
]

NIGHT_STEPS = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 0},
    {"op": "chat", "message": "Es ist Nacht."},
]


def update_presets(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug="daytime").update(steps=DAY_STEPS)
    LuantiCityPreset.objects.filter(slug="nighttime").update(
        steps=NIGHT_STEPS,
        description="Nachtzeit (Mitternacht, klar)",
    )


def revert_presets(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug="daytime").update(
        steps=[
            {"op": "set_time", "value": 6000},
            {"op": "chat", "message": "Es ist Tag."},
        ]
    )
    LuantiCityPreset.objects.filter(slug="nighttime").update(
        steps=[
            {"op": "set_time", "value": 0},
            {"op": "chat", "message": "Es ist Nacht."},
        ],
        description="Nachtzeit (Mitternacht)",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("luanti", "0005_fix_nighttime_midnight"),
    ]

    operations = [
        migrations.RunPython(update_presets, revert_presets),
    ]
