# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0013_luanti_registered_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiintegrationconfig",
            name="session_end_warning_seconds",
            field=models.PositiveIntegerField(
                default=60,
                help_text=(
                    "Spieler erhält eine Chat-Warnung so viele Sekunden vor Session-Ende. "
                    "0 = keine Warnung."
                ),
                verbose_name="Session-Ende-Warnung (Sek.)",
            ),
        ),
        migrations.AddField(
            model_name="luantisession",
            name="end_warning_sent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Zeitpunkt der Chat-Vorwarnung vor Session-Ende.",
                null=True,
                verbose_name="Ende-Warnung gesendet",
            ),
        ),
    ]
