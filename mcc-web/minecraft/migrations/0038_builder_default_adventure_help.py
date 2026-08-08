# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0037_paper_proxy_permission_label"),
    ]

    operations = [
        migrations.AlterField(
            model_name="minecraftteamregistration",
            name="prefer_gamemode",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Leer = Adventure. Werte: survival, adventure, spectator. "
                    "Überschreibt „Spectator bevorzugen“, wenn gesetzt. "
                    "Für Bau typischerweise leer lassen und Survival über die Session-GUI setzen."
                ),
                max_length=16,
                verbose_name="Bevorzugter Spielmodus",
            ),
        ),
    ]
