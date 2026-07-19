# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("minecraft", "0005_shop_catalog_sidebar"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftshopitem",
            name="esgui_item_loc",
            field=models.CharField(
                blank=True,
                max_length=128,
                verbose_name="EconomyShopGUI Item-Index",
                help_text="z.B. page1.items.5 oder 23 — für Preis-Sync auf den MC-Server",
            ),
        ),
    ]
