# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models
import django.db.models.deletion


def migrate_display_names_to_de_labels(apps, schema_editor):
    LuantiShopItem = apps.get_model("luanti", "LuantiShopItem")
    LuantiShopItemLabel = apps.get_model("luanti", "LuantiShopItemLabel")
    for item in LuantiShopItem.objects.exclude(display_name="").iterator():
        LuantiShopItemLabel.objects.update_or_create(
            item_id=item.pk,
            language_code="de",
            defaults={"display_name": (item.display_name or "")[:128]},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0023_luanti_login_password_permissions"),
    ]

    operations = [
        migrations.CreateModel(
            name="LuantiShopItemLabel",
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
                ("display_name", models.CharField(max_length=128, verbose_name="Anzeigename")),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="luanti.luantishopitem",
                        verbose_name="Shop-Artikel",
                    ),
                ),
            ],
            options={
                "verbose_name": "Shop-Artikel-Übersetzung",
                "verbose_name_plural": "Shop-Artikel-Übersetzungen",
                "ordering": ["item", "language_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="luantishopitemlabel",
            constraint=models.UniqueConstraint(
                fields=("item", "language_code"),
                name="luanti_shop_item_label_unique",
            ),
        ),
        migrations.RunPython(migrate_display_names_to_de_labels, migrations.RunPython.noop),
    ]
