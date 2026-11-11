# Generated manually for Luanti planning mode.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_yearend_snapshot_spendable"),
        ("luanti", "0026_luanti_registered_item_icon_meta"),
    ]

    operations = [
        migrations.AddField(
            model_name="luantiprotectedregion",
            name="plan_funding_include_master_top",
            field=models.BooleanField(
                default=True,
                help_text="Spendable Velos der Master-TOP-Gruppe fließen in den Umwandlungs-Pool dieser Zone.",
                verbose_name="TOP der Master-Region für Plan-Velos",
            ),
        ),
        migrations.AlterField(
            model_name="luantishoptransaction",
            name="side",
            field=models.CharField(
                choices=[
                    ("buy", "Kauf"),
                    ("sell", "Verkauf"),
                    ("plan_buy", "Plan-Kauf"),
                ],
                max_length=8,
            ),
        ),
        migrations.CreateModel(
            name="LuantiRegionPlanFunding",
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
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Sortierung")),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="luanti_plan_funding_regions",
                        to="api.group",
                        verbose_name="Gruppe",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plan_funding_links",
                        to="luanti.luantiprotectedregion",
                        verbose_name="Region",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plan-Velos Gruppe",
                "verbose_name_plural": "Plan-Velos Gruppen",
                "ordering": ["sort_order", "group_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="luantiregionplanfunding",
            constraint=models.UniqueConstraint(
                fields=("region", "group"),
                name="luanti_region_plan_funding_unique",
            ),
        ),
        migrations.CreateModel(
            name="LuantiPlanBlock",
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
                ("world", models.CharField(default="world", max_length=64, verbose_name="Welt")),
                ("x", models.IntegerField(verbose_name="X")),
                ("y", models.IntegerField(verbose_name="Y")),
                ("z", models.IntegerField(verbose_name="Z")),
                (
                    "shop_item_id",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Shop-Artikel-ID"
                    ),
                ),
                ("target_name", models.CharField(max_length=128, verbose_name="Ziel-Item")),
                (
                    "buy_price_velos",
                    models.PositiveIntegerField(verbose_name="Umwandlungspreis (Velos)"),
                ),
                ("param2", models.PositiveSmallIntegerField(default=0, verbose_name="Param2")),
                (
                    "placed_by",
                    models.CharField(blank=True, max_length=32, verbose_name="Platziert von"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("planned", "Geplant"), ("materialized", "Umgewandelt")],
                        db_index=True,
                        default="planned",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plan_blocks",
                        to="luanti.luantiprotectedregion",
                        verbose_name="Region",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plan-Block",
                "verbose_name_plural": "Plan-Blöcke",
            },
        ),
        migrations.AddIndex(
            model_name="luantiplanblock",
            index=models.Index(fields=["region", "status"], name="luanti_plan_region_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="luantiplanblock",
            constraint=models.UniqueConstraint(
                fields=("world", "x", "y", "z"),
                name="luanti_plan_block_pos_unique",
            ),
        ),
        migrations.CreateModel(
            name="LuantiPlanMaterializeTransaction",
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
                (
                    "client_tx_id",
                    models.CharField(max_length=64, unique=True, verbose_name="Client-Tx-ID"),
                ),
                ("world", models.CharField(default="world", max_length=64)),
                ("x", models.IntegerField()),
                ("y", models.IntegerField()),
                ("z", models.IntegerField()),
                ("velos_delta", models.IntegerField(verbose_name="Velos-Delta")),
                ("login_name", models.CharField(blank=True, db_index=True, max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="luanti_plan_materialize_txs",
                        to="api.group",
                        verbose_name="Gruppe",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plan_materialize_txs",
                        to="luanti.luantiprotectedregion",
                        verbose_name="Region",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plan-Umwandlungs-Transaktion",
                "verbose_name_plural": "Plan-Umwandlungs-Transaktionen",
                "ordering": ["-created_at"],
            },
        ),
    ]
