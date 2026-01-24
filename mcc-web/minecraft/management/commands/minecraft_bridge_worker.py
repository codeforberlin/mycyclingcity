import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftWorkerState
from minecraft.services.rcon_client import check_connection
from minecraft.services.worker import process_next_event


logger = get_logger("minecraft")


class Command(BaseCommand):
    help = "Run the Minecraft bridge worker (process outbox events)."

    def handle(self, *args, **options):
        poll_interval = settings.MCC_MINECRAFT_WORKER_POLL_INTERVAL
        health_interval = settings.MCC_MINECRAFT_RCON_HEALTH_INTERVAL
        next_health_check = 0
        last_rcon_ok = None
        last_rcon_error = None

        state = MinecraftWorkerState.get_state()
        state.is_running = True
        state.pid = str(os.getpid())
        state.started_at = timezone.now()
        state.last_heartbeat = timezone.now()
        ok, error, mode = check_connection()
        if ok and mode != "auth":
            state.last_error = "RCON-Port erreichbar (Authentifizierung nicht geprüft)"
        else:
            state.last_error = "" if ok else f"RCON-Fehler: {error}"
        state.save(update_fields=["is_running", "pid", "started_at", "last_heartbeat", "last_error"])

        logger.info("[minecraft_worker] started")

        try:
            while True:
                now = time.time()
                if now >= next_health_check:
                    ok, error, mode = check_connection()
                    if ok and mode != "auth":
                        state.last_error = "RCON-Port erreichbar (Authentifizierung nicht geprüft)"
                    else:
                        state.last_error = "" if ok else f"RCON-Fehler: {error}"
                    state.last_heartbeat = timezone.now()
                    state.save(update_fields=["last_error", "last_heartbeat"])
                    if last_rcon_ok is None or ok != last_rcon_ok or (error and error != last_rcon_error):
                        if not ok:
                            logger.warning(f"[minecraft_worker] RCON Verbindung fehlgeschlagen: {error}")
                    last_rcon_ok = ok
                    last_rcon_error = error
                    next_health_check = now + health_interval

                processed = process_next_event()
                state.last_heartbeat = timezone.now()
                state.save(update_fields=["last_heartbeat"])

                if not processed:
                    logger.debug(f"[minecraft_worker] no events to process, sleeping {poll_interval}s")
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("[minecraft_worker] stopped by keyboard interrupt")
        except Exception as exc:
            state.last_error = str(exc)
            state.save(update_fields=["last_error"])
            logger.error(f"[minecraft_worker] fatal error: {exc}")
            raise
        finally:
            state.is_running = False
            state.pid = ""
            state.save(update_fields=["is_running", "pid"])
