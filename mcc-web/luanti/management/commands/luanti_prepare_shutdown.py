# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.services.session_control import prepare_luanti_shutdown


class Command(BaseCommand):
    help = (
        "Kick Luanti players so inventories are saved via session/leave, "
        "then end any remaining open sessions (used before server stop/restart)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--wait",
            type=float,
            default=25.0,
            help="Seconds to wait for leave callbacks before force-ending sessions.",
        )

    def handle(self, *args, **options):
        result = prepare_luanti_shutdown(wait_seconds=options["wait"])
        self.stdout.write(
            "prepare: requested=%(sessions_requested)s forced=%(forced_end)s ok=%(ok)s"
            % {
                "sessions_requested": result["sessions_requested"],
                "forced_end": ",".join(result["forced_end"]) or "-",
                "ok": result["ok"],
            }
        )
        if result["forced_end"]:
            self.stdout.write(
                self.style.WARNING(
                    "Force-ended without fresh inventory: " + ", ".join(result["forced_end"])
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("All open sessions closed cleanly."))
