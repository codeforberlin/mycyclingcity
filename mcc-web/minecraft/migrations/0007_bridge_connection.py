# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("minecraft", "0006_shop_item_esgui_loc"),
    ]

    operations = [
        migrations.CreateModel(
            name="MinecraftBridgeConnection",
            fields=[
                (
                    "server_id",
                    models.CharField(max_length=64, primary_key=True, serialize=False, verbose_name="Server ID"),
                ),
                ("is_connected", models.BooleanField(default=False, verbose_name="Verbunden")),
                ("connected_at", models.DateTimeField(blank=True, null=True, verbose_name="Verbunden seit")),
                ("last_seen_at", models.DateTimeField(blank=True, null=True, verbose_name="Zuletzt gesehen")),
            ],
            options={
                "verbose_name": "Minecraft Bridge Connection",
                "verbose_name_plural": "Minecraft Bridge Connections",
            },
        ),
    ]
