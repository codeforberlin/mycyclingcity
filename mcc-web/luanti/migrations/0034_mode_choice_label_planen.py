# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0033_luantiplayerinventory_sell_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="luantiaccount",
            name="default_mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planen"),
                    ("build", "Bauen"),
                    ("watch", "Zuschauen"),
                ],
                default="play",
                max_length=16,
                verbose_name="Standard-Modus",
            ),
        ),
        migrations.AlterField(
            model_name="luantisession",
            name="mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planen"),
                    ("build", "Bauen"),
                    ("watch", "Zuschauen"),
                ],
                default="play",
                max_length=16,
                verbose_name="Modus",
            ),
        ),
        migrations.AlterField(
            model_name="luantiplayerinventory",
            name="mode",
            field=models.CharField(
                choices=[
                    ("play", "Spielen"),
                    ("plan", "Planen"),
                    ("build", "Bauen"),
                ],
                max_length=16,
                verbose_name="Modus",
            ),
        ),
    ]