# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


def backfill_sort_order(apps, schema_editor):
    Region = apps.get_model("minecraft", "MinecraftProtectedRegion")
    # Masters first, then subs grouped by parent — assign 0,10,20,… per sibling group.
    masters = list(
        Region.objects.filter(parent__isnull=True).order_by("region_id", "pk")
    )
    for i, master in enumerate(masters):
        if master.sort_order != i * 10:
            Region.objects.filter(pk=master.pk).update(sort_order=i * 10)
        subs = list(
            Region.objects.filter(parent_id=master.pk).order_by("region_id", "pk")
        )
        for j, sub in enumerate(subs):
            if sub.sort_order != j * 10:
                Region.objects.filter(pk=sub.pk).update(sort_order=j * 10)


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0048_protected_region_top_assignment"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="minecraftprotectedregion",
            options={
                "ordering": ["sort_order", "region_id"],
                "verbose_name": "Geschützte Region",
                "verbose_name_plural": "Geschützte Regionen",
            },
        ),
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="sort_order",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Reihenfolge in der Liste (Master untereinander, Subs je Master).",
                verbose_name="Sortierung",
            ),
        ),
        migrations.RunPython(backfill_sort_order, migrations.RunPython.noop),
    ]
