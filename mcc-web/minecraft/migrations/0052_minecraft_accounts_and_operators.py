# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def grant_account_operator_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    specs = [
        (
            "manage_minecraft_accounts",
            "Minecraft-Accounts (Spieler und Bau) verwalten",
        ),
        (
            "manage_minecraft_operators",
            "Vanilla-Operatorrechte (/op, /deop) verwalten",
        ),
    ]
    for codename, name in specs:
        perm, _ = Permission.objects.get_or_create(
            content_type=ct,
            codename=codename,
            defaults={"name": name},
        )
        for group_name in ("mcc_operator", "Operatoren"):
            group = Group.objects.filter(name=group_name).first()
            if group is not None:
                group.permissions.add(perm)


def revoke_account_operator_permissions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    for codename in ("manage_minecraft_accounts", "manage_minecraft_operators"):
        perm = Permission.objects.filter(content_type=ct, codename=codename).first()
        if perm is None:
            continue
        for group in Group.objects.filter(name__in=["mcc_operator", "Operatoren"]):
            group.permissions.remove(perm)
        perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0022_dynamo_energy_fields"),
        ("minecraft", "0051_protected_region_spawn_point"),
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
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.AddField(
            model_name="minecraftplayaccount",
            name="assigned_to_group",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optionale Zuordnung zu einer TOP-Gruppe (parent is None) "
                    "für Filter und Organisation in der Account-Verwaltung."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_play_accounts",
                to="api.group",
                verbose_name="TOP-Gruppe",
            ),
        ),
        migrations.CreateModel(
            name="MinecraftVanillaOpLog",
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
                ("action", models.CharField(choices=[("op", "op"), ("deop", "deop")], max_length=8)),
                ("player_name", models.CharField(max_length=32, verbose_name="Spielername")),
                (
                    "account_type",
                    models.CharField(blank=True, max_length=16, verbose_name="Account-Typ"),
                ),
                (
                    "account_ref",
                    models.CharField(blank=True, max_length=64, verbose_name="Account-Ref"),
                ),
                ("ok", models.BooleanField(default=False)),
                ("detail", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Vanilla-OP-Aktion",
                "verbose_name_plural": "Vanilla-OP-Aktionen",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(
            grant_account_operator_permissions,
            revoke_account_operator_permissions,
        ),
    ]
