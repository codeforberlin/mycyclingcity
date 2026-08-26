# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def fix_nighttime(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    # 18000 (=0.75) is dusk; Mineclonia sky is dark only outside ~0.2–0.8.
    # Use midnight (0) for an immediate dark night.
    LuantiCityPreset.objects.filter(slug="nighttime").update(
        steps=[{"op": "set_time", "value": 0}, {"op": "chat", "message": "Es ist Nacht."}],
        description="Nachtzeit (Mitternacht)",
    )


def revert_nighttime(apps, schema_editor):
    LuantiCityPreset = apps.get_model("luanti", "LuantiCityPreset")
    LuantiCityPreset.objects.filter(slug="nighttime").update(
        steps=[{"op": "set_time", "value": 18000}, {"op": "chat", "message": "Es ist Nacht."}],
        description="Nachtzeit",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("luanti", "0004_pending_command"),
    ]

    operations = [
        migrations.RunPython(fix_nighttime, revert_nighttime),
    ]
