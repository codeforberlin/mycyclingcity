# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType

from minecraft.models import MinecraftRconPreset


class Command(BaseCommand):
    help = "Create permission groups for Minecraft RCON preset management."

    def handle(self, *args, **options):
        content_type = ContentType.objects.get_for_model(MinecraftRconPreset)
        all_perms = Permission.objects.filter(content_type=content_type)
        perm_map = {perm.codename: perm for perm in all_perms}

        groups_spec = {
            "minecraft_moderator": [
                "run_rconpreset",
                "view_minecraftrconpreset",
            ],
            "mcc_operator": [
                "add_minecraftrconpreset",
                "change_minecraftrconpreset",
                "delete_minecraftrconpreset",
                "run_rconpreset",
                "change_system_rconpreset",
                "export_rconpreset",
                "view_minecraftrconpreset",
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
