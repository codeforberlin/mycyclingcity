# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations


def add_vp_packs_permission(apps, schema_editor):
    """Create manage_vehiclesplus_packs and assign to operator/admin preset groups."""
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_vehiclesplus_packs",
        defaults={
            "name": "VehiclesPlus Resourcepacks erzeugen/erweitern",
        },
    )
    for group_name in ("minecraft_admin", "mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_vp_packs_permission(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="manage_vehiclesplus_packs"
    ).first()
    if perm is None:
        return
    for group in Group.objects.filter(
        name__in=["minecraft_admin", "mcc_operator", "Operatoren"]
    ):
        group.permissions.remove(perm)
    perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("minecraft", "0060_city_mode_vehiclesplus_lp"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
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
                    (
                        "manage_grant_catalog",
                        "Vergabe-Katalog (Fahrzeuge, Items) verwalten",
                    ),
                    (
                        "manage_vehiclesplus_packs",
                        "VehiclesPlus Resourcepacks erzeugen/erweitern",
                    ),
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.RunPython(add_vp_packs_permission, revoke_vp_packs_permission),
    ]
