# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0009_wallet_assignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiintegrationconfig",
            name="session_min_minutes",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Fallback, wenn am Account kein Minimum gesetzt ist.",
                verbose_name="Standard-Minimum Dauer (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="luantiintegrationconfig",
            name="session_max_minutes",
            field=models.PositiveIntegerField(
                default=180,
                help_text="Fallback, wenn am Account kein Maximum gesetzt ist.",
                verbose_name="Standard-Maximum Dauer (Min.)",
            ),
        ),
        migrations.AlterField(
            model_name="luantiintegrationconfig",
            name="session_add_minutes",
            field=models.PositiveIntegerField(
                default=15,
                verbose_name="Zeit hinzufügen/kürzen (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="luantiaccount",
            name="session_duration_min_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Untergrenze für Start/Kürzung. Leer = globaler Standard.",
                null=True,
                verbose_name="Min. Dauer (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="luantiaccount",
            name="session_duration_max_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Obergrenze für Start/Verlängerung. Leer = globaler Standard.",
                null=True,
                verbose_name="Max. Dauer (Min.)",
            ),
        ),
        migrations.AddField(
            model_name="luantisession",
            name="paused_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Pausiert seit"),
        ),
        migrations.AddField(
            model_name="luantisession",
            name="remaining_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Gespeicherte Restzeit während STATUS_PAUSED.",
                null=True,
                verbose_name="Restzeit bei Pause (Sek.)",
            ),
        ),
        migrations.AlterField(
            model_name="luantisession",
            name="status",
            field=models.CharField(
                choices=[
                    ("READY", "Bereit"),
                    ("ACTIVE", "Aktiv"),
                    ("PAUSED", "Pausiert"),
                    ("FINISHED", "Beendet"),
                ],
                db_index=True,
                default="READY",
                max_length=16,
                verbose_name="Status",
            ),
        ),
    ]
