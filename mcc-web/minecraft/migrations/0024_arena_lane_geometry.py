# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


def create_solo_settings(apps, schema_editor):
    settings_model = apps.get_model("minecraft", "MinecraftArenaMotionSettings")
    settings_model.objects.get_or_create(pk=1)


def delete_solo_settings(apps, schema_editor):
    settings_model = apps.get_model("minecraft", "MinecraftArenaMotionSettings")
    settings_model.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0023_waitlist_assigned_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="MinecraftArenaMotionSettings",
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
                    "tick_interval_seconds",
                    models.FloatField(default=0.1, verbose_name="Tick-Intervall (s)"),
                ),
                (
                    "motion_min_distance",
                    models.FloatField(
                        default=0.03,
                        verbose_name="Min. Bewegungsdistanz für Motion",
                    ),
                ),
                (
                    "lap_cooldown_ticks",
                    models.PositiveIntegerField(
                        default=30, verbose_name="Lap-Cooldown (Ticks)"
                    ),
                ),
                (
                    "actionbar_enabled",
                    models.BooleanField(default=True, verbose_name="Actionbar-Ansagen"),
                ),
                (
                    "cart_name_visible",
                    models.BooleanField(
                        default=True, verbose_name="Floating-Labels an Loren"
                    ),
                ),
                (
                    "reference_mps",
                    models.FloatField(
                        default=2.0, verbose_name="Referenz-Geschwindigkeit (m/s)"
                    ),
                ),
                (
                    "min_motion_speed",
                    models.FloatField(default=0.08, verbose_name="Min. Motion"),
                ),
                (
                    "max_motion_speed",
                    models.FloatField(default=0.55, verbose_name="Max. Motion"),
                ),
                (
                    "default_impulse_x",
                    models.FloatField(default=0.0, verbose_name="Default-Impuls X"),
                ),
                (
                    "default_impulse_y",
                    models.FloatField(default=0.0, verbose_name="Default-Impuls Y"),
                ),
                (
                    "default_impulse_z",
                    models.FloatField(default=1.0, verbose_name="Default-Impuls Z"),
                ),
                (
                    "prefer_database_lanes",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Wenn aktiv und mindestens eine aktive Bahn existiert, "
                            "wird die TOML-Datei ignoriert."
                        ),
                        verbose_name="Bahn-Geometrie aus Datenbank nutzen",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Arena-Motion-Einstellungen",
                "verbose_name_plural": "Arena-Motion-Einstellungen",
            },
        ),
        migrations.CreateModel(
            name="MinecraftArenaLane",
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
                    "lane_id",
                    models.SlugField(
                        help_text="Stabiler Schlüssel, z. B. lane_1",
                        max_length=64,
                        unique=True,
                        verbose_name="Bahn-ID",
                    ),
                ),
                ("name", models.CharField(max_length=64, verbose_name="Anzeigename")),
                (
                    "tag",
                    models.CharField(
                        help_text="Minecraft-Entity-Tag, z. B. velo_lane_1",
                        max_length=64,
                        verbose_name="Minecart-Tag",
                    ),
                ),
                (
                    "color",
                    models.CharField(
                        default="white",
                        help_text="Minecraft-Farbname für text_display",
                        max_length=32,
                        verbose_name="Label-Farbe",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Sortierung"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktiv")),
                ("start_x", models.FloatField(verbose_name="Start X")),
                ("start_y", models.FloatField(verbose_name="Start Y")),
                ("start_z", models.FloatField(verbose_name="Start Z")),
                ("yaw", models.FloatField(default=0.0, verbose_name="Yaw")),
                ("pitch", models.FloatField(default=0.0, verbose_name="Pitch")),
                (
                    "base_speed",
                    models.FloatField(default=0.4, verbose_name="Basis-Motion"),
                ),
                ("finish_x_min", models.FloatField(verbose_name="Ziel X min")),
                ("finish_x_max", models.FloatField(verbose_name="Ziel X max")),
                ("finish_z_trigger", models.FloatField(verbose_name="Ziel Z-Trigger")),
                ("impulse_x", models.FloatField(default=0.0, verbose_name="Impuls X")),
                ("impulse_y", models.FloatField(default=0.0, verbose_name="Impuls Y")),
                ("impulse_z", models.FloatField(default=1.0, verbose_name="Impuls Z")),
                (
                    "sign_x",
                    models.FloatField(blank=True, null=True, verbose_name="Schild X"),
                ),
                (
                    "sign_y",
                    models.FloatField(blank=True, null=True, verbose_name="Schild Y"),
                ),
                (
                    "sign_z",
                    models.FloatField(blank=True, null=True, verbose_name="Schild Z"),
                ),
                (
                    "notes",
                    models.CharField(blank=True, max_length=255, verbose_name="Notiz"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Arena-Bahn (Geometrie)",
                "verbose_name_plural": "Arena-Bahnen (Geometrie)",
                "ordering": ["sort_order", "lane_id"],
            },
        ),
        migrations.RunPython(create_solo_settings, delete_solo_settings),
    ]
