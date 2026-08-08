# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mgmt", "0017_game_end_sessions_on_round_stop_default"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gunicornconfig",
            name="bind_address",
            field=models.CharField(
                default="0.0.0.0:8001",
                help_text=(
                    "Adresse und Port für Gunicorn (Standard 0.0.0.0:8001 = alle Interfaces; "
                    "öffentlich erreichbar ist nur Apache:443)"
                ),
                max_length=100,
                verbose_name="Bind Adresse",
            ),
        ),
    ]
