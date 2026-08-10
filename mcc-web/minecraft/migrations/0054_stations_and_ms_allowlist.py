# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def grant_station_permission(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_minecraft_stations",
        defaults={"name": "Minecraft-Stationen (PCs) und MS-Allowlist verwalten"},
    )
    for group_name in ("mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group:
            group.permissions.add(perm)


def revoke_station_permission(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    Permission.objects.filter(content_type=ct, codename="manage_minecraft_stations").delete()


def seed_ms_allowlist(apps, schema_editor):
    Allowlist = apps.get_model("minecraft", "MinecraftMsAllowlistEntry")
    PlayAccount = apps.get_model("minecraft", "MinecraftPlayAccount")
    TeamReg = apps.get_model("minecraft", "MinecraftTeamRegistration")

    names: set[str] = set()
    for row in PlayAccount.objects.exclude(ms_username="").values_list("ms_username", flat=True):
        name = (row or "").strip()
        if name:
            names.add(name)
    for row in TeamReg.objects.exclude(ms_username="").values_list("ms_username", flat=True):
        name = (row or "").strip()
        if name:
            names.add(name)

    for name in sorted(names, key=str.lower):
        if not Allowlist.objects.filter(ms_username__iexact=name, station__isnull=True).exists():
            Allowlist.objects.create(
                ms_username=name,
                station=None,
                note="Seed aus Account-Stammdaten",
                is_active=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("minecraft", "0053_waitlist_entry_source"),
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
                    (
                        "manage_assigned_protected_regions",
                        "Zugewiesene Bauzonen (Subregionen der eigenen TOP-Gruppe)",
                    ),
                    (
                        "manage_minecraft_accounts",
                        "Minecraft-Accounts (Spieler und Bau) verwalten",
                    ),
                    (
                        "manage_minecraft_operators",
                        "Vanilla-Operatorrechte (/op, /deop) verwalten",
                    ),
                    (
                        "manage_minecraft_stations",
                        "Minecraft-Stationen (PCs) und MS-Allowlist verwalten",
                    ),
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.CreateModel(
            name="MinecraftStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=64, unique=True, verbose_name="Name")),
                ("location", models.CharField(blank=True, max_length=120, verbose_name="Standort")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("play", "Nur Spiel"),
                            ("builder", "Nur Bau"),
                            ("both", "Spiel und Bau"),
                        ],
                        db_index=True,
                        default="both",
                        max_length=16,
                        verbose_name="Rolle",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Aktiv")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Reihenfolge")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Notiz")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "default_play_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="default_for_stations",
                        to="minecraft.minecraftplayaccount",
                        verbose_name="Standard-Spiel-Slot",
                    ),
                ),
            ],
            options={
                "verbose_name": "Station (PC)",
                "verbose_name_plural": "Stationen (PCs)",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="MinecraftMsAllowlistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ms_username", models.CharField(db_index=True, max_length=32, verbose_name="Microsoft-Login")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Notiz")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Aktiv")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Angelegt von",
                    ),
                ),
                (
                    "station",
                    models.ForeignKey(
                        blank=True,
                        help_text="Leer = global für alle Stationen.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ms_allowlist_entries",
                        to="minecraft.minecraftstation",
                        verbose_name="Nur für Station",
                    ),
                ),
            ],
            options={
                "verbose_name": "MS-Allowlist-Eintrag",
                "verbose_name_plural": "MS-Allowlist",
                "ordering": ["ms_username", "station_id"],
            },
        ),
        migrations.AddField(
            model_name="mcsession",
            name="station",
            field=models.ForeignKey(
                blank=True,
                help_text="Physischer PC, an dem diese Session freigegeben wurde.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions",
                to="minecraft.minecraftstation",
                verbose_name="Station (PC)",
            ),
        ),
        migrations.AddConstraint(
            model_name="minecraftmsallowlistentry",
            constraint=models.UniqueConstraint(
                fields=("ms_username", "station"),
                name="minecraft_ms_allowlist_user_station_uniq",
            ),
        ),
        migrations.RunPython(grant_station_permission, revoke_station_permission),
        migrations.RunPython(seed_ms_allowlist, migrations.RunPython.noop),
    ]
