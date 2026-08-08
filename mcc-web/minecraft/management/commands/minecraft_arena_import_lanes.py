# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from minecraft.services.arena_motion.lanes import import_lanes_from_toml


class Command(BaseCommand):
    help = "Import VeloArena lane geometry from TOML into Django Admin (MinecraftArenaLane)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--toml",
            type=str,
            default="",
            help="Path to velo_arena_race.toml (default: search paths).",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Deactivate DB lanes not present in the TOML.",
        )

    def handle(self, *args, **options):
        path = Path(options["toml"]) if options["toml"] else None
        if path is not None and not path.is_file():
            raise CommandError(f"TOML nicht gefunden: {path}")
        try:
            count = import_lanes_from_toml(
                path,
                deactivate_missing=bool(options["deactivate_missing"]),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Import OK: {count} Bahn(en) in der Datenbank.")
        )
