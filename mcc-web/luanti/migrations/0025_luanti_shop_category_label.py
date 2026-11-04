# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models
import django.db.models.deletion


def migrate_category_names_to_de_labels(apps, schema_editor):
    LuantiShopCategory = apps.get_model("luanti", "LuantiShopCategory")
    LuantiShopCategoryLabel = apps.get_model("luanti", "LuantiShopCategoryLabel")
    for cat in LuantiShopCategory.objects.exclude(name="").iterator():
        LuantiShopCategoryLabel.objects.update_or_create(
            category_id=cat.pk,
            language_code="de",
            defaults={"display_name": (cat.name or "")[:64]},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0024_luanti_shop_item_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="LuantiShopCategoryLabel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("language_code", models.CharField(max_length=16, verbose_name="Sprachcode")),
                ("display_name", models.CharField(max_length=64, verbose_name="Anzeigename")),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="luanti.luantishopcategory",
                        verbose_name="Shop-Kategorie",
                    ),
                ),
            ],
            options={
                "verbose_name": "Shop-Kategorie-Übersetzung",
                "verbose_name_plural": "Shop-Kategorie-Übersetzungen",
                "ordering": ["category", "language_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="luantishopcategorylabel",
            constraint=models.UniqueConstraint(
                fields=("category", "language_code"),
                name="luanti_shop_category_label_unique",
            ),
        ),
        migrations.RunPython(migrate_category_names_to_de_labels, migrations.RunPython.noop),
    ]
