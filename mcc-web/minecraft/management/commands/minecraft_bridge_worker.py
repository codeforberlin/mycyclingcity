import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.models import MinecraftWorkerState
from minecraft.services.rcon_client import check_connection
from minecraft.services.worker import process_next_event
from minecraft.services.socket_notifier import wait_for_notification


logger = get_logger("minecraft")


class Command(BaseCommand):
    help = "Run the Minecraft bridge worker (process outbox events)."

    def handle(self, *args, **options):
        # Fallback polling interval (used if socket notification fails)
        fallback_poll_interval = getattr(settings, 'MCC_MINECRAFT_WORKER_FALLBACK_POLL_INTERVAL', 30)
        # Socket wait timeout (how long to wait for notification before fallback polling)
        socket_timeout = getattr(settings, 'MCC_MINECRAFT_WORKER_SOCKET_TIMEOUT', 5.0)
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

        logger.info("[minecraft_worker] started (using socket notifications with fallback polling)")

        try:
            while True:
                now = time.time()
                
                # Health check
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

                # Try to process events
                processed = process_next_event()
                state.last_heartbeat = timezone.now()
                state.save(update_fields=["last_heartbeat"])

                if processed:
                    # Event was processed, immediately check for more
                    continue
                
                # No events to process - wait for notification via socket
                logger.debug(f"[minecraft_worker] no events, waiting for notification (timeout: {socket_timeout}s)")
                notification_received = wait_for_notification(timeout=socket_timeout)
                
                if notification_received:
                    # Notification received, process events immediately
                    logger.debug(f"[minecraft_worker] notification received, processing events")
                    continue
                
                # No notification received (timeout) - fallback to polling
                logger.debug(f"[minecraft_worker] no notification, fallback polling in {fallback_poll_interval}s")
                time.sleep(fallback_poll_interval)
                
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
