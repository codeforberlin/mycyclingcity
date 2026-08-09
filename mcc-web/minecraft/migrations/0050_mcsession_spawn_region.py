# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0049_protected_region_sort_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcsession",
            name="spawn_region",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Wenn gesetzt: Session startete mit Teleport in diese geschützte "
                    "Region (statt Welt-Spawn)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions_spawned_here",
                to="minecraft.minecraftprotectedregion",
                verbose_name="Spawn-Region",
            ),
        ),
    ]
