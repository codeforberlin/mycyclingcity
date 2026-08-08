# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def grant_manage_protected_regions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_protected_regions",
        defaults={"name": "Geschützte Regionen (WorldGuard)"},
    )
    for group_name in ("mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_manage_protected_regions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="manage_protected_regions"
    ).first()
    if perm is None:
        return
    for group in Group.objects.filter(name__in=["mcc_operator", "Operatoren"]):
        group.permissions.remove(perm)
    perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0040_manage_coreprotect_permission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="minecraftintegrationconfig",
            options={
                "permissions": [
                    ("access_minecraft_control", "Control öffnen"),
                    ("access_minecraft_city", "Stadtsteuerung öffnen"),
                    ("access_minecraft_shop", "Shop-Betrieb öffnen"),
                    ("run_free_rcon", "Freie RCON-Befehle senden"),
                    ("manage_player_sessions", "Spieler-Sessions verwalten"),
                    ("manage_builder_sessions", "Builder-Sessions verwalten"),
                    ("run_arena_sim", "Velo-Arena Simulation starten"),
                    ("manage_minecraft_proxy", "Velocity / Limbo / Paper steuern"),
                    ("manage_auth_failover", "Auth-Failover / Playerdata-Transfer"),
                    ("manage_coreprotect", "CoreProtect Rollback/Restore"),
                    ("manage_protected_regions", "Geschützte Regionen (WorldGuard)"),
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.CreateModel(
            name="MinecraftProtectedRegion",
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
                    "region_id",
                    models.SlugField(
                        help_text="WorldGuard-Regionsname (a–z, 0–9, _, -).",
                        max_length=64,
                        unique=True,
                        verbose_name="Region-ID",
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        blank=True, max_length=120, verbose_name="Anzeigename"
                    ),
                ),
                (
                    "world",
                    models.CharField(
                        default="MyCyclingCity", max_length=64, verbose_name="Welt"
                    ),
                ),
                ("min_x", models.IntegerField(verbose_name="Min X")),
                ("min_y", models.IntegerField(default=-64, verbose_name="Min Y")),
                ("min_z", models.IntegerField(verbose_name="Min Z")),
                ("max_x", models.IntegerField(verbose_name="Max X")),
                ("max_y", models.IntegerField(default=320, verbose_name="Max Y")),
                ("max_z", models.IntegerField(verbose_name="Max Z")),
                (
                    "protect_build",
                    models.BooleanField(
                        default=True,
                        help_text="Nicht-Mitglieder dürfen in der Region nicht bauen.",
                        verbose_name="Bauen sperren (build deny)",
                    ),
                ),
                (
                    "synced_members",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="MS-Logins, die zuletzt per RCON als Member gesetzt wurden.",
                        verbose_name="Zuletzt synchronisierte Members",
                    ),
                ),
                (
                    "last_synced_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Zuletzt synchronisiert"
                    ),
                ),
                (
                    "last_sync_error",
                    models.TextField(blank=True, verbose_name="Letzter Sync-Fehler"),
                ),
                (
                    "notes",
                    models.CharField(blank=True, max_length=255, verbose_name="Notiz"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "builders",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Verknüpfte Bau-Registrierungen; Sync setzt WorldGuard-Members "
                            "auf deren Microsoft-Login (ms_username)."
                        ),
                        related_name="protected_regions",
                        to="minecraft.minecraftteamregistration",
                        verbose_name="Bau-Accounts (Mitglieder)",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Geändert von",
                    ),
                ),
            ],
            options={
                "verbose_name": "Geschützte Region",
                "verbose_name_plural": "Geschützte Regionen",
                "ordering": ["region_id"],
            },
        ),
        migrations.RunPython(
            grant_manage_protected_regions, revoke_manage_protected_regions
        ),
    ]
