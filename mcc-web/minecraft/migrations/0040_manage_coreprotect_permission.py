# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def grant_manage_coreprotect(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_coreprotect",
        defaults={"name": "CoreProtect Rollback/Restore"},
    )
    for group_name in ("mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_manage_coreprotect(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="manage_coreprotect"
    ).first()
    if perm is None:
        return
    for group in Group.objects.filter(name__in=["mcc_operator", "Operatoren"]):
        group.permissions.remove(perm)
    perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0039_world_border_config"),
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
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.RunPython(grant_manage_coreprotect, revoke_manage_coreprotect),
    ]
