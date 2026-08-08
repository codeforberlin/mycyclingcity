# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0028_mcsession_gamemode_spectator_db_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftarenamotionsettings",
            name="end_device_sessions_on_race_start",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Beim Velo-Arena-Start werden aktive Geräte-Sessions der "
                    "zugewiesenen Radler beendet (Session-km/Velos starten bei 0; "
                    "Standalone-Radler am Counter bleiben aktiv). OLED-Sperre wird "
                    "unabhängig davon gelöst."
                ),
                verbose_name="Geräte-Sessions bei Rennstart beenden",
            ),
        ),
    ]
