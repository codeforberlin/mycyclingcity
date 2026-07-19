from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.db.utils import OperationalError
from django.utils import timezone

from config.db_retry import is_db_locked_error, retry_on_db_lock
from config.logger_utils import get_logger
from minecraft.models import MinecraftOutboxEvent, MinecraftTeamRegistration
from minecraft.services.team_scoreboard import (
    add_team_spendable_score,
    ensure_team_scoreboard_objective,
    register_team_on_server,
    set_team_spendable_score,
    sync_all_registered_teams,
    unregister_team_on_server,
)


logger = get_logger("minecraft")

# Transient Minecraft/RCON outages — keep or requeue events so scoreboard deltas are not lost.
TRANSIENT_ERROR_MARKERS = (
    "connection refused",
    "errno 111",
    "timed out",
    "timeout",
    "connection reset",
    "broken pipe",
    "network is unreachable",
    "no route to host",
    "temporarily unavailable",
    "server is closed",
)


def is_transient_minecraft_error(error: str | BaseException | None) -> bool:
    msg = str(error or "").lower()
    return any(marker in msg for marker in TRANSIENT_ERROR_MARKERS)


def reset_stale_processing_events() -> int:
    """Return crashed worker events stuck in 'processing' back to pending."""
    updated = MinecraftOutboxEvent.objects.filter(
        status=MinecraftOutboxEvent.STATUS_PROCESSING
    ).update(status=MinecraftOutboxEvent.STATUS_PENDING)
    if updated:
        logger.warning(
            "[minecraft_worker] reset %s stale processing outbox event(s) to pending",
            updated,
        )
    return updated


def requeue_transient_failed_events(*, limit: int = 200) -> int:
    """
    Move failed events caused by Minecraft/RCON outages back to pending.

    Call when RCON is healthy again so scoreboard deltas from the outage are applied.
    """
    qs = (
        MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_FAILED)
        .order_by("created_at")[:limit]
    )
    requeued = 0
    for event in qs:
        if not is_transient_minecraft_error(event.last_error):
            continue
        event.status = MinecraftOutboxEvent.STATUS_PENDING
        event.processed_at = None
        event.save(update_fields=["status", "processed_at"])
        requeued += 1
    if requeued:
        logger.info(
            "[minecraft_worker] requeued %s transient failed outbox event(s) for retry",
            requeued,
        )
    return requeued


@retry_on_db_lock(max_retries=15, base_delay=0.05, max_delay=2.0)
def _get_pending_event():
    backoff = getattr(settings, "MCC_MINECRAFT_OUTBOX_RETRY_BACKOFF_SECONDS", 5)
    now = timezone.now()
    ready = Q(processed_at__isnull=True) | Q(
        processed_at__lte=now - timedelta(seconds=max(1, int(backoff)))
    )
    qs = (
        MinecraftOutboxEvent.objects.filter(status=MinecraftOutboxEvent.STATUS_PENDING)
        .filter(ready)
        .order_by("created_at")
    )
    if connection.vendor != "sqlite":
        qs = qs.select_for_update(skip_locked=True)
    with transaction.atomic():
        event = qs.first()
        if not event:
            return None
        event.mark_processing()
        return event


def _handle_update_team_velos(event: MinecraftOutboxEvent) -> None:
    payload = event.payload or {}
    player = payload.get("player")
    if not player:
        raise ValueError("Missing player in payload")

    velos_spendable = int(payload.get("velos_spendable", 0))
    spendable_action = payload.get("spendable_action", "set")
    spendable_delta = payload.get("spendable_delta")
    reason = payload.get("reason", "unknown")

    logger.debug(
        f"[minecraft_worker] processing UPDATE_TEAM_VELOS event_id={event.id} "
        f"player={player} velos_spendable={velos_spendable} "
        f"spendable_action={spendable_action} spendable_delta={spendable_delta} reason={reason}"
    )

    if spendable_action == "set" and payload.get("reason") == "db_update" and spendable_delta is not None:
        spendable_action = "add"
        logger.debug(
            "[minecraft_worker] converted spendable_action from 'set' to 'add' (db_update with delta)"
        )

    ensure_team_scoreboard_objective()
    if spendable_action == "add" and spendable_delta is not None:
        add_team_spendable_score(player, int(spendable_delta))
    else:
        set_team_spendable_score(player, velos_spendable)


def _handle_update_group_velos(event: MinecraftOutboxEvent) -> None:
    """Legacy handler — delegates to spendable-only team update."""
    _handle_update_team_velos(event)


def _handle_register_team(event: MinecraftOutboxEvent) -> None:
    payload = event.payload or {}
    registration_id = payload.get("registration_id")
    if not registration_id:
        raise ValueError("Missing registration_id in payload")

    registration = MinecraftTeamRegistration.objects.select_related("group").get(pk=registration_id)
    register_team_on_server(registration)


def _handle_unregister_team(event: MinecraftOutboxEvent) -> None:
    payload = event.payload or {}
    player = payload.get("player")
    if not player:
        raise ValueError("Missing player in payload")
    unregister_team_on_server(player)


def _handle_sync_registered_teams(event: MinecraftOutboxEvent) -> None:
    sync_all_registered_teams()


def _handle_sync_all(event: MinecraftOutboxEvent) -> None:
    """Legacy alias."""
    _handle_sync_registered_teams(event)


def _handle_ensure_objectives(event: MinecraftOutboxEvent) -> None:
    ensure_team_scoreboard_objective()


def _dispatch_event(event: MinecraftOutboxEvent) -> None:
    if event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_TEAM_VELOS:
        _handle_update_team_velos(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_GROUP_VELOS:
        _handle_update_group_velos(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_REGISTER_TEAM:
        _handle_register_team(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_UNREGISTER_TEAM:
        _handle_unregister_team(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_SYNC_REGISTERED_TEAMS:
        _handle_sync_registered_teams(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_SYNC_ALL:
        _handle_sync_all(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_ENSURE_OBJECTIVES:
        _handle_ensure_objectives(event)
    elif event.event_type == MinecraftOutboxEvent.EVENT_UPDATE_PLAYER_COINS:
        logger.warning(
            f"[minecraft_worker] skipping deprecated UPDATE_PLAYER_COINS event_id={event.id}"
        )
    else:
        raise ValueError(f"Unsupported event_type: {event.event_type}")


def process_next_event() -> bool:
    try:
        event = _get_pending_event()
    except OperationalError as exc:
        if is_db_locked_error(exc):
            logger.warning("[minecraft_worker] database locked while fetching outbox event")
            return False
        raise
    if not event:
        return False

    logger.debug(
        f"[minecraft_worker] processing event_id={event.id} type={event.event_type} status={event.status}"
    )
    try:
        _dispatch_event(event)
        try:
            event.mark_done()
        except OperationalError as exc:
            if is_db_locked_error(exc):
                logger.warning(
                    "[minecraft_worker] database locked marking event_id=%s done (will retry)",
                    event.id,
                )
                MinecraftOutboxEvent.objects.filter(pk=event.pk).update(
                    status=MinecraftOutboxEvent.STATUS_PENDING
                )
                return False
            raise
        logger.info(f"[minecraft_worker] processed event_id={event.id} type={event.event_type}")
        return True
    except Exception as exc:
        transient = is_transient_minecraft_error(exc)
        logger.error(
            "[minecraft_worker] event %s id=%s type=%s: %s",
            "transient-retry" if transient else "failed",
            event.id,
            event.event_type,
            exc,
            exc_info=not transient,
        )
        try:
            if transient:
                event.mark_retry(str(exc))
            else:
                event.mark_failed(str(exc))
        except OperationalError as db_exc:
            if is_db_locked_error(db_exc):
                logger.warning(
                    "[minecraft_worker] database locked marking event_id=%s after error",
                    event.id,
                )
                return False
            raise
        return True
