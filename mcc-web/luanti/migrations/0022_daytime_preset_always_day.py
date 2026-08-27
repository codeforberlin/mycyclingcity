# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations

# Always-day Tag preset: noon + frozen clock (not time_speed 72).
DAYTIME_ALWAYS_STEPS = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "set_time_speed", "value": 0},
    {"op": "chat", "message": "Es ist Tag."},
]

DAYTIME_CYCLE_STEPS = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "set_time_speed", "value": 72},
    {"op": "chat", "message": "Es ist Tag."},
]


def freeze_daytime(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug__in=["daytime", "session-bootstrap"]).update(
        steps=DAYTIME_ALWAYS_STEPS,
        description="Immer Tag: Mittag, klares Wetter, Zeit eingefroren",
    )


def revert_freeze(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug__in=["daytime", "session-bootstrap"]).update(
        steps=DAYTIME_CYCLE_STEPS,
        description="Helle Tageszeit, klares Wetter, Tageszyklus läuft weiter",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("luanti", "0021_daytime_preset_time_speed"),
    ]

    operations = [
        migrations.RunPython(freeze_daytime, revert_freeze),
    ]
