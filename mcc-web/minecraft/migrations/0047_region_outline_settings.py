# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0046_shop_purchase_credit"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="region_outline_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Wenn aktiv: MCC-Bridge zeichnet farbige Partikel-Umrandungen "
                    "für geschützte Regionen in Spieler-Nähe."
                ),
                verbose_name="Region-Markierung (Partikel) aktiv",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="region_outline_enter_hint",
            field=models.BooleanField(
                default=True,
                help_text="Actionbar mit Anzeigename, wenn ein Spieler eine Region betritt.",
                verbose_name="Hinweis beim Betreten der Region",
            ),
        ),
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="region_outline_view_distance",
            field=models.PositiveIntegerField(
                default=48,
                help_text="Partikel nur, wenn ein Spieler so nah an der Region ist. Minimum 8.",
                validators=[django.core.validators.MinValueValidator(8)],
                verbose_name="Sichtweite Region-Markierung (Blöcke)",
            ),
        ),
    ]
