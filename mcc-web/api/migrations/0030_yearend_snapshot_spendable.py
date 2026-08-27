# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0029_grant_transfer_group_velos"),
    ]

    operations = [
        migrations.AddField(
            model_name="yearendsnapshot",
            name="group_total_spendable",
            field=models.IntegerField(
                default=0,
                help_text="velos_spendable der TOP-Gruppe zum Abschlusszeitpunkt (wird nicht genullt)",
                verbose_name="Gruppen-Velos ausgebbar (TOP)",
            ),
        ),
        migrations.AddField(
            model_name="yearendsnapshotdetail",
            name="velos_spendable",
            field=models.IntegerField(
                default=0,
                help_text=(
                    "Nur für Gruppen relevant. Radler/Geräte: 0. "
                    "Spendable wird beim Abschluss nicht genullt — nur historisch gespeichert."
                ),
                verbose_name="Ausgebbare Velos zum Abschlusszeitpunkt",
            ),
        ),
    ]
