# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0017_region_outline_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantisession",
            name="teleport_to_spawn",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text=(
                    "Wenn gesetzt: nach Freigabe einmal zum static_spawnpoint "
                    "teleportieren. Sonst letzte Spielerposition behalten."
                ),
                verbose_name="Zum Welt-Spawn beim Start",
            ),
        ),
    ]
