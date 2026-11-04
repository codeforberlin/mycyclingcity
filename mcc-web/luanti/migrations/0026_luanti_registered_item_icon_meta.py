# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0025_luanti_shop_category_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiregistereditem",
            name="drawtype",
            field=models.CharField(blank=True, max_length=32, verbose_name="Drawtype"),
        ),
        migrations.AddField(
            model_name="luantiregistereditem",
            name="inventory_image",
            field=models.CharField(blank=True, max_length=128, verbose_name="Inventarbild"),
        ),
        migrations.AddField(
            model_name="luantiregistereditem",
            name="wield_image",
            field=models.CharField(blank=True, max_length=128, verbose_name="Wield-Bild"),
        ),
        migrations.AddField(
            model_name="luantiregistereditem",
            name="not_in_creative_inventory",
            field=models.BooleanField(default=False, verbose_name="Nicht im Kreativ-Inventar"),
        ),
    ]
