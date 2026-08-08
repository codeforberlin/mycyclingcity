# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("iot", "0015_device_display_velos_lock"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="is_arena_sim_allowed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Nur freigegebene Geräte dürfen in der Arena-Simulation "
                    "(intern oder über die API) verwendet werden."
                ),
                verbose_name="Arena-/API-Simulation erlaubt",
            ),
        ),
    ]
