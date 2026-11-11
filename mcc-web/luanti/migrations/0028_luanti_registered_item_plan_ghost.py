# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0027_luanti_plan_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiregistereditem",
            name="plan_ghost_status",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="Plan-Hologramm-Status",
                help_text="Vom Luanti-Server: shape = Form-Klon, fallback = Glaswürfel, na = kein Node.",
            ),
        ),
        migrations.AddField(
            model_name="luantiregistereditem",
            name="plan_ghost_detail",
            field=models.CharField(
                blank=True,
                default="",
                max_length=128,
                verbose_name="Plan-Hologramm-Detail",
            ),
        ),
        migrations.AddField(
            model_name="luantiregistereditem",
            name="plan_ghost_checked_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Plan-Hologramm geprüft am",
            ),
        ),
    ]
