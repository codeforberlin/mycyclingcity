# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0041_protected_regions_worldguard"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcsession",
            name="teleport_to_spawn",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text=(
                    "Wenn gesetzt: nach Login zum Welt-/Lobby-Spawn teleportieren. "
                    "Sonst Minecraft-Standard (letzte Position)."
                ),
                verbose_name="Zum Welt-Spawn beim Start",
            ),
        ),
        migrations.AlterField(
            model_name="minecraftprotectedregion",
            name="protect_build",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Wenn aktiv: WorldGuard-Standardschutz (Nicht-Mitglieder dürfen nicht bauen). "
                    "Nicht das Flag „build deny“ — das würde auch Members blockieren."
                ),
                verbose_name="Bauen schützen",
            ),
        ),
    ]
