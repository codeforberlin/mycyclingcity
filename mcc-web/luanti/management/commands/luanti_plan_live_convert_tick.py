# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.services.plan import tick_plan_live_convert_regions


class Command(BaseCommand):
    help = "One tick of admin plan live conversion for all active regions (cron/systemd)."

    def handle(self, *args, **options):
        converted = tick_plan_live_convert_regions()
        if converted:
            self.stdout.write(
                self.style.SUCCESS(f"Plan live convert: {converted} block(s)")
            )
