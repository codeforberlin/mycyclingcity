# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from minecraft.services.preset_groups import sync_minecraft_preset_groups


class Command(BaseCommand):
    help = (
        "Create/update Django auth groups for Minecraft admin modules "
        "(minecraft_admin, mcc_operator, minecraft_moderator, …)."
    )

    def handle(self, *args, **options):
        for group_name, created, missing in sync_minecraft_preset_groups():
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} group: {group_name}"))
            for codename in missing:
                self.stdout.write(self.style.WARNING(f"  Permission missing: {codename}"))
