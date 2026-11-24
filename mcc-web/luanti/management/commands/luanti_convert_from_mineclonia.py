# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from luanti.services.mcl_convert import apply_conversion, build_report


class Command(BaseCommand):
    help = (
        "Map Mineclonia itemstrings in this host's Django data using "
        "worlds/<world>/mcc_migrator_map.json. Dry-run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--world",
            default="",
            help="World directory name (default: MCC_LUANTI_WORLD).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write itemstrings. Refuses when the map file is missing, unknown, or conflicting.",
        )

    def handle(self, *args, **options):
        world = (options["world"] or "").strip() or getattr(settings, "MCC_LUANTI_WORLD", "mycyclingcity")
        if options["apply"]:
            report = apply_conversion(world)
        else:
            report = build_report(world)
        self.stdout.write(f"world={world}")
        self.stdout.write(f"map={report.file_path} found={report.file_found}")
        for key, count in sorted(report.counts.items()):
            self.stdout.write(f"  {key}={count}")
        if report.unknown:
            self.stdout.write("unknown:")
            for name in report.unknown:
                self.stdout.write(f"  {name}")
        if report.conflicts:
            self.stdout.write("conflicts:")
            for row in report.conflicts:
                self.stdout.write(f"  {row}")
        if options["apply"] and report.blocked:
            raise CommandError("conversion refused")
        if report.applied:
            self.stdout.write(self.style.SUCCESS("applied"))
        else:
            self.stdout.write("dry-run")
