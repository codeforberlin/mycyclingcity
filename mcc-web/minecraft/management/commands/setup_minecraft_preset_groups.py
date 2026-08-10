# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from minecraft.models import MinecraftIntegrationConfig, MinecraftRconPreset


class Command(BaseCommand):
    help = (
        "Create permission groups for Minecraft admin modules "
        "(control, city, shop) and RCON preset management."
    )

    def handle(self, *args, **options):
        preset_ct = ContentType.objects.get_for_model(MinecraftRconPreset)
        config_ct = ContentType.objects.get_for_model(MinecraftIntegrationConfig)

        perm_map = {
            perm.codename: perm
            for perm in Permission.objects.filter(content_type__in=[preset_ct, config_ct])
        }

        groups_spec = {
            "minecraft_moderator": [
                "access_minecraft_city",
                "run_rconpreset",
                "view_minecraftrconpreset",
                "manage_player_sessions",
                "run_arena_sim",
            ],
            "mcc_operator": [
                "access_minecraft_control",
                "access_minecraft_city",
                "access_minecraft_shop",
                "run_free_rcon",
                "manage_player_sessions",
                "manage_builder_sessions",
                "manage_minecraft_accounts",
                "manage_minecraft_operators",
                "manage_minecraft_stations",
                "run_arena_sim",
                "manage_minecraft_proxy",
                "manage_auth_failover",
                "manage_coreprotect",
                "manage_protected_regions",
                "manage_assigned_protected_regions",
                "add_minecraftrconpreset",
                "change_minecraftrconpreset",
                "delete_minecraftrconpreset",
                "run_rconpreset",
                "change_system_rconpreset",
                "export_rconpreset",
                "view_minecraftrconpreset",
            ],
            # Assign this group (or the run_arena_sim permission) to any staff users
            # who should start arena distance simulations without full arena admin.
            "minecraft_arena_sim": [
                "run_arena_sim",
            ],
            "mcc_viewer": [
                "view_minecraftrconpreset",
            ],
        }

        for group_name, codenames in groups_spec.items():
            group, created = Group.objects.get_or_create(name=group_name)
            group.permissions.clear()
            for codename in codenames:
                perm = perm_map.get(codename)
                if perm:
                    group.permissions.add(perm)
                else:
                    self.stdout.write(self.style.WARNING(f"Permission missing: {codename}"))
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} group: {group_name}"))
