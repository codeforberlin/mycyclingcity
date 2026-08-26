# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0011_enable_watch_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiaccount",
            name="session_add_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Schrittweite der ±-Buttons auf Session-Kacheln. Leer = globaler Standard.",
                null=True,
                verbose_name="Zeit-Schrittgröße (Min.)",
            ),
        ),
    ]
