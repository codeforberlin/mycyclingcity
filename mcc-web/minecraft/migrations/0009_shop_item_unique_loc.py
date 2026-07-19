# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


def backfill_shop_item_locations(apps, schema_editor):
    item_model = apps.get_model("minecraft", "MinecraftShopItem")
    for item in item_model.objects.all():
        loc = (item.esgui_item_loc or "").strip()
        if not loc:
            item.esgui_item_loc = f"legacy.{item.pk}"
            item.save(update_fields=["esgui_item_loc"])
        if not (item.esgui_item_key or "").strip() and ".items." in item.esgui_item_loc:
            item.esgui_item_key = item.esgui_item_loc.rsplit(".items.", 1)[-1]
            item.save(update_fields=["esgui_item_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0008_rcon_presets"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftshopitem",
            name="esgui_item_key",
            field=models.CharField(
                blank=True,
                help_text="Kurzschlüssel aus der Shop-YAML (z. B. super_pickaxe)",
                max_length=128,
                verbose_name="EconomyShopGUI Item-Key",
            ),
        ),
        migrations.RunPython(backfill_shop_item_locations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="minecraftshopitem",
            name="esgui_item_loc",
            field=models.CharField(
                help_text="Eindeutige Position in der Shop-YAML, z. B. page1.items.super_pickaxe",
                max_length=128,
                verbose_name="EconomyShopGUI Item-Index",
            ),
        ),
        migrations.AddConstraint(
            model_name="minecraftshopitem",
            constraint=models.UniqueConstraint(
                fields=("category", "esgui_item_loc"),
                name="minecraft_shop_item_unique_loc",
            ),
        ),
    ]
