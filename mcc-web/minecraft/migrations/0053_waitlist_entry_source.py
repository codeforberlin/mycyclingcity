# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0023_cyclistvelosredemption_redeem_permission"),
        ("minecraft", "0052_minecraft_accounts_and_operators"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftsessionwaitlistentry",
            name="source",
            field=models.CharField(
                choices=[
                    ("manual", "Manuell (Flyer/Counter)"),
                    ("velos_redeem", "Velos-Einlösung (RFID)"),
                ],
                db_index=True,
                default="manual",
                max_length=16,
                verbose_name="Herkunft",
            ),
        ),
        migrations.AddField(
            model_name="minecraftsessionwaitlistentry",
            name="cyclist",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="minecraft_waitlist_entries",
                to="api.cyclist",
                verbose_name="Radler (RFID-Einlösung)",
            ),
        ),
        migrations.AddField(
            model_name="minecraftsessionwaitlistentry",
            name="velos_redemption",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="minecraft_waitlist_entries",
                to="api.cyclistvelosredemption",
                verbose_name="Velos-Einlösung",
            ),
        ),
    ]
