# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("luanti", "0012_account_session_add_minutes"),
    ]

    operations = [
        migrations.CreateModel(
            name="LuantiRegisteredItem",
            fields=[
                (
                    "item_name",
                    models.CharField(
                        max_length=128,
                        primary_key=True,
                        serialize=False,
                        verbose_name="Itemstring",
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, max_length=256, verbose_name="Beschreibung"),
                ),
                (
                    "kind",
                    models.CharField(default="item", max_length=16, verbose_name="Art"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Aktualisiert"),
                ),
            ],
            options={
                "verbose_name": "Registriertes Luanti-Item",
                "verbose_name_plural": "Registrierte Luanti-Items",
                "ordering": ["item_name"],
            },
        ),
    ]
