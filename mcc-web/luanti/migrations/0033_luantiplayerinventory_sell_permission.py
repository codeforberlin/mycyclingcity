# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0032_plan_materialize_credit_group"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="luantiplayerinventory",
            options={
                "permissions": [
                    (
                        "sell_luantiplayerinventory",
                        "Spieler-Inventar verkaufen (Admin)",
                    ),
                ],
                "verbose_name": "Spieler-Inventar",
                "verbose_name_plural": "Spieler-Inventare",
            },
        ),
    ]