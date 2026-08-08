# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.validators import MinValueValidator
from django.db import migrations, models


def forwards_set_min_velos(apps, schema_editor):
    MinecraftShopItem = apps.get_model("minecraft", "MinecraftShopItem")
    MinecraftShopItem.objects.filter(buy_price_velos__lt=1).update(buy_price_velos=1)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0029_arena_end_device_sessions_on_race_start"),
    ]

    operations = [
        migrations.RunPython(forwards_set_min_velos, backwards_noop),
        migrations.AlterField(
            model_name="minecraftshopitem",
            name="buy_price_velos",
            field=models.PositiveIntegerField(
                help_text="Mindestens 1 Velo — kostenlose Artikel (0) sind nicht erlaubt.",
                validators=[MinValueValidator(1)],
                verbose_name="Kaufpreis (Velos)",
            ),
        ),
    ]
