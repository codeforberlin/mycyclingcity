# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations

# Tag preset must re-enable the day/night cycle (72). Tag (Mittag) keeps speed 0.
DAYTIME_STEPS = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "set_time_speed", "value": 72},
    {"op": "chat", "message": "Es ist Tag."},
]

DAYTIME_STEPS_WITHOUT_SPEED = [
    {"op": "set_weather", "value": "clear"},
    {"op": "set_time", "value": 6000},
    {"op": "chat", "message": "Es ist Tag."},
]


def add_time_speed(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    # Only the running-cycle Tag presets — not daytime-noon (frozen) or nighttime.
    LuantiCityPreset.objects.filter(slug__in=["daytime", "session-bootstrap"]).update(
        steps=DAYTIME_STEPS,
        description="Helle Tageszeit, klares Wetter, Tageszyklus läuft weiter",
    )


def revert_time_speed(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug__in=["daytime", "session-bootstrap"]).update(
        steps=DAYTIME_STEPS_WITHOUT_SPEED,
        description="Helle Tageszeit, klares Wetter",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("luanti", "0020_account_server_op"),
    ]

    operations = [
        migrations.RunPython(add_time_speed, revert_time_speed),
    ]
