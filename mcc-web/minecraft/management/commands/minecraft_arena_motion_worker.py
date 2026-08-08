# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft_arena_motion_worker.py
# @note    Long-running VeloArena motion loop (Distance → Motion).

from django.core.management.base import BaseCommand

from config.logger_utils import get_logger
from minecraft.services.arena_motion.worker_loop import ArenaMotionWorker

logger = get_logger("minecraft")


class Command(BaseCommand):
    help = (
        "Run the VeloArena minecart motion worker "
        "(shared RCON lock; no scoreboard commands)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--idle-poll",
            type=float,
            default=0.25,
            help="Seconds between control-state polls when idle (default 0.25).",
        )

    def handle(self, *args, **options):
        idle = float(options["idle_poll"])
        self.stdout.write(self.style.NOTICE("Starting arena motion worker…"))
        worker = ArenaMotionWorker()
        try:
            worker.run_forever(poll_idle_seconds=idle)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Arena motion worker stopped."))
        except Exception as exc:
            logger.exception("[arena_motion] worker crashed: %s", exc)
            raise
