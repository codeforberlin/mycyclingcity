# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    minecraft_session_worker.py
# @note    Periodically expire due / abandoned Minecraft play/builder sessions.

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.services.session_control import (
    expire_due_sessions,
    reconcile_abandoned_sessions,
    retry_pending_session_bootstraps,
)


logger = get_logger("minecraft")


class Command(BaseCommand):
    help = "Expire due Minecraft sessions and detect players who left Paper/proxy."

    def handle(self, *args, **options):
        interval = int(getattr(settings, "MCC_MINECRAFT_SESSION_WORKER_INTERVAL", 5))
        if interval < 1:
            interval = 1
        logger.info("[minecraft_session_worker] started interval=%ss", interval)
        try:
            while True:
                try:
                    pending = retry_pending_session_bootstraps()
                    finished_due = expire_due_sessions()
                    finished_left = reconcile_abandoned_sessions()
                    logger.info(
                        "[minecraft_session_worker] heartbeat pending=%s expired=%s abandoned=%s at %s",
                        pending,
                        len(finished_due),
                        len(finished_left),
                        timezone.now().isoformat(),
                    )
                except Exception as exc:
                    logger.error(
                        "[minecraft_session_worker] cycle failed: %s",
                        exc,
                        exc_info=True,
                    )
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("[minecraft_session_worker] stopped by KeyboardInterrupt")
            self.stdout.write(self.style.WARNING("Session worker stopped."))
