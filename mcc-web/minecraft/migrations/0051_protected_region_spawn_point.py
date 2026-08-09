# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0050_mcsession_spawn_region"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="spawn_x",
            field=models.IntegerField(
                blank=True,
                help_text="Optionaler Session-Spawn. Leer = automatische Cuboid-Mitte.",
                null=True,
                verbose_name="Spawn X",
            ),
        ),
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="spawn_y",
            field=models.IntegerField(blank=True, null=True, verbose_name="Spawn Y"),
        ),
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="spawn_z",
            field=models.IntegerField(blank=True, null=True, verbose_name="Spawn Z"),
        ),
    ]
