# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


def grant_manage_assigned_protected_regions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_assigned_protected_regions",
        defaults={
            "name": "Zugewiesene Bauzonen (Subregionen der eigenen TOP-Gruppe)"
        },
    )
    for group_name in ("mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_manage_assigned_protected_regions(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="manage_assigned_protected_regions"
    ).first()
    if perm is None:
        return
    for group in Group.objects.filter(name__in=["mcc_operator", "Operatoren"]):
        group.permissions.remove(perm)
    perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0022_dynamo_energy_fields"),
        ("minecraft", "0047_region_outline_settings"),
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
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="assigned_to_group",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Nur bei Master-Regionen: permanente Zuordnung zur TOP-Gruppe. "
                    "Subregionen erben die Ownership über die Master-Region."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_protected_regions",
                to="api.group",
                verbose_name="TOP-Gruppe",
            ),
        ),
        migrations.AddField(
            model_name="minecraftprotectedregion",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Leer = Master-Region. Gesetzt = Subregion innerhalb der Master-Bounds."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subregions",
                to="minecraft.minecraftprotectedregion",
                verbose_name="Master-Region",
            ),
        ),
        migrations.RunPython(
            grant_manage_assigned_protected_regions,
            revoke_manage_assigned_protected_regions,
        ),
    ]
