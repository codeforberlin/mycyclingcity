# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def grant_catalog_permission(apps, schema_editor):
    """Create manage_grant_catalog and assign to operator/admin preset groups."""
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")

    ct = ContentType.objects.get(app_label="minecraft", model="minecraftintegrationconfig")
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="manage_grant_catalog",
        defaults={
            "name": "Vergabe-Katalog (Fahrzeuge, Items) verwalten",
        },
    )
    for group_name in ("minecraft_admin", "mcc_operator", "Operatoren"):
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_catalog_permission(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ct = ContentType.objects.filter(
        app_label="minecraft", model="minecraftintegrationconfig"
    ).first()
    if ct is None:
        return
    perm = Permission.objects.filter(
        content_type=ct, codename="manage_grant_catalog"
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
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("minecraft", "0057_minecraft_admin_group"),
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
                ],
                "verbose_name": "Integration",
                "verbose_name_plural": "Integration",
            },
        ),
        migrations.AddField(
            model_name="mcsession",
            name="grant_catalog_slugs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Katalog-Slugs, die beim Session-Bootstrap per RCON vergeben werden "
                    "(z. B. VehiclesPlus-Garage). Für Pending-Retry persistiert."
                ),
                verbose_name="Vergabe-Katalog (Slugs)",
            ),
        ),
        migrations.CreateModel(
            name="MinecraftGrantCatalogItem",
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
                ("slug", models.SlugField(max_length=64, unique=True, verbose_name="Slug")),
                ("name", models.CharField(max_length=128, verbose_name="Anzeigename")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("vehicle_garage", "Fahrzeug (Garage)"),
                            ("inventory", "Inventar-Item"),
                            ("currency", "Währung / Guthaben"),
                            ("other", "Sonstiges"),
                        ],
                        db_index=True,
                        default="vehicle_garage",
                        max_length=32,
                        verbose_name="Art",
                    ),
                ),
                ("enabled", models.BooleanField(default=True, verbose_name="Aktiv")),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=100, verbose_name="Sortierung"),
                ),
                (
                    "applies_to_player",
                    models.BooleanField(default=True, verbose_name="Spieler-Sessions"),
                ),
                (
                    "applies_to_builder",
                    models.BooleanField(default=True, verbose_name="Bau-Sessions"),
                ),
                (
                    "model_id",
                    models.CharField(
                        blank=True,
                        help_text="z. B. VehiclesPlus ExampleBike — Platzhalter {model}.",
                        max_length=64,
                        verbose_name="Modell-ID",
                    ),
                ),
                (
                    "quantity_default",
                    models.PositiveIntegerField(
                        default=1,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="Standard-Menge",
                    ),
                ),
                (
                    "velos_cost",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="0 = kostenlose Session-Vergabe; >0 = Einlösung vom Radler-Konto.",
                        verbose_name="Velos-Kosten",
                    ),
                ),
                (
                    "repair_velos_cost",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Admin-Reparatur (VehiclesPlus); 0 = keine Reparatur-Aktion.",
                        verbose_name="Reparatur-Velos",
                    ),
                ),
                (
                    "rcon_grant_template",
                    models.CharField(
                        help_text="z. B. v give {player} {model}",
                        max_length=512,
                        verbose_name="RCON Vergabe",
                    ),
                ),
                (
                    "rcon_revoke_template",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Optional beim Slot-Clear. Leer = nur DB-Status; "
                            "Ingame-Garage ggf. manuell/andere Mittel."
                        ),
                        max_length=512,
                        verbose_name="RCON Entfernen",
                    ),
                ),
                (
                    "rcon_repair_template",
                    models.CharField(
                        blank=True,
                        help_text="z. B. v repair {player}. Leer = Art ohne Admin-Reparatur.",
                        max_length=512,
                        verbose_name="RCON Reparatur",
                    ),
                ),
                (
                    "notes",
                    models.CharField(blank=True, max_length=255, verbose_name="Hinweis"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Vergabe-Katalogeintrag",
                "verbose_name_plural": "Vergabe-Katalog",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="MinecraftGrantRecord",
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
                    "account_name",
                    models.CharField(
                        db_index=True, max_length=100, verbose_name="Account-Slot"
                    ),
                ),
                (
                    "account_type",
                    models.CharField(
                        choices=[
                            ("PLAYER", "Spieler (Arena)"),
                            ("BUILDER", "Bau-Team"),
                        ],
                        max_length=16,
                        verbose_name="Account-Typ",
                    ),
                ),
                (
                    "ms_username",
                    models.CharField(blank=True, max_length=32, verbose_name="MS-Login"),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("session_grant", "Session-Vergabe"),
                            ("velos_redeem", "Velos-Einlösung"),
                        ],
                        default="session_grant",
                        max_length=16,
                        verbose_name="Herkunft",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Aktiv"),
                            ("revoked", "Widerrufen"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(default=1, verbose_name="Menge"),
                ),
                (
                    "velos_charged",
                    models.PositiveIntegerField(default=0, verbose_name="Velos abgezogen"),
                ),
                (
                    "granted_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Vergeben"),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Widerrufen"
                    ),
                ),
                (
                    "last_error",
                    models.TextField(blank=True, verbose_name="Letzter Fehler"),
                ),
                (
                    "catalog_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="records",
                        to="minecraft.minecraftgrantcatalogitem",
                        verbose_name="Katalog",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Vergeben von",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="grant_records",
                        to="minecraft.mcsession",
                        verbose_name="Session",
                    ),
                ),
            ],
            options={
                "verbose_name": "Vergabe-Eintrag",
                "verbose_name_plural": "Vergabe-Einträge",
                "ordering": ["-granted_at"],
            },
        ),
        migrations.AddIndex(
            model_name="minecraftgrantrecord",
            index=models.Index(
                fields=["account_name", "status"],
                name="minecraft_grant_acct_status",
            ),
        ),
        migrations.RunPython(grant_catalog_permission, revoke_catalog_permission),
    ]
