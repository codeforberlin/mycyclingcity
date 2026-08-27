# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0018_session_teleport_to_spawn"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantisession",
            name="spawn_region",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Wenn gesetzt: Session startete mit Teleport in diese Region "
                    "(statt Welt-Spawn)."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions_spawned_here",
                to="luanti.luantiprotectedregion",
                verbose_name="Spawn-Region",
            ),
        ),
    ]
