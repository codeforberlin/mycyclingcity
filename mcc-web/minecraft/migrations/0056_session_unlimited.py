# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0055_world_tickets"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="session_unlimited",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Kein Zeitlimit beim Admin-Start. Session endet bei manuellem Kick "
                    "oder wenn der Spieler den Server verlässt (Logout). "
                    "Wartelisten-Zuweisungen bleiben zeitbegrenzt."
                ),
                verbose_name="Unbegrenzte Session",
            ),
        ),
        migrations.AddField(
            model_name="minecraftteamregistration",
            name="session_unlimited",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Kein Zeitlimit beim Admin-Start. Session endet bei manuellem Kick "
                    "oder wenn der Spieler den Server verlässt (Logout). "
                    "Wartelisten-Zuweisungen bleiben zeitbegrenzt."
                ),
                verbose_name="Unbegrenzte Session",
            ),
        ),
        migrations.AlterField(
            model_name="mcsession",
            name="duration_minutes",
            field=models.PositiveIntegerField(
                help_text="0 = unbegrenzte Session (ends_at ist dann leer).",
                verbose_name="Dauer (Minuten)",
            ),
        ),
        migrations.AlterField(
            model_name="mcsession",
            name="ends_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Leer bei unbegrenzter Session (kein Timeout).",
                null=True,
                verbose_name="Geplantes Ende",
            ),
        ),
    ]
