# Generated manually for shop catalog and sidebar config

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0004_team_scoreboard_v4"),
    ]

    operations = [
        migrations.AddField(
            model_name="minecraftintegrationconfig",
            name="sidebar_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Objective automatisch in der Sidebar anzeigen (setdisplay)",
                verbose_name="Sidebar-Anzeige aktiv",
            ),
        ),
        migrations.CreateModel(
            name="MinecraftShopCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64, unique=True, verbose_name="Slug")),
                ("name", models.CharField(max_length=64, verbose_name="Name")),
                (
                    "esgui_section",
                    models.CharField(
                        blank=True,
                        help_text="Leer = Slug",
                        max_length=64,
                        verbose_name="EconomyShopGUI-Section",
                    ),
                ),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Sortierung")),
                ("enabled", models.BooleanField(default=True, verbose_name="Aktiv")),
            ],
            options={
                "verbose_name": "Minecraft Shop Category",
                "verbose_name_plural": "Minecraft Shop Categories",
                "ordering": ["sort_order", "slug"],
            },
        ),
        migrations.CreateModel(
            name="MinecraftShopItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("material", models.CharField(max_length=64, verbose_name="Material")),
                ("display_name", models.CharField(blank=True, max_length=128, verbose_name="Anzeigename")),
                ("buy_price_velos", models.PositiveIntegerField(verbose_name="Kaufpreis (Velos)")),
                ("stack_size", models.PositiveIntegerField(default=1, verbose_name="Stack-Größe")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Sortierung")),
                ("enabled", models.BooleanField(default=True, verbose_name="Aktiv")),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="minecraft.minecraftshopcategory",
                        verbose_name="Kategorie",
                    ),
                ),
            ],
            options={
                "verbose_name": "Minecraft Shop Item",
                "verbose_name_plural": "Minecraft Shop Items",
                "ordering": ["category", "sort_order", "material"],
            },
        ),
    ]
