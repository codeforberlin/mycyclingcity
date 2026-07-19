import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.utils import OperationalError
from django.utils import timezone

from config.db_retry import is_db_locked_error, retry_on_db_lock
from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent, MinecraftWorkerState
from minecraft.services.rcon_client import check_connection
from minecraft.services.socket_notifier import wait_for_notification
from minecraft.services.worker import (
    process_next_event,
    requeue_transient_failed_events,
    reset_stale_processing_events,
)


logger = get_logger("minecraft")

# Process multiple outbox events per loop when backlog is high (RCON-bound).
BACKLOG_BATCH_THRESHOLD = 100
BACKLOG_BATCH_SIZE = 25
IDLE_BATCH_SIZE = 1


class Command(BaseCommand):
    help = "Run the Minecraft bridge worker (process outbox events)."

    @retry_on_db_lock(max_retries=10, base_delay=0.05, max_delay=2.0)
    def _save_worker_state(self, state, **fields):
        for name, value in fields.items():
            setattr(state, name, value)
        state.save(update_fields=list(fields.keys()))

    def _process_batch(self) -> int:
        pending = MinecraftOutboxEvent.objects.filter(
            status=MinecraftOutboxEvent.STATUS_PENDING
        ).count()
        batch_size = BACKLOG_BATCH_SIZE if pending >= BACKLOG_BATCH_THRESHOLD else IDLE_BATCH_SIZE
        processed = 0
        for _ in range(batch_size):
            if process_next_event():
                processed += 1
            else:
                break
        if processed:
            logger.info(
                "[minecraft_worker] processed batch=%s pending_before=%s",
                processed,
                pending,
            )
        return processed

    def handle(self, *args, **options):
        # Keep listening on the notify socket. Do NOT sleep with the socket unbound —
        # that drops notifications and delays scoreboard updates by FALLBACK seconds.
        # On wait timeout, re-poll the DB (covers missed notifies / races) then listen again.
        socket_timeout = getattr(settings, "MCC_MINECRAFT_WORKER_SOCKET_TIMEOUT", 5.0)
        health_interval = settings.MCC_MINECRAFT_RCON_HEALTH_INTERVAL
        next_health_check = 0
        last_rcon_ok = None
        last_rcon_error = None
        db_lock_backoff = 0.5
        rcon_ok = False

        reset_stale_processing_events()

        state = MinecraftWorkerState.get_state()
        self._save_worker_state(
            state,
            is_running=True,
            pid=str(os.getpid()),
            started_at=timezone.now(),
            last_heartbeat=timezone.now(),
        )
        ok, error, mode = check_connection()
        rcon_ok = bool(ok)
        if ok and mode != "auth":
            self._save_worker_state(state, last_error="RCON-Port erreichbar (Authentifizierung nicht geprüft)")
        else:
            self._save_worker_state(state, last_error="" if ok else f"RCON-Fehler: {error}")

        logger.info(
            "[minecraft_worker] started (socket notifications, timeout=%ss; "
            "transient RCON failures are retried)",
            socket_timeout,
        )

        try:
            while True:
                now = time.time()

                if now >= next_health_check:
                    ok, error, mode = check_connection()
                    rcon_ok = bool(ok)
                    if ok and mode != "auth":
                        last_error = "RCON-Port erreichbar (Authentifizierung nicht geprüft)"
                    else:
                        last_error = "" if ok else f"RCON-Fehler: {error}"
                    try:
                        self._save_worker_state(
                            state,
                            last_error=last_error,
                            last_heartbeat=timezone.now(),
                        )
                    except OperationalError as exc:
                        if is_db_locked_error(exc):
                            logger.warning("[minecraft_worker] database locked during health heartbeat")
                        else:
                            raise
                    if last_rcon_ok is None or ok != last_rcon_ok or (error and error != last_rcon_error):
                        if not ok:
                            logger.warning(f"[minecraft_worker] RCON Verbindung fehlgeschlagen: {error}")
                        elif last_rcon_ok is False:
                            logger.info("[minecraft_worker] RCON wieder erreichbar — requeue transient failures")
                            requeue_transient_failed_events(limit=500)
                    last_rcon_ok = ok
                    last_rcon_error = error
                    next_health_check = now + health_interval

                # While Minecraft is down, leave pending events untouched (no fail spam).
                if not rcon_ok:
                    try:
                        self._save_worker_state(state, last_heartbeat=timezone.now())
                    except OperationalError as exc:
                        if not is_db_locked_error(exc):
                            raise
                    logger.debug(
                        "[minecraft_worker] RCON unavailable — holding pending outbox, waiting %ss",
                        socket_timeout,
                    )
                    wait_for_notification(timeout=socket_timeout)
                    continue

                try:
                    processed = self._process_batch()
                    try:
                        self._save_worker_state(
                            state,
                            last_heartbeat=timezone.now(),
                            last_error="" if last_rcon_ok else (state.last_error or ""),
                        )
                    except OperationalError as exc:
                        if is_db_locked_error(exc):
                            logger.warning("[minecraft_worker] database locked updating heartbeat")
                        else:
                            raise
                except OperationalError as exc:
                    if is_db_locked_error(exc):
                        logger.warning(
                            "[minecraft_worker] database locked in main loop, backing off %.1fs",
                            db_lock_backoff,
                        )
                        time.sleep(db_lock_backoff)
                        db_lock_backoff = min(db_lock_backoff * 1.5, 5.0)
                        continue
                    raise
                else:
                    db_lock_backoff = 0.5

                if processed:
                    continue

                logger.debug(
                    "[minecraft_worker] no events, waiting for notification (timeout: %ss)",
                    socket_timeout,
                )
                notification_received = wait_for_notification(timeout=socket_timeout)

                if notification_received:
                    logger.debug("[minecraft_worker] notification received, processing events")
                else:
                    logger.debug("[minecraft_worker] notification timeout, re-polling outbox")

        except KeyboardInterrupt:
            logger.info("[minecraft_worker] stopped by keyboard interrupt")
        except Exception as exc:
            try:
                self._save_worker_state(state, last_error=str(exc))
            except Exception:
                pass
            logger.error(f"[minecraft_worker] fatal error: {exc}", exc_info=True)
            raise
        finally:
            try:
                self._save_worker_state(state, is_running=False, pid="")
            except Exception:
                pass
